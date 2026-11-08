from datetime import timedelta

import pytest


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_login_and_me(client, make_user):
    uid, headers = make_user()
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200 and r.json()["id"] == uid


@pytest.mark.parametrize("sub", ["verify:user@example.com", "reset:user@example.com"])
def test_email_tokens_cannot_be_used_as_access_token(client, sub):
    from app.core.security import create_access_token

    token = create_access_token({"sub": sub, "jti": "x"}, expires_delta=timedelta(hours=1))
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_without_jti_is_rejected(client, make_user):
    from app.core.security import create_access_token

    uid, _ = make_user()
    token = create_access_token({"sub": str(uid)}, expires_delta=timedelta(hours=1))
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_signed_with_legacy_default_secret_is_rejected(client, make_user):
    from jose import jwt

    from app.core.security import LEGACY_DEFAULT_SECRET

    uid, _ = make_user()
    forged = jwt.encode({"sub": str(uid), "jti": "x"}, LEGACY_DEFAULT_SECRET, algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_validate_secret_config_in_production(monkeypatch):
    from app.core import security

    monkeypatch.setattr(security, "_IS_PRODUCTION", True)
    for bad in ("", security.LEGACY_DEFAULT_SECRET, "short"):
        monkeypatch.setattr(security, "_configured_secret", bad)
        with pytest.raises(RuntimeError):
            security.validate_secret_config()
    monkeypatch.setattr(security, "_configured_secret", "y" * 48)
    security.validate_secret_config()


def test_gemini_key_encrypted_with_legacy_secret_still_decrypts():
    from types import SimpleNamespace

    from cryptography.fernet import Fernet

    from app.core import crypto

    user = SimpleNamespace(hashed_password="$2b$12$abcdefghijklmnopqrstuv")
    legacy = Fernet(crypto._get_user_derived_key(user, crypto.LEGACY_DEFAULT_SECRET)).encrypt(b"AIza-legacy").decode()
    assert crypto.decrypt_api_key(legacy, user) == "AIza-legacy"
    fresh = crypto.encrypt_api_key("AIza-new", user)
    assert crypto.decrypt_api_key(fresh, user) == "AIza-new"


def test_reset_password_also_verifies_email(client):
    """เปิดลิงก์รีเซ็ตจากอีเมลได้ = เป็นเจ้าของอีเมล → login ได้ทันทีแม้ยังไม่เคยกดลิงก์ยืนยัน"""
    from datetime import timedelta

    from app.core.security import create_access_token, get_password_hash
    from app.db.database import SessionLocal
    from app.models.domain import User

    db = SessionLocal()
    try:
        user = User(email="unverified-reset@example.com", hashed_password=get_password_hash("Old-Passw0rd!"),
                    is_verified=False, is_active=True, plan_type="free", accepted_tos=True)
        db.add(user)
        db.commit()
        uid = user.id
    finally:
        db.close()

    r = client.post("/auth/login", data={"username": "unverified-reset@example.com", "password": "Old-Passw0rd!"})
    assert r.status_code == 401 and "ยืนยันอีเมล" in r.json()["detail"]

    from app.api.routes_auth import _password_version

    db = SessionLocal()
    try:
        pwv = _password_version(db.get(User, uid))  # ลิงก์รีเซ็ตผูกกับรหัสผ่านปัจจุบัน (ใช้ครั้งเดียว)
    finally:
        db.close()
    token = create_access_token({"sub": str(uid), "type": "reset", "pwv": pwv}, expires_delta=timedelta(minutes=15))
    r = client.post("/auth/reset-password", json={"token": token, "new_password": "New-Passw0rd!"})
    assert r.status_code == 200, r.text
    r = client.post("/auth/login", data={"username": "unverified-reset@example.com", "password": "New-Passw0rd!"})
    assert r.status_code == 200, r.text
