"""passkey_service — เข้าสู่ระบบด้วย Passkey (WebAuthn) ผ่านไลบรารี py_webauthn

ลำดับงาน (ทั้งลงทะเบียนและเข้าสู่ระบบ):
1. ``*_options``  สร้าง challenge สุ่ม เก็บไว้ฝั่ง server (Redis หรือหน่วยความจำ) อายุ 5 นาที คืน flow_id + options ให้เบราว์เซอร์
2. เบราว์เซอร์ให้ผู้ใช้สแกนหน้า/นิ้ว แล้วส่ง credential กลับมาพร้อม flow_id
3. ``*_verify`` ดึง challenge ออก (ใช้ได้ครั้งเดียว) แล้วให้ py_webauthn ตรวจลายเซ็น/origin/RP ID

เข้าสู่ระบบแบบไม่ต้องกรอกอีเมล (discoverable credential): options ไม่ระบุ allow_credentials
แล้วหา passkey จาก credential id ที่เบราว์เซอร์ส่งมา
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.core.redis_client import get_redis
from app.models.domain import Passkey, User

logger = logging.getLogger("passkey")

CHALLENGE_TTL_SECONDS = 300
MAX_PASSKEYS_PER_USER = 20
NAME_MAX = 60


class PasskeyError(Exception):
    """ข้อผิดพลาดที่แสดงให้ผู้ใช้เห็นได้ (status 400)"""


# ---------------------------------------------------------------- ค่าตั้งค่า


def rp_id() -> str:
    return settings.WEBAUTHN_RP_ID or (urlparse(settings.FRONTEND_URL).hostname or "localhost")


def expected_origins() -> list[str]:
    if settings.WEBAUTHN_ORIGINS:
        raw = settings.WEBAUTHN_ORIGINS.split(",")
    else:
        raw = [settings.FRONTEND_URL, *settings.ALLOWED_ORIGINS]
    out = []
    for o in raw:
        o = o.strip().rstrip("/")
        if o and o not in out:
            out.append(o)
    return out


_LOCAL_ORIGIN = re.compile(r"https?://(localhost|127\.0\.0\.1)(:\d{1,5})?")


def _origins_for(credential: dict) -> list[str]:
    """origin ที่ยอมรับสำหรับคำขอนี้ — ตอนพัฒนา (RP ID = localhost) ยอมทุกพอร์ตของ localhost
    เพราะ dev/CI เปิดหน้าเว็บได้หลายพอร์ต (vite 5173, nginx 8080) แต่ FRONTEND_URL ตั้งได้ค่าเดียว"""
    origins = expected_origins()
    if rp_id() != "localhost":
        return origins
    try:
        raw = (credential.get("response") or {}).get("clientDataJSON") or ""
        origin = json.loads(base64url_to_bytes(raw)).get("origin", "")
    except (ValueError, TypeError, AttributeError):  # ข้อมูลเสีย — ให้ py_webauthn ปฏิเสธเอง
        return origins
    if isinstance(origin, str) and _LOCAL_ORIGIN.fullmatch(origin) and origin not in origins:
        origins = [*origins, origin]
    return origins


# ---------------------------------------------------------------- เก็บ challenge


class _MemoryStore:
    def __init__(self):
        self._data: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: bytes, ttl: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._data = {k: v for k, v in self._data.items() if v[0] > now}  # ล้างของหมดอายุ
            self._data[key] = (now + ttl, value)

    def pop(self, key: str) -> bytes | None:
        with self._lock:
            item = self._data.pop(key, None)
        if item is None or item[0] < time.monotonic():
            return None
        return item[1]


_memory = _MemoryStore()


def _store_set(key: str, value: dict) -> None:
    data = json.dumps(value).encode()
    r = get_redis()
    if r is not None:
        r.set(f"passkey:{key}", data, ex=CHALLENGE_TTL_SECONDS)
    else:
        _memory.set(key, data, CHALLENGE_TTL_SECONDS)


def _store_pop(key: str) -> dict | None:
    r = get_redis()
    if r is not None:
        pipe = r.pipeline()
        pipe.get(f"passkey:{key}")
        pipe.delete(f"passkey:{key}")
        data = pipe.execute()[0]
    else:
        data = _memory.pop(key)
    return json.loads(data) if data else None


def _new_flow(kind: str, challenge: bytes, user_id: int | None, **extra) -> str:
    flow_id = secrets.token_urlsafe(24)
    _store_set(f"{kind}:{flow_id}", {"challenge": bytes_to_base64url(challenge), "user_id": user_id, **extra})
    return flow_id


def _take_flow(kind: str, flow_id: str) -> dict:
    flow = _store_pop(f"{kind}:{flow_id}") if flow_id else None
    if not flow:
        raise PasskeyError("คำขอหมดอายุแล้ว กรุณาลองใหม่อีกครั้ง")
    return flow


# ---------------------------------------------------------------- ลงทะเบียน


def _user_handle(db: Session, user: User) -> str:
    """user.id ฝั่ง WebAuthn — สุ่มครั้งแรกแล้วใช้ค่าเดิมกับทุก passkey ของผู้ใช้คนนี้"""
    existing = db.query(Passkey.user_handle).filter(Passkey.user_id == user.id).first()
    return existing[0] if existing else bytes_to_base64url(secrets.token_bytes(32))


def registration_options(db: Session, user: User) -> dict:
    owned = db.query(Passkey).filter(Passkey.user_id == user.id).all()
    if len(owned) >= MAX_PASSKEYS_PER_USER:
        raise PasskeyError(f"มี passkey ครบ {MAX_PASSKEYS_PER_USER} อันแล้ว กรุณาลบอันที่ไม่ใช้ก่อน")
    handle = _user_handle(db, user)
    options = generate_registration_options(
        rp_id=rp_id(),
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=base64url_to_bytes(handle),
        user_name=user.email,
        user_display_name=user.display_name or user.email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        # กันสร้างซ้ำบนอุปกรณ์/ผู้จัดการรหัสผ่านเดิม
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.credential_id)) for p in owned],
    )
    flow_id = _new_flow("reg", options.challenge, user.id, handle=handle)
    return {"flow_id": flow_id, "options": json.loads(options_to_json(options))}


def _clean_name(name: str | None, fallback: str) -> str:
    name = " ".join((name or "").split())[:NAME_MAX]
    return name or fallback


def register(db: Session, user: User, flow_id: str, credential: dict, name: str | None) -> Passkey:
    flow = _take_flow("reg", flow_id)
    handle = flow.get("handle")
    if flow.get("user_id") != user.id or not handle:
        raise PasskeyError("คำขอไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(flow["challenge"]),
            expected_rp_id=rp_id(),
            expected_origin=_origins_for(credential),
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        logger.info("ลงทะเบียน passkey ไม่ผ่าน user=%s: %s", user.id, exc)
        raise PasskeyError("ยืนยัน passkey ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง") from exc

    cred_id = bytes_to_base64url(verified.credential_id)
    if db.query(Passkey).filter(Passkey.credential_id == cred_id).first():
        raise PasskeyError("passkey นี้ถูกลงทะเบียนไว้แล้ว")
    transports = credential.get("response", {}).get("transports") or []
    valid_transports = {t.value for t in AuthenticatorTransport}
    count = db.query(Passkey).filter(Passkey.user_id == user.id).count()
    passkey = Passkey(
        user_id=user.id,
        credential_id=cred_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        user_handle=handle,
        transports=",".join(t for t in transports if t in valid_transports) or None,
        name=_clean_name(name, f"Passkey {count + 1}"),
        aaguid=str(verified.aaguid) if verified.aaguid else None,
        backed_up=bool(verified.credential_backed_up),
    )
    db.add(passkey)
    db.commit()
    db.refresh(passkey)
    logger.info("เพิ่ม passkey id=%s user=%s backed_up=%s", passkey.id, user.id, passkey.backed_up)
    return passkey


# ---------------------------------------------------------------- เข้าสู่ระบบ


def authentication_options(db: Session | None = None, user: User | None = None, purpose: str = "auth") -> dict:
    """user=None: เข้าสู่ระบบแบบไม่ระบุบัญชี (discoverable) · user: ยืนยันตัวตนของผู้ใช้คนนี้ (เช่น ก่อนลงนาม)
    — จำกัดเฉพาะ passkey ของบัญชีนี้ และ flow ใช้ได้กับ purpose เดียวกันเท่านั้น"""
    allow = None
    if user is not None:
        owned = list_passkeys(db, user)
        if not owned:
            raise PasskeyError("บัญชีนี้ยังไม่มี passkey — เพิ่มได้ที่เมนูความปลอดภัย")
        allow = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(p.credential_id),
                transports=[AuthenticatorTransport(t) for t in (p.transports or "").split(",") if t] or None,
            )
            for p in owned
        ]
    options = generate_authentication_options(
        rp_id=rp_id(),
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    flow_id = _new_flow(purpose, options.challenge, user.id if user else None)
    return {"flow_id": flow_id, "options": json.loads(options_to_json(options))}


def _verify_assertion(db: Session, flow: dict, credential: dict) -> Passkey:
    """ตรวจลายเซ็นของ passkey กับ challenge ใน flow แล้วอัปเดตตัวนับ (ยังไม่ commit)"""
    cred_id = credential.get("id") or credential.get("rawId") or ""
    passkey = db.query(Passkey).filter(Passkey.credential_id == cred_id).first()
    if passkey is None:
        raise PasskeyError("ไม่พบ passkey นี้ในระบบ (อาจถูกลบไปแล้ว) กรุณาเข้าสู่ระบบด้วยวิธีอื่น")
    if flow.get("user_id") is not None and passkey.user_id != flow["user_id"]:
        raise PasskeyError("passkey นี้ไม่ใช่ของบัญชีที่เข้าสู่ระบบอยู่")
    user_handle = credential.get("response", {}).get("userHandle")
    if user_handle and user_handle != passkey.user_handle:
        raise PasskeyError("passkey ไม่ตรงกับบัญชี")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(flow["challenge"]),
            expected_rp_id=rp_id(),
            expected_origin=_origins_for(credential),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        logger.info("ยืนยัน passkey ไม่ผ่าน passkey=%s: %s", passkey.id, exc)
        raise PasskeyError("ยืนยัน passkey ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง") from exc
    passkey.sign_count = verified.new_sign_count
    passkey.backed_up = bool(verified.credential_backed_up)
    passkey.last_used_at = datetime.now(timezone.utc)
    return passkey


def authenticate(db: Session, flow_id: str, credential: dict) -> User:
    flow = _take_flow("auth", flow_id)
    passkey = _verify_assertion(db, flow, credential)
    user = db.get(User, passkey.user_id)
    if user is None or not user.is_active:
        raise PasskeyError("บัญชีนี้ถูกปิดใช้งาน")
    if not user.is_verified:
        raise PasskeyError("กรุณายืนยันอีเมลของคุณก่อนเข้าใช้งาน")
    db.commit()
    return user


def verify_for_user(db: Session, user: User, purpose: str, flow_id: str, credential: dict) -> Passkey:
    """ยืนยันว่าผู้ใช้ที่เข้าสู่ระบบอยู่คือเจ้าของบัญชีจริง (สแกนหน้า/นิ้วตอนนี้) — ผู้เรียกเป็นคน commit"""
    flow = _take_flow(purpose, flow_id)
    if flow.get("user_id") != user.id:
        raise PasskeyError("คำขอไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง")
    return _verify_assertion(db, flow, credential)


# ---------------------------------------------------------------- จัดการ


def list_passkeys(db: Session, user: User) -> list[Passkey]:
    return db.query(Passkey).filter(Passkey.user_id == user.id).order_by(Passkey.created_at, Passkey.id).all()


def get_owned(db: Session, user: User, passkey_id: int) -> Passkey | None:
    return db.query(Passkey).filter(Passkey.id == passkey_id, Passkey.user_id == user.id).first()


def rename(db: Session, passkey: Passkey, name: str) -> Passkey:
    passkey.name = _clean_name(name, passkey.name)
    db.commit()
    db.refresh(passkey)
    return passkey


def delete(db: Session, passkey: Passkey) -> None:
    db.delete(passkey)
    db.commit()


def to_dict(p: Passkey) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "backed_up": bool(p.backed_up),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
    }

