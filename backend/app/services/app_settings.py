"""ค่าตั้งที่แอดมินแก้ได้ในหน้าเว็บ (ตาราง app_settings: key → JSON) — ไม่ต้องแก้ .env หรือ restart

ใช้กับข้อมูลที่ไม่ควรอยู่ในซอร์ส/.env เช่น เลขพร้อมเพย์สำหรับรับบริจาค (ตั้งโดยแอดมินของแต่ละเครื่อง)
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import AppSetting


def get(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return default


def put(db: Session, key: str, value: Any) -> None:
    raw = json.dumps(value, ensure_ascii=False)
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=raw))
    else:
        row.value = raw


def _fernet():
    import base64
    import hashlib

    from cryptography.fernet import Fernet

    from app.core.security import SECRET_KEY

    key = hashlib.sha256(("app-settings:" + SECRET_KEY).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(value: str) -> str:
    """เข้ารหัสค่าลับระดับระบบ (เช่น API key ของบริการตรวจสลิป) ด้วยคีย์ที่ได้จาก JWT_SECRET ก่อนเก็บใน app_settings"""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:  # noqa: BLE001 — JWT_SECRET เปลี่ยน = ต้องตั้ง key ใหม่
        return ""
