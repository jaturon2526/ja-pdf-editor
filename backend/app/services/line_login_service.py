"""เข้าสู่ระบบด้วย LINE (LINE Login v2.1, OpenID Connect + PKCE)

ขั้นตอน:
1. start()     สร้าง state/nonce/PKCE เก็บใน Redis 10 นาที → URL หน้าอนุญาตของ LINE (bot_prompt=aggressive ชวนเพิ่มเพื่อน OA)
2. LINE ส่งกลับมาที่ {FRONTEND_URL}/auth/line/callback?code&state → frontend เรียก complete(code, state)
3. complete()  แลก code เป็น token → ตรวจ id_token กับ LINE (/oauth2/v2.1/verify, ตรวจ nonce) → ได้ sub, ชื่อ, รูป, อีเมล(ถ้าอนุญาต)
   - sub ผูกกับบัญชีอยู่แล้ว → เข้าบัญชีนั้น
   - mode=link (กดจากหน้าความปลอดภัย) → ผูก sub กับบัญชีที่ล็อกอินอยู่
   - มีอีเมล → เข้าบัญชีที่อีเมลตรงกัน (ผูก LINE ให้) หรือสร้างบัญชีใหม่ — LINE ยืนยันอีเมลมาแล้ว เหมือน Google
   - ไม่มีอีเมล → คืน pending token ให้ผู้ใช้กรอกอีเมล → ส่งลิงก์ยืนยัน → confirm() ต้องมีทั้งรหัสในอีเมลและ pending
     token ในเบราว์เซอร์ที่เริ่ม (กันคนอื่นใช้ LINE ของตัวเองกรอกอีเมลเหยื่อแล้วหลอกให้เหยื่อกดยืนยัน)
4. ถ้าเป็นเพื่อน OA (friendship API) และเปิด Messaging API ไว้ → ผูกรับแจ้งเตือนทาง LINE ให้ด้วย (provider เดียวกัน userId ตรงกัน)

ไม่ log token/อีเมล — log แค่ผลลัพธ์และ user id
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.domain import User
from app.services import line_service

logger = logging.getLogger("line_login")

STATE_TTL = 600
PENDING_TTL = 15 * 60
CONFIRM_TTL = 30 * 60
MAX_CONFIRM_EMAILS = 3
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _grants_initial_admin(db, email):
    from app.services.account_service import grants_initial_admin

    return grants_initial_admin(db, email)


class LineLoginError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- เรียก LINE


def _http(method: str, url: str, form: Optional[dict] = None, bearer: Optional[str] = None, timeout: int = 10) -> dict:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    headers = {"Content-Type": "application/x-www-form-urlencoded"} if form is not None else {}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL มาจาก config
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = json.loads(exc.read() or b"{}")
            detail = body.get("error_description") or body.get("error") or body.get("message") or ""
        except Exception:
            pass
        raise line_service.LineApiError(exc.code, detail) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise line_service.LineApiError(0, str(exc)) from None
    return json.loads(raw) if raw else {}


# เทสต์แทนที่ตัวนี้เพื่อจำลอง LINE
call: Callable[..., dict] = _http


def _api(path: str) -> str:
    return f"{settings.LINE_API_BASE.rstrip('/')}{path}"


def redirect_uri() -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/line/callback"


# ---------------------------------------------------------------- เก็บชั่วคราว (Redis ผ่าน line_service)


def _put(key: str, data: dict, ttl: int) -> None:
    line_service._set(f"login:{key}", json.dumps(data).encode(), ttl)


def _take(key: str) -> Optional[dict]:
    raw = line_service._pop(f"login:{key}")
    return json.loads(raw) if raw else None


def _token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------- 1. เริ่ม


def start(mode: str = "login", user: Optional[User] = None) -> dict:
    if not settings.line_login_enabled:
        raise LineLoginError("ระบบยังไม่ได้เปิดใช้การเข้าสู่ระบบด้วย LINE", 503)
    state, nonce, verifier = _token(), _token(), secrets.token_urlsafe(48)
    _put(f"state:{state}", {"mode": mode, "user_id": user.id if user else None, "nonce": nonce,
                            "verifier": verifier}, STATE_TTL)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = {
        "response_type": "code",
        "client_id": settings.LINE_LOGIN_CHANNEL_ID,
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": "profile openid email",
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "ui_locales": "th-TH",
    }
    if settings.line_enabled:  # มี OA ให้เพิ่มเพื่อน (ต้องผูก OA กับ LINE Login channel ใน console)
        params["bot_prompt"] = "aggressive"
    return {"url": f"{settings.LINE_LOGIN_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}", "state": state}


# ---------------------------------------------------------------- 2. กลับจาก LINE


def _exchange(code: str, ctx: dict) -> dict:
    try:
        token = call("POST", _api("/oauth2/v2.1/token"), form={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
            "client_id": settings.LINE_LOGIN_CHANNEL_ID, "client_secret": settings.LINE_LOGIN_CHANNEL_SECRET,
            "code_verifier": ctx["verifier"]})
        claims = call("POST", _api("/oauth2/v2.1/verify"), form={
            "id_token": token.get("id_token", ""), "client_id": settings.LINE_LOGIN_CHANNEL_ID,
            "nonce": ctx["nonce"]})
    except line_service.LineApiError as exc:
        logger.warning("LINE Login แลก token/ตรวจ id_token ไม่สำเร็จ: %s", exc)
        raise LineLoginError("เข้าสู่ระบบด้วย LINE ไม่สำเร็จ — ลองใหม่อีกครั้ง") from None
    if not claims.get("sub"):
        raise LineLoginError("เข้าสู่ระบบด้วย LINE ไม่สำเร็จ — ไม่ได้รับข้อมูลบัญชี")
    friend = False
    if token.get("access_token"):
        try:
            friend = bool(call("GET", _api("/friendship/v1/status"), bearer=token["access_token"]).get("friendFlag"))
        except line_service.LineApiError as exc:
            logger.info("อ่านสถานะเพื่อน OA ไม่สำเร็จ: %s", exc)
    email = (claims.get("email") or "").strip()
    return {"sub": claims["sub"], "name": claims.get("name") or "", "picture": claims.get("picture"),
            "email": email if _EMAIL_RE.match(email) else "", "friend": friend}


def _attach_notifications(db: Session, user: User, info: dict) -> None:
    """เป็นเพื่อน OA แล้ว → ส่งแจ้งเตือนทาง LINE ได้ทันที ไม่ต้องผูกด้วยรหัส"""
    if not (info.get("friend") and settings.line_enabled) or user.line_user_id == info["sub"]:
        return
    try:
        line_service.link(db, user, info["sub"])
        logger.info("ผูกแจ้งเตือน LINE ให้ผู้ใช้ %s จาก LINE Login", user.id)
    except Exception:
        db.rollback()
        logger.exception("ผูกแจ้งเตือน LINE จาก LINE Login ไม่สำเร็จ")


def _set_login_id(db: Session, user: User, sub: str) -> None:
    other = db.query(User).filter(User.line_login_id == sub, User.id != user.id).first()
    if other is not None:
        raise LineLoginError("บัญชี LINE นี้ใช้เข้าสู่ระบบบัญชีอื่นอยู่แล้ว — ยกเลิกที่บัญชีนั้นก่อน", 409)
    user.line_login_id = sub


def _login_user(db: Session, info: dict, email: str) -> User:
    """หา/สร้างบัญชีจาก LINE (email ต้องยืนยันแล้ว — จาก LINE หรือจากลิงก์ในอีเมล)"""
    user = db.query(User).filter(User.line_login_id == info["sub"]).first()
    if user is None:
        user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
        if user is None:
            from app.services.account_service import SignupNotAllowed, check_new_account

            try:
                check_new_account(db, email)
            except SignupNotAllowed as exc:
                raise LineLoginError(str(exc), 403) from None
            user = User(
                email=email,
                display_name=info.get("name") or None,
                profile_picture=info.get("picture"),
                # ไม่มีรหัสผ่าน — สุ่มค่าที่เดาไม่ได้ (อยากใช้รหัสผ่านให้กด "ลืมรหัสผ่าน")
                hashed_password=get_password_hash(secrets.token_urlsafe(32)),
                is_verified=True,
                is_admin=_grants_initial_admin(db, email),
                line_login_id=info["sub"],
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("สร้างบัญชีใหม่ %s จาก LINE Login", user.id)
        else:
            if not user.is_active:
                raise LineLoginError("บัญชีนี้ถูกระงับโดยผู้ดูแลระบบ", 403)
            user.line_login_id = info["sub"]
            user.is_verified = True
            if not user.profile_picture and info.get("picture"):
                user.profile_picture = info["picture"]
            db.commit()
            logger.info("ผูก LINE Login กับบัญชีเดิม %s (อีเมลตรงกัน)", user.id)
    if not user.is_active:
        raise LineLoginError("บัญชีนี้ถูกระงับโดยผู้ดูแลระบบ", 403)
    _attach_notifications(db, user, info)
    return user


def complete(db: Session, code: str, state: str) -> dict:
    """คืน {"status": "login", "user": User} | {"status": "linked"} | {"status": "need_email", "pending", "name"}"""
    if not settings.line_login_enabled:
        raise LineLoginError("ระบบยังไม่ได้เปิดใช้การเข้าสู่ระบบด้วย LINE", 503)
    ctx = _take(f"state:{state}") if state else None
    if ctx is None or not code:
        raise LineLoginError("ลิงก์เข้าสู่ระบบหมดอายุหรือถูกใช้แล้ว — กดเข้าสู่ระบบด้วย LINE ใหม่อีกครั้ง")
    info = _exchange(code, ctx)

    if ctx.get("mode") == "link":
        user = db.get(User, ctx.get("user_id") or 0)
        if user is None or not user.is_active:
            raise LineLoginError("ไม่พบบัญชีที่ต้องการเชื่อมต่อ — เข้าสู่ระบบแล้วลองใหม่", 401)
        _set_login_id(db, user, info["sub"])
        db.commit()
        _attach_notifications(db, user, info)
        logger.info("ผู้ใช้ %s เชื่อม LINE Login จากหน้าความปลอดภัย", user.id)
        return {"status": "linked"}

    existing = db.query(User).filter(User.line_login_id == info["sub"]).first()
    if existing is not None or info["email"]:
        return {"status": "login", "user": _login_user(db, info, info["email"] or existing.email)}

    pending = _token()
    _put(f"pending:{pending}", {k: info[k] for k in ("sub", "name", "picture", "friend")}, PENDING_TTL)
    return {"status": "need_email", "pending": pending, "name": info["name"]}


# ---------------------------------------------------------------- 3. ไม่มีอีเมลจาก LINE → ยืนยันอีเมลที่กรอก


def _pending_key(pending: str) -> str:
    return hashlib.sha256(pending.encode()).hexdigest()


def request_email(pending: str, email: str) -> dict:
    from app.services.email_service import send_line_login_confirm_email

    email = (email or "").strip()
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise LineLoginError("รูปแบบอีเมลไม่ถูกต้อง")
    info = _take(f"pending:{pending}") if pending else None
    if info is None:
        raise LineLoginError("หมดเวลาแล้ว — กดเข้าสู่ระบบด้วย LINE ใหม่อีกครั้ง")
    sent = line_service._incr(f"login:mails:{_pending_key(pending)}", PENDING_TTL)
    _put(f"pending:{pending}", info, PENDING_TTL)  # เก็บกลับไว้ ให้แก้อีเมล/ส่งซ้ำได้
    if sent > MAX_CONFIRM_EMAILS:
        raise LineLoginError("ส่งอีเมลยืนยันครบจำนวนแล้ว — รออีเมล หรือเริ่มเข้าสู่ระบบด้วย LINE ใหม่", 429)
    token = _token()
    _put(f"confirm:{token}", {**info, "email": email, "pending": _pending_key(pending)}, CONFIRM_TTL)
    link = f"{settings.FRONTEND_URL.rstrip('/')}/auth/line/callback?confirm={urllib.parse.quote(token)}"
    if not send_line_login_confirm_email(email, link):
        raise LineLoginError("ส่งอีเมลไม่สำเร็จ — ลองใหม่อีกครั้ง", 502)
    return {"status": "sent", "email": email}


def confirm(db: Session, token: str, pending: str) -> User:
    data = _take(f"confirm:{token}") if token else None
    if data is None:
        raise LineLoginError("ลิงก์ยืนยันหมดอายุหรือถูกใช้แล้ว — เข้าสู่ระบบด้วย LINE ใหม่อีกครั้ง")
    if not pending or not secrets.compare_digest(data["pending"], _pending_key(pending)):
        # เก็บกลับไว้ เผื่อผู้ใช้เปิดผิดเบราว์เซอร์แล้วไปเปิดในเบราว์เซอร์ที่ถูก
        _put(f"confirm:{token}", data, CONFIRM_TTL)
        raise LineLoginError("ต้องเปิดลิงก์ยืนยันในเบราว์เซอร์เดียวกับที่กดเข้าสู่ระบบด้วย LINE", 403)
    line_service._pop(f"login:pending:{pending}")
    return _login_user(db, data, data["email"])


# ---------------------------------------------------------------- ยกเลิก / สถานะ


def unlink(db: Session, user: User) -> None:
    user.line_login_id = None
    db.commit()


def status(user: User) -> dict:
    return {"enabled": settings.line_login_enabled, "linked": bool(user.line_login_id)}
