"""ใบรับรองลายเซ็นดิจิทัล (.p12/.pfx) ที่ผู้ใช้เก็บไว้บนระบบ — ใช้เซ็นได้โดยไม่ต้องเลือกไฟล์ทุกครั้ง

ผู้ใช้กำหนด (2026-11-18):
- อัปโหลดแล้ว **ตรวจรหัสครั้งแรกก่อนเก็บ** (เกณฑ์เดียวกับตอนเซ็น: รหัสถูก, ยังไม่หมดอายุ/ถึงวันใช้, อนุญาตให้ลงนาม)
  และเก็บชื่อผู้ถือ ผู้ออก วันเริ่มใช้ วันหมดอายุ วันที่อัปโหลด
- **ไม่เก็บรหัสผ่าน** — ทุกครั้งที่เลือกใช้เซ็น หรือจะลบ ต้องกรอกรหัสของใบรับรอง
- ลบได้ตลอด (ยืนยันรหัสก่อนลบ)

ความปลอดภัย:
- ไฟล์ p12 ถูกล็อกด้วยรหัสของผู้ใช้อยู่แล้ว · ระบบเข้ารหัสซ้ำอีกชั้นด้วยกุญแจจาก JWT_SECRET (Fernet) ก่อนเก็บลงฐานข้อมูล
  → ฐานข้อมูล/backup หลุดไปอย่างเดียวยังได้แค่ข้อมูลที่ถอดไม่ได้ · เปลี่ยน JWT_SECRET = ใบรับรองที่เก็บไว้ใช้ไม่ได้ (ต้องอัปโหลดใหม่)
- รหัสผิดนับต่อผู้ใช้: 5 ครั้ง / 15 นาที → ล็อกการใช้ใบรับรองที่เก็บไว้ชั่วคราว (กันเดารหัสผ่านจากเซิร์ฟเวอร์)
  · กรอกถูกแล้วล้างตัวนับ
- ใช้ได้เฉพาะเจ้าของ (หาแถวด้วย user_id เสมอ)

ปลดล็อกด้วย passkey (ผู้ใช้ขอ 2026-11-19 · เลือกแบบผูกกับอุปกรณ์ "PRF"):
- ผูก: เบราว์เซอร์ขอค่าลับจาก passkey (ส่วนขยาย WebAuthn PRF + prf_salt สุ่ม) → เข้ารหัสรหัสผ่านของใบรับรองด้วย AES-GCM
  ในเครื่อง (frontend/src/utils/certPasskey.js) → ส่ง wrapped + assertion ของ passkey + รหัส (ตรวจว่าถูกก่อนเก็บ) มาที่นี่
- server เก็บแค่ prf_salt + wrapped — **ไม่มีค่าลับจาก passkey จึงถอดรหัสเองไม่ได้** (ข้อตกลง "ไม่เก็บรหัส" ยังเป็นจริง)
- ใช้/ลบ: เบราว์เซอร์ถอด wrapped ได้รหัส แล้วส่งรหัสมาเหมือนพิมพ์เอง → ผ่าน unlock() ตัวเดิม (นับครั้งผิด/ล็อกเหมือนเดิม)
- ลบ passkey ออกจากบัญชี = ลบการผูกทั้งหมดของ passkey นั้น
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core import ratelimit
from app.models.domain import CertificatePasskey, User, UserCertificate

logger = logging.getLogger(__name__)

MAX_PER_USER = 5
MAX_FILE_BYTES = 1024 * 1024  # p12 ปกติไม่กี่ KB (รวม chain ก็ไม่ถึง 100 KB)
WRONG_PASSWORD_MAX = 5
WRONG_PASSWORD_WINDOW = 15 * 60
_RL_NAME = "cert-password"
_LOCKED_MSG = "กรอกรหัสใบรับรองผิดหลายครั้ง"


class CertificateError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _fernet():
    from cryptography.fernet import Fernet

    from app.core.security import SECRET_KEY

    key = hashlib.sha256(("user-certificates:" + SECRET_KEY).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _seal(pfx_bytes: bytes) -> bytes:
    return _fernet().encrypt(pfx_bytes)


def _unseal(blob: bytes) -> bytes:
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(bytes(blob))
    except InvalidToken:
        raise CertificateError("ใบรับรองที่เก็บไว้เปิดไม่ได้แล้ว (กุญแจของระบบเปลี่ยน) — ลบแล้วอัปโหลดใหม่", 409) from None


def _open(pfx_bytes: bytes, password: str):
    """เปิดและตรวจใบรับรอง (เกณฑ์เดียวกับตอนเซ็น) — คืน (signer, info)"""
    from app.services import signature_service
    from app.services.pdf_service import PDFError

    try:
        return signature_service.load_signer(pfx_bytes, password or "")
    except PDFError as exc:
        raise CertificateError(str(exc)) from None


def _metadata(signer) -> dict:
    cert = signer.signing_cert
    validity = cert["tbs_certificate"]["validity"]
    subject, issuer = cert.subject.native, cert.issuer.native
    return {
        "subject_cn": (subject.get("common_name") or "")[:255] or None,
        "organization": (subject.get("organization_name") or "")[:255] or None,
        "issuer_cn": (issuer.get("common_name") or issuer.get("organization_name") or "")[:255] or None,
        "serial_hex": format(cert.serial_number, "X")[:130],
        "fingerprint_sha256": hashlib.sha256(cert.dump()).hexdigest(),
        "self_signed": cert.self_signed != "no",
        "valid_from": validity["not_before"].native,
        "valid_to": validity["not_after"].native,
    }


def to_dict(cert: UserCertificate) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    valid_to = cert.valid_to if cert.valid_to.tzinfo else cert.valid_to.replace(tzinfo=dt.timezone.utc)
    return {
        "id": cert.id,
        "label": cert.label,
        "subject_cn": cert.subject_cn,
        "organization": cert.organization,
        "issuer_cn": cert.issuer_cn,
        "serial": cert.serial_hex,
        "fingerprint_sha256": cert.fingerprint_sha256,
        "self_signed": cert.self_signed,
        "valid_from": cert.valid_from.isoformat() if cert.valid_from else None,
        "valid_to": valid_to.isoformat(),
        "expired": valid_to <= now,
        "days_left": max(0, (valid_to - now).days),
        "created_at": cert.created_at.isoformat() if cert.created_at else None,
        "last_used_at": cert.last_used_at.isoformat() if cert.last_used_at else None,
        "passkeys": [_binding_dict(b) for b in cert.passkey_bindings],
    }


def _binding_dict(b: CertificatePasskey) -> dict:
    from app.services import passkey_service

    return {
        "id": b.id,
        "passkey_id": b.passkey_id,
        "name": b.passkey.name if b.passkey else "Passkey",
        "credential_id": b.passkey.credential_id if b.passkey else None,
        "transports": [t for t in ((b.passkey.transports or "") if b.passkey else "").split(",") if t],
        "rp_id": passkey_service.rp_id(),
        "prf_salt": b.prf_salt,
        "wrapped": b.wrapped,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


def list_for(db: Session, user: User) -> list[dict]:
    rows = (db.query(UserCertificate).filter(UserCertificate.user_id == user.id)
            .order_by(UserCertificate.created_at.desc(), UserCertificate.id.desc()).all())
    return [to_dict(r) for r in rows]


def add(db: Session, user: User, pfx_bytes: bytes, password: str, label: Optional[str] = None) -> dict:
    if not pfx_bytes:
        raise CertificateError("ไม่พบไฟล์ใบรับรอง")
    if len(pfx_bytes) > MAX_FILE_BYTES:
        raise CertificateError("ไฟล์ใบรับรองใหญ่เกินไป (สูงสุด 1 MB)", 413)
    if not password:
        raise CertificateError("กรอกรหัสผ่านของใบรับรองเพื่อยืนยันก่อนบันทึก")
    if db.query(UserCertificate).filter(UserCertificate.user_id == user.id).count() >= MAX_PER_USER:
        raise CertificateError(f"เก็บใบรับรองได้สูงสุด {MAX_PER_USER} ใบ — ลบใบที่ไม่ใช้แล้วก่อน")
    signer, _info = _open(pfx_bytes, password)
    meta = _metadata(signer)
    dup = (db.query(UserCertificate)
           .filter(UserCertificate.user_id == user.id, UserCertificate.fingerprint_sha256 == meta["fingerprint_sha256"])
           .first())
    if dup:
        raise CertificateError(f"ใบรับรองนี้บันทึกไว้แล้ว (“{dup.label}”)", 409)
    name = (label or "").strip()[:100] or meta["subject_cn"] or "ใบรับรองของฉัน"
    cert = UserCertificate(user_id=user.id, label=name, pfx_encrypted=_seal(pfx_bytes), **meta)
    db.add(cert)
    db.commit()
    db.refresh(cert)
    logger.info("ผู้ใช้ %s บันทึกใบรับรอง %s (fp %s…)", user.id, cert.id, meta["fingerprint_sha256"][:12])
    return to_dict(cert)


def _get(db: Session, user: User, cert_id: int) -> UserCertificate:
    cert = (db.query(UserCertificate)
            .filter(UserCertificate.id == cert_id, UserCertificate.user_id == user.id).first())
    if cert is None:
        raise CertificateError("ไม่พบใบรับรองนี้", 404)
    return cert


def _password_ok(pfx_bytes: bytes, password: str) -> bool:
    """แค่ตรวจว่ารหัสเปิดกุญแจได้ (ไม่โหลด chain จากอินเทอร์เน็ตแบบตอนเซ็น) — การตรวจวันหมดอายุ/สิทธิ์ลงนามทำตอนเซ็นอยู่แล้ว"""
    from cryptography.hazmat.primitives.serialization import pkcs12

    try:
        key, _cert, _extra = pkcs12.load_key_and_certificates(pfx_bytes, password.encode("utf-8"))
    except (ValueError, TypeError):
        return False
    return key is not None


def unlock(db: Session, user: User, cert_id: int, password: str, *, mark_used: bool = True) -> bytes:
    """ตรวจรหัสของใบรับรองที่เก็บไว้ — ถูก: คืนไบต์ p12 (ไว้ส่งต่อให้ขั้นตอนเซ็นเดิม) · ผิด: นับครั้งผิด"""
    ident = str(user.id)
    ratelimit.ensure_below(_RL_NAME, ident, WRONG_PASSWORD_MAX, _LOCKED_MSG)
    cert = _get(db, user, cert_id)
    pfx_bytes = _unseal(cert.pfx_encrypted)
    if not _password_ok(pfx_bytes, password or ""):
        ratelimit.hit(_RL_NAME, ident, WRONG_PASSWORD_WINDOW)
        raise CertificateError("รหัสผ่านของใบรับรองไม่ถูกต้อง")
    ratelimit.reset(_RL_NAME, ident)  # ถูกแล้วล้างตัวนับ — พิมพ์ผิดบ้างตลอดวันไม่ถูกล็อก (ล็อกเฉพาะผิดติดกัน)
    if mark_used:
        cert.last_used_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
    return pfx_bytes


def delete(db: Session, user: User, cert_id: int, password: str) -> None:
    unlock(db, user, cert_id, password, mark_used=False)
    db.delete(_get(db, user, cert_id))  # ลบการผูก passkey ไปด้วย (relationship cascade)
    db.commit()
    logger.info("ผู้ใช้ %s ลบใบรับรอง %s", user.id, cert_id)


# ---------- ปลดล็อกด้วย passkey (WebAuthn PRF) ----------

MAX_PASSKEYS_PER_CERT = 10
_PASSKEY_PURPOSE = "cert-passkey"


def _b64url_bytes(value: str, field: str, lo: int, hi: int) -> bytes:
    from webauthn.helpers import base64url_to_bytes

    try:
        raw = base64url_to_bytes(value or "")
    except (ValueError, TypeError):
        raw = b""
    if not (lo <= len(raw) <= hi):
        raise CertificateError(f"ข้อมูล {field} ไม่ถูกต้อง")
    return raw


def passkey_options(db: Session, user: User, cert_id: int) -> dict:
    """challenge สำหรับยืนยัน passkey ตอนผูกกับใบรับรอง (จำกัดเฉพาะ passkey ของบัญชีนี้)"""
    from app.services import passkey_service

    _get(db, user, cert_id)
    try:
        return passkey_service.authentication_options(db, user, purpose=_PASSKEY_PURPOSE)
    except passkey_service.PasskeyError as exc:
        raise CertificateError(str(exc)) from None


def bind_passkey(db: Session, user: User, cert_id: int, *, password: str, flow_id: str, credential: dict,
                 prf_salt: str, wrapped: str) -> dict:
    """ผูก passkey กับใบรับรอง: ยืนยัน passkey (สแกนตอนนี้) + ตรวจรหัสของใบรับรองว่าถูก แล้วเก็บรหัสที่เข้ารหัสในเครื่องแล้ว"""
    from app.services import passkey_service

    cert = _get(db, user, cert_id)
    _b64url_bytes(prf_salt, "prf_salt", 32, 32)
    _b64url_bytes(wrapped, "wrapped", 12 + 16 + 1, 12 + 16 + 256)  # IV + tag + รหัส ≤ 256 ไบต์
    try:
        passkey = passkey_service.verify_for_user(db, user, _PASSKEY_PURPOSE, flow_id, credential)
    except passkey_service.PasskeyError as exc:
        db.rollback()
        raise CertificateError(str(exc)) from None
    unlock(db, user, cert_id, password, mark_used=False)  # รหัสผิด = ไม่ผูก (นับครั้งผิดเหมือนเดิม)
    binding = next((b for b in cert.passkey_bindings if b.passkey_id == passkey.id), None)
    if binding is None:
        if len(cert.passkey_bindings) >= MAX_PASSKEYS_PER_CERT:
            raise CertificateError(f"ผูก passkey กับใบรับรองนี้ได้สูงสุด {MAX_PASSKEYS_PER_CERT} อัน")
        binding = CertificatePasskey(certificate_id=cert.id, passkey_id=passkey.id)
        cert.passkey_bindings.append(binding)
    binding.prf_salt = prf_salt
    binding.wrapped = wrapped
    db.commit()  # รวมตัวนับของ passkey ที่ verify_for_user อัปเดตไว้
    db.refresh(cert)
    logger.info("ผู้ใช้ %s ผูก passkey %s กับใบรับรอง %s", user.id, passkey.id, cert.id)
    return to_dict(cert)


def unbind_passkey(db: Session, user: User, cert_id: int, binding_id: int) -> dict:
    """เลิกใช้ passkey กับใบรับรองนี้ (กลับไปพิมพ์รหัส) — ไม่ต้องยืนยันรหัส เพราะไม่ได้เพิ่มสิทธิ์อะไร"""
    cert = _get(db, user, cert_id)
    binding = next((b for b in cert.passkey_bindings if b.id == binding_id), None)
    if binding is None:
        raise CertificateError("ไม่พบ passkey ที่ผูกกับใบรับรองนี้", 404)
    cert.passkey_bindings.remove(binding)
    db.commit()
    db.refresh(cert)
    return to_dict(cert)
