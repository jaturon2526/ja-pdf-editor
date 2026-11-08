"""ภาพหน้าเอกสาร: JPEG (เร็วกว่า PNG มาก) + cache ตามรุ่นเอกสาร — แก้ไข/undo แล้วไม่ได้ภาพเก่า · หลาย worker (Redis) ใช้ cache ร่วมกัน"""
import base64

import fitz
import pytest
from PIL import Image

from app.services import pdf_service, render_cache
from tests.test_redis_sessions import _new_session, _rotate, pods  # noqa: F401


@pytest.fixture
def encode_count(monkeypatch):
    n = {"save": 0}
    orig = Image.Image.save

    def counting(self, fp, format=None, **kw):
        if format == "JPEG":
            n["save"] += 1
        return orig(self, fp, format, **kw)

    monkeypatch.setattr(Image.Image, "save", counting)
    return n


def test_api_returns_jpeg_and_png_on_request(client, make_user, upload):
    _, h = make_user()
    sid = upload(h)
    r = client.get(f"/pdf/{sid}/page/0?zoom=1", headers=h).json()
    assert r["image_mime"] == "image/jpeg" and base64.b64decode(r["image_base64"])[:3] == b"\xff\xd8\xff"
    p = client.get(f"/pdf/{sid}/page/0?zoom=1&fmt=png", headers=h).json()
    assert p["image_mime"] == "image/png" and base64.b64decode(p["image_base64"])[:4] == b"\x89PNG"


def test_cache_hits_and_invalidates_on_edit_and_undo(client, make_user, upload, encode_count):
    _, h = make_user()
    sid = upload(h)
    get = lambda: client.get(f"/pdf/{sid}/page/0?zoom=1", headers=h).json()["image_base64"]  # noqa: E731
    first = get()
    assert get() == first and encode_count["save"] == 1           # ครั้งที่ 2 มาจาก cache
    r = client.post(f"/annotation/{sid}", headers=h, json={
        "page_number": 0, "type": "rect", "rect": {"x0": 50, "y0": 50, "x1": 300, "y1": 300}, "color": [1, 0, 0]})
    assert r.status_code == 200
    edited = get()
    assert edited != first and encode_count["save"] == 2           # แก้ไขแล้วเรนเดอร์ใหม่
    assert client.post(f"/pdf/{sid}/undo", headers=h).status_code == 200
    assert get() != edited                                          # undo แล้วไม่ได้ภาพที่มีกรอบแดง


def test_redis_workers_share_cache_and_see_edits(pods, monkeypatch, encode_count):  # noqa: F811
    a, b = pods
    s_a = _new_session(a)
    monkeypatch.setattr("app.core.session.session_manager", a)
    with s_a.lock:
        img1, _, _ = pdf_service.render_page_image(s_a, 0, 1.0)
    s_b = b.get(s_a.session_id)
    monkeypatch.setattr("app.core.session.session_manager", b)
    with s_b.lock:
        img_b, _, _ = pdf_service.render_page_image(s_b, 0, 1.0)
    assert img_b == img1 and encode_count["save"] == 1              # worker b ใช้ภาพที่ worker a เรนเดอร์
    monkeypatch.setattr("app.core.session.session_manager", a)
    _rotate(s_a, 90)
    monkeypatch.setattr("app.core.session.session_manager", b)
    with s_b.lock:
        img_b2, w, h = pdf_service.render_page_image(s_b, 0, 1.0)
    assert img_b2 != img1 and w > h                                 # เห็นการหมุนจาก worker a
    assert render_cache.key_for(s_b, 0, 1.0, "jpeg").startswith(f"render:{s_b.session_id}:")
