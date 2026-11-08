"""บัญชีผู้ใช้: อีเมลไม่สนตัวพิมพ์, ลิงก์รีเซ็ตใช้ครั้งเดียว, เปลี่ยน/รีเซ็ตรหัสแล้วอุปกรณ์อื่นออกจากระบบ, ออกจากระบบจริง,
บัญชีถูกระงับ login ไม่ได้, ชื่อไฟล์ที่อัปโหลด, เปิดไฟล์ซ้ำไม่ทิ้งสำเนาเก่าบนดิสก์"""
import os
import time

from app.core.config import settings
from app.core.security import create_access_token
from app.models.domain import FileRecord, User
import pytest

from app.db.database import SessionLocal
from app.services import mailer
from tests.conftest import make_pdf_bytes


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def _email(client, h):
    return client.get("/auth/me", headers=h).json()["email"]


def _login(client, email, pw="password123"):
    return client.post("/auth/login", data={"username": email, "password": pw})


def test_email_case_insensitive(client, make_user):
    u, h0 = make_user()
    email = _email(client, h0)
    assert _login(client, email.upper()).status_code == 200
    r = client.post("/auth/register", json={"email": email.upper(), "password": "Another-pass1"})
    assert r.status_code == 400 and "สมัครสมาชิกแล้ว" in r.json()["detail"]


def test_reset_link_single_use_and_logs_out_everywhere(client, make_user, monkeypatch):
    from app.api import routes_auth

    links = []
    monkeypatch.setattr(routes_auth, "send_reset_password_email", lambda to, link: links.append(link) or True)
    u, h = make_user()
    email = _email(client, h)
    assert client.post("/auth/forgot-password", json={"email": email.upper()}).status_code == 200
    token = links[-1].split("token=", 1)[1]
    r = client.post("/auth/reset-password", json={"token": token, "new_password": "NewPass-123"})
    assert r.status_code == 200, r.text
    assert client.get("/auth/me", headers=h).status_code == 401  # session เดิมถูกยกเลิก
    r = client.post("/auth/reset-password", json={"token": token, "new_password": "Other-Pass-9"})
    assert r.status_code == 400 and "ใช้ตั้งรหัสผ่านไปแล้ว" in r.json()["detail"]
    assert _login(client, email, "NewPass-123").status_code == 200


def test_change_password_keeps_this_device_only(client, make_user):
    u, h = make_user()
    email = _email(client, h)
    other = {"Authorization": f"Bearer {_login(client, email).json()['access_token']}"}
    r = client.put("/auth/change-password", headers=h, json={"old_password": "password123", "new_password": "Changed-Pass1"})
    assert r.status_code == 200, r.text
    assert client.get("/auth/me", headers=h).status_code == 200
    assert client.get("/auth/me", headers=other).status_code == 401


def test_logout_revokes_token(client, make_user):
    _, h = make_user()
    assert client.post("/auth/logout", headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401


def test_deactivated_user_cannot_login(client, make_user, db_session):
    u, h0 = make_user()
    email = _email(client, h0)
    user = db_session.query(User).filter(User.email == email).first()
    user.is_active = False
    db_session.commit()
    r = _login(client, email)
    assert r.status_code == 403 and "ระงับ" in r.json()["detail"]


def test_upload_filename_cleaned(client, make_user):
    _, h = make_user()
    r = client.post("/pdf/upload", headers=h, files={"file": ("C:\\fakepath\\รายงาน: Q1?.pdf", make_pdf_bytes(), "application/pdf")})
    assert r.status_code == 200
    names = [f["filename"] for f in client.get("/pdf/files", headers=h).json()["files"]]
    assert names == ["รายงาน Q1.pdf"]


def test_reopen_removes_old_copies_and_cleanup(client, make_user, db_session):
    from app.core.session import session_manager
    from app.services import file_storage

    _, h = make_user()
    sid = client.post("/pdf/upload", headers=h, files={"file": ("a.pdf", make_pdf_bytes(), "application/pdf")}).json()["session_id"]
    assert client.post(f"/pdf/{sid}/save", headers=h).status_code == 200
    assert file_storage.upload_path(sid).exists() and file_storage.saved_path(sid).exists()
    session_manager.close(sid)  # session หมดอายุ
    files = client.get("/pdf/files", headers=h).json()["files"]
    new_sid = client.post(f"/pdf/{files[0]['session_id']}/open", headers=h).json()["session_id"]
    assert new_sid != sid
    assert not file_storage.upload_path(sid).exists() and not file_storage.saved_path(sid).exists()  # เดิมค้างตลอดไป
    assert file_storage.upload_path(new_sid).exists()

    # ไฟล์กำพร้าเก่า (ไม่มี FileRecord) ถูกเก็บกวาด — ไฟล์ที่ยังใช้อยู่/ไฟล์ใหม่ไม่ถูกแตะ
    orphan = settings.UPLOAD_DIR / ("ab" * 16 + "_saved.pdf")
    orphan.write_bytes(b"%PDF-old")
    old = time.time() - 48 * 3600
    os.utime(orphan, (old, old))
    os.utime(file_storage.upload_path(new_sid), (old, old))
    fresh = settings.UPLOAD_DIR / ("cd" * 16 + ".pdf")
    fresh.write_bytes(b"%PDF-new")
    assert file_storage.cleanup_unreferenced_files(db_session) >= 1
    assert not orphan.exists() and fresh.exists() and file_storage.upload_path(new_sid).exists()
    fresh.unlink()


def test_initial_admin_emails(client, monkeypatch):
    from app.core.config import settings
    from app.db.database import SessionLocal
    from app.services.account_service import grants_initial_admin

    monkeypatch.setattr(settings, "INITIAL_ADMIN_EMAILS", "Boss@Example.com, ops@example.com")
    db = SessionLocal()
    try:
        assert grants_initial_admin(db, "boss@example.com") is True
        assert grants_initial_admin(db, "stranger@example.com") is False  # ไม่ใช่ "คนแรก" ก็ได้สิทธิ์เฉพาะรายชื่อ
    finally:
        db.close()
    r = client.post("/auth/register", json={"email": "ops@example.com", "password": "Strong-Pass1"})
    assert r.status_code == 200 and r.json()["is_admin"] is True
    r = client.post("/auth/register", json={"email": "random-user@example.com", "password": "Strong-Pass1"})
    assert r.status_code == 200 and r.json()["is_admin"] is False


def test_make_admin_script(client):
    from scripts.make_admin import main

    client.post("/auth/register", json={"email": "promote-me@example.com", "password": "Strong-Pass1"})
    assert main("PROMOTE-ME@example.com") == 0
    assert main("nobody@example.com") == 1
