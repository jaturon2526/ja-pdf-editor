import os
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt

import logging
import secrets

logger = logging.getLogger("security")

# ค่า default เดิมที่เคยฮาร์ดโค้ดไว้ — เก็บไว้เพื่อ (1) ตรวจจับว่ายังใช้ค่านี้อยู่หรือไม่ และ (2) ถอดรหัส
# Gemini API key ที่เคยเข้ารหัสด้วยค่านี้ไว้ก่อนหน้า (ดู app/core/crypto.py) ห้ามใช้เซ็น token ใหม่
LEGACY_DEFAULT_SECRET = "super-secret-key-for-pdf-editor"

# อ่านได้ทั้ง JWT_SECRET และ SECRET_KEY (.env.prod ใช้ชื่อ SECRET_KEY มาตลอด แต่โค้ดเดิมอ่านแค่
# JWT_SECRET ทำให้ production ใช้ค่า default ที่ฮาร์ดโค้ดอยู่โดยไม่รู้ตัว)
_configured_secret = os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY") or ""
_IS_PRODUCTION = os.environ.get("APP_ENV", "").lower() in ("prod", "production")

if _configured_secret and _configured_secret != LEGACY_DEFAULT_SECRET:
    SECRET_KEY = _configured_secret
else:
    # dev: สุ่มค่าใหม่ทุกครั้งที่ start (token เก่าจะใช้ไม่ได้หลังรีสตาร์ท) — production จะไม่ยอม start
    # (ดู validate_secret_config) เพื่อกันการ deploy โดยไม่ได้ตั้งค่า secret
    SECRET_KEY = secrets.token_urlsafe(48)

ALGORITHM = os.environ.get("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))  # ดีฟอลต์ 7 วัน


def validate_secret_config() -> None:
    """เรียกตอน start แอป — production ต้องตั้ง JWT_SECRET/SECRET_KEY ที่ยาวพอและไม่ใช่ค่า default"""
    problem = None
    if not _configured_secret:
        problem = "ไม่ได้ตั้งค่า JWT_SECRET (หรือ SECRET_KEY)"
    elif _configured_secret == LEGACY_DEFAULT_SECRET:
        problem = "JWT_SECRET ยังเป็นค่า default ที่เปิดเผยอยู่ในซอร์สโค้ด"
    elif len(_configured_secret) < 32:
        problem = "JWT_SECRET สั้นเกินไป (ควรยาวอย่างน้อย 32 ตัวอักษร)"
    if problem is None:
        return
    if _IS_PRODUCTION:
        raise RuntimeError(f"{problem} — สร้างค่าใหม่ด้วย: python -c 'import secrets; print(secrets.token_urlsafe(48))'")
    logger.warning("%s — ใช้ค่าสุ่มชั่วคราวแทน (dev เท่านั้น, token จะหมดอายุเมื่อรีสตาร์ท)", problem)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ---------- token สำหรับ URL ที่ใส่ Authorization header ไม่ได้ (เช่น @font-face src: url(...)) ----------
import hashlib  # noqa: E402
import hmac  # noqa: E402
import time  # noqa: E402

RESOURCE_TOKEN_TTL_SECONDS = 7 * 24 * 3600


def make_resource_token(scope: str, user_id: int, ttl: int = RESOURCE_TOKEN_TTL_SECONDS) -> str:
    """token สั้นๆ ผูกกับ scope + user_id + วันหมดอายุ (HMAC-SHA256 ด้วย SECRET_KEY)"""
    exp = int(time.time()) + ttl
    msg = f"{scope}:{user_id}:{exp}".encode()
    sig = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:32]
    return f"{user_id}.{exp}.{sig}"


def verify_resource_token(scope: str, token: str | None) -> int | None:
    """คืน user_id ถ้า token ถูกต้องและยังไม่หมดอายุ ไม่งั้นคืน None"""
    try:
        uid_s, exp_s, sig = (token or "").split(".")
        uid, exp = int(uid_s), int(exp_s)
    except ValueError:
        return None
    if exp < time.time():
        return None
    expected = hmac.new(SECRET_KEY.encode(), f"{scope}:{uid}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return uid if hmac.compare_digest(expected, sig) else None
