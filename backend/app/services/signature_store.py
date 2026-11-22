"""signature_store — เก็บรูปลายเซ็นของผู้ใช้แบบ Zero-Knowledge ล็อกด้วย Passkey (WebAuthn PRF, v1.48.0)

เบราว์เซอร์เข้ารหัสไฟล์ PNG ของลายเซ็นด้วย AES-GCM จากค่าลับของ Passkey (WebAuthn PRF) ก่อนส่งมาเก็บ
เซิร์ฟเวอร์เก็บเฉพาะ ciphertext + prf_salt + passkey_id (ไม่เคยเห็นรูปลายเซ็นจริง)
"""
from __future__ import annotations

import base64
import binascii

from sqlalchemy.orm import Session

from app.models.domain import User, UserSignature
from app.services import passkey_service

MAX_SIGNATURES_PER_USER = 5
MAX_ENCRYPTED_BYTES = 1024 * 1024  # 1 MB
LABEL_MAX = 100
_PASSKEY_PURPOSE = "saved-sig"


class SignatureStoreError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _b64url_ok(value: str, min_len: int, max_len: int) -> bool:
    if not value or not (min_len <= len(value) <= max_len):
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")
    return all(ch in allowed for ch in value)


def _to_dict(row: UserSignature) -> dict:
    pk = row.passkey
    transports = [t for t in (pk.transports or "").split(",") if t] if pk else []
    return {
        "id": row.id,
        "label": row.label,
        "passkey_id": row.passkey_id,
        "passkey_name": pk.name if pk else "Passkey",
        "credential_id": pk.credential_id if pk else "",
        "transports": transports,
        "rp_id": passkey_service.rp_id(),
        "prf_salt": row.prf_salt,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_for(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(UserSignature)
        .filter(UserSignature.user_id == user.id)
        .order_by(UserSignature.id.asc())
        .all()
    )
    return [_to_dict(r) for r in rows]


def get_blob(db: Session, user: User, sig_id: int) -> dict:
    row = (
        db.query(UserSignature)
        .filter(UserSignature.id == sig_id, UserSignature.user_id == user.id)
        .first()
    )
    if not row:
        raise SignatureStoreError("ไม่พบรูปลายเซ็นที่บันทึกไว้", status_code=404)
    return {
        **_to_dict(row),
        "encrypted_png_b64": base64.b64encode(row.encrypted_png).decode("ascii"),
    }


def save_options(db: Session, user: User) -> dict:
    try:
        return passkey_service.authentication_options(db, user, purpose=_PASSKEY_PURPOSE)
    except passkey_service.PasskeyError as exc:
        raise SignatureStoreError(str(exc), status_code=400) from exc


def add(
    db: Session,
    user: User,
    *,
    label: str,
    prf_salt: str,
    encrypted_png_b64: str,
    flow_id: str,
    credential: dict,
) -> dict:
    existing_count = db.query(UserSignature).filter(UserSignature.user_id == user.id).count()
    if existing_count >= MAX_SIGNATURES_PER_USER:
        raise SignatureStoreError(f"บันทึกรูปลายเซ็นได้สูงสุด {MAX_SIGNATURES_PER_USER} อัน กรุณาลบอันที่ไม่ใช้ก่อน")

    clean_label = " ".join((label or "").split())[:LABEL_MAX] or f"ลายเซ็น {existing_count + 1}"
    if not _b64url_ok(prf_salt, 16, 64):
        raise SignatureStoreError("ค่า prf_salt ไม่ถูกต้อง")

    try:
        enc_bytes = base64.b64decode(encrypted_png_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SignatureStoreError("ข้อมูลรูปลายเซ็นที่เข้ารหัสไม่ถูกต้อง") from exc

    if len(enc_bytes) < 28 or len(enc_bytes) > MAX_ENCRYPTED_BYTES:
        raise SignatureStoreError("ขนาดรูปลายเซ็นไม่ถูกต้อง (สูงสุด 1 MB)")

    try:
        pk = passkey_service.verify_for_user(db, user, _PASSKEY_PURPOSE, flow_id, credential)
    except passkey_service.PasskeyError as exc:
        raise SignatureStoreError(str(exc), status_code=400) from exc

    row = UserSignature(
        user_id=user.id,
        passkey_id=pk.id,
        label=clean_label,
        prf_salt=prf_salt,
        encrypted_png=enc_bytes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


def delete(db: Session, user: User, sig_id: int) -> None:
    row = (
        db.query(UserSignature)
        .filter(UserSignature.id == sig_id, UserSignature.user_id == user.id)
        .first()
    )
    if not row:
        raise SignatureStoreError("ไม่พบรูปลายเซ็นที่ต้องการลบ", status_code=404)
    db.delete(row)
    db.commit()
