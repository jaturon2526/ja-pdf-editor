"""ตั้งค่า environment สำหรับ test ก่อน import แอป — ใช้ SQLite + โฟลเดอร์ชั่วคราว ไม่ต้องมี Postgres/Redis

รัน (จาก backend/):  pytest -q
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="pdf-editor-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["PDF_UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["PDF_WORKING_DIR"] = str(_TMP / "working")
os.environ["PDF_REDIS_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
# งานตามรอบของแอป (ตรวจโควต้าทุก 60 วินาทีหลังเริ่ม ฯลฯ) ห้ามรันระหว่าง test — เคยเรียก Brevo API ที่ test
# monkeypatch ไว้ซ้อนเข้ามาเมื่อชุด test ยาวเกิน 60 วินาที (test_brevo_api_credits_and_error ล้มแบบสุ่ม)
os.environ["PDF_BACKGROUND_JOBS"] = "0"
os.environ.pop("APP_ENV", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.services import fonts  # noqa: E402

fonts.sync_google_fonts = lambda *a, **k: None  # ไม่ออกเน็ตระหว่าง test

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # with → รัน lifespan (migration + seed)
        yield c


def make_pdf_bytes(pages: int = 2, text: str = "Hello PDF") -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} page {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_bytes():
    return make_pdf_bytes()


_counter = {"n": 0}


@pytest.fixture
def make_user(client):
    """สร้างผู้ใช้ที่ยืนยันอีเมลแล้ว + login คืน (user_id, headers)"""
    from app.core.security import get_password_hash
    from app.db.database import SessionLocal
    from app.models.domain import User

    def _make(plan: str = "premium"):
        _counter["n"] += 1
        email = f"user{_counter['n']}@example.com"
        db = SessionLocal()
        try:
            user = User(email=email, hashed_password=get_password_hash("password123"), is_verified=True,
                        is_active=True, plan_type=plan, accepted_tos=True)
            db.add(user)
            db.commit()
            db.refresh(user)
            uid = user.id
        finally:
            db.close()
        r = client.post("/auth/login", data={"username": email, "password": "password123"})
        assert r.status_code == 200, r.text
        return uid, {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make


@pytest.fixture
def upload(client):
    def _upload(headers, data: bytes = None, name: str = "doc.pdf"):
        r = client.post("/pdf/upload", headers=headers,
                        files={"file": (name, data or make_pdf_bytes(), "application/pdf")})
        assert r.status_code == 200, r.text
        return r.json()["session_id"]

    return _upload


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """ตัวนับ rate limit (app/core/ratelimit.py) อยู่ในหน่วยความจำของ process — ล้างทุกเทสต์ไม่ให้นับข้ามกัน"""
    from app.core import ratelimit

    ratelimit._mem.clear()
    yield
