"""โควต้าแปลงไฟล์ด้วย AI ฟรีรายวัน — เก็บในฐานข้อมูล (เดิมใช้ Redis ไม่มี Redis ก็ไม่นับเลย)"""
import json

import pytest

from app.services import ai_usage, gemini_client
from tests.test_file_storage import _file_id


@pytest.fixture
def fake_gemini(monkeypatch):
    state = {"fail": False, "keys": []}

    def generate_text(api_key, model, contents):
        state["keys"].append(api_key)
        if state["fail"]:
            raise RuntimeError("boom")
        texts = json.loads(contents.split("Input JSON:\n", 1)[1])
        return json.dumps(texts, ensure_ascii=False)

    monkeypatch.setattr(gemini_client, "generate_text", generate_text)
    monkeypatch.setattr(gemini_client, "latest_flash_model", lambda key: "gemini-test")
    from app.services import convert_service
    monkeypatch.setattr(convert_service.settings, "GEMINI_API_KEY", "SYSTEM-KEY")
    monkeypatch.setattr(convert_service.settings, "AI_SYSTEM_DAILY_LIMIT", 2)
    return state


def _thai_pdf():
    import fitz
    from app.services import fonts

    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="th", fontfile=fonts.resolve_font_path("sarabun")[1])
    page.insert_text((72, 72), "สวัสดีครับ ทดสอบภาษาไทย", fontname="th", fontsize=16)
    data = doc.tobytes()
    doc.close()
    return data


def _convert(client, headers, sid):
    r = client.post("/convert/pdf-to-word/async", headers=headers, json={"file_record_id": _file_id(client, headers, sid)})
    return client.get(f"/convert/pdf-to-word/status/{r.json()['task_id']}", headers=headers).json()


def test_reserve_and_release(client):
    from app.db.database import SessionLocal

    uid = _make_plain_user()
    assert ai_usage.try_reserve(uid, "test_kind", 2)
    assert ai_usage.try_reserve(uid, "test_kind", 2)
    assert not ai_usage.try_reserve(uid, "test_kind", 2)
    ai_usage.release(uid, "test_kind")
    with SessionLocal() as db:
        assert ai_usage.get_count(db, uid, "test_kind") == 1


def _make_plain_user():
    import uuid

    from app.db.database import SessionLocal
    from app.models.domain import User

    with SessionLocal() as db:
        u = User(email=f"{uuid.uuid4().hex}@example.com", hashed_password="x", is_verified=True)
        db.add(u)
        db.commit()
        return u.id


def test_free_quota_is_counted_and_enforced(client, make_user, upload, fake_gemini):
    _, headers = make_user()
    sid = upload(headers, _thai_pdf())
    q = client.get("/auth/ai-quota", headers=headers).json()
    assert q["system_requests_today"] == 0 and q["system_daily_limit"] == 2

    assert _convert(client, headers, sid)["status"] == "completed"
    assert client.get("/auth/ai-quota", headers=headers).json()["system_requests_today"] == 1
    _convert(client, headers, sid)
    assert client.get("/auth/ai-quota", headers=headers).json()["system_requests_today"] == 2

    fake_gemini["keys"].clear()
    _convert(client, headers, sid)  # โควต้าหมด และไม่มี key ส่วนตัว → ไม่เรียก AI
    assert fake_gemini["keys"] == []
    assert client.get("/auth/ai-quota", headers=headers).json()["system_requests_today"] == 2


def test_failed_ai_does_not_use_quota(client, make_user, upload, fake_gemini):
    _, headers = make_user()
    sid = upload(headers, _thai_pdf())
    fake_gemini["fail"] = True
    _convert(client, headers, sid)
    assert fake_gemini["keys"]  # พยายามเรียก AI แล้ว
    assert client.get("/auth/ai-quota", headers=headers).json()["system_requests_today"] == 0
