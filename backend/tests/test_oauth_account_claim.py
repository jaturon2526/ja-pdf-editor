"""SEC-01/02: กันยึดบัญชีล่วงหน้าผ่าน Google/LINE Login และไม่รับอีเมล Google ที่ยังไม่ยืนยัน

สถานการณ์: ผู้โจมตีสมัครด้วยอีเมลของเหยื่อ + ตั้งรหัสผ่านเอง (ยังไม่ยืนยันอีเมล) → เหยื่อเข้าระบบด้วย Google/LINE
ต้องได้: บัญชียืนยันแล้ว แต่รหัสผ่านของผู้โจมตีใช้ไม่ได้อีก
"""
import itertools

import pytest

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.database import SessionLocal
from app.models.domain import User
from app.services import line_login_service, line_service

_seq = itertools.count(1)
ATTACKER_PW = "attacker-pass-123"


def _pre_registered(email: str) -> int:
    db = SessionLocal()
    try:
        user = User(email=email, hashed_password=get_password_hash(ATTACKER_PW), is_verified=False,
                    is_active=True, accepted_tos=True)
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _user(uid: int) -> User:
    db = SessionLocal()
    try:
        return db.get(User, uid)
    finally:
        db.close()


def _password_login(client, email):
    return client.post("/auth/login", data={"username": email, "password": ATTACKER_PW})


@pytest.fixture
def google(monkeypatch):
    claims = {}
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    from app.api import routes_auth

    monkeypatch.setattr(routes_auth.id_token, "verify_oauth2_token", lambda cred, req, aud: dict(claims))
    return claims


def test_google_login_on_pre_registered_account_resets_password(client, google):
    email = f"victim{next(_seq)}@example.com"
    uid = _pre_registered(email)
    assert _password_login(client, email).status_code != 200  # ยังไม่ยืนยัน → login ไม่ได้

    google.update(email=email, email_verified=True, name="Victim")
    r = client.post("/auth/google", json={"credential": "x"})
    assert r.status_code == 200, r.text
    assert _user(uid).is_verified
    assert _password_login(client, email).status_code == 401  # รหัสผ่านของผู้โจมตีใช้ไม่ได้แล้ว


def test_google_login_keeps_password_of_verified_account(client, google, make_user):
    uid, _ = make_user()
    email = _user(uid).email
    google.update(email=email, email_verified=True)
    assert client.post("/auth/google", json={"credential": "x"}).status_code == 200
    r = client.post("/auth/login", data={"username": email, "password": "password123"})
    assert r.status_code == 200  # บัญชีที่ยืนยันแล้ว ไม่แตะรหัสผ่าน


@pytest.mark.parametrize("flag", [False, None, "true"])
def test_google_unverified_email_is_rejected(client, google, flag):
    email = f"unverified{next(_seq)}@example.com"
    google.update(email=email)
    if flag is not None:
        google["email_verified"] = flag
    r = client.post("/auth/google", json={"credential": "x"})
    assert r.status_code == 400 and "ยืนยัน" in r.json()["detail"]
    db = SessionLocal()
    try:
        assert db.query(User).filter_by(email=email).first() is None
    finally:
        db.close()


def test_line_login_on_pre_registered_account_resets_password(client, monkeypatch):
    from tests.test_line_login import FakeLineLogin, _flow

    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_ID", "2000000000")
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_SECRET", "c" * 32)
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", "")
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
    fake = FakeLineLogin()
    monkeypatch.setattr(line_login_service, "call", fake)
    line_service.reset_for_testing()

    email = f"linevictim{next(_seq)}@example.com"
    uid = _pre_registered(email)
    _, r = _flow(client, fake, email=email)
    assert r.status_code == 200 and r.json()["status"] == "login", r.text
    user = _user(uid)
    assert user.is_verified and user.line_login_id
    assert _password_login(client, email).status_code == 401
    line_service.reset_for_testing()
