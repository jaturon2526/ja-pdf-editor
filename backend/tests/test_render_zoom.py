"""ซูมที่ใช้เรนเดอร์หน้า: frontend ขอละเอียดตามจอ (×2) — backend จำกัดซูม/จำนวนพิกเซล กันหน่วยความจำล้น"""
import base64
import io

import fitz
from PIL import Image

from app.services.pdf_service.core import MAX_RENDER_PIXELS, _safe_render_zoom


def test_safe_render_zoom_bounds():
    doc = fitz.open()
    a4 = doc.new_page(width=595, height=842)
    assert _safe_render_zoom(a4, 3) == 3
    assert _safe_render_zoom(a4, 100) == 8.0
    assert _safe_render_zoom(a4, -1) == 0.05
    assert _safe_render_zoom(a4, float("nan")) == 1.5
    big = doc.new_page(width=3370, height=2384)  # A0
    z = _safe_render_zoom(big, 8)
    assert 3370 * 2384 * z * z <= MAX_RENDER_PIXELS * 1.0001


def test_render_endpoint_caps_huge_zoom(client, make_user, upload):
    _, h = make_user()
    sid = upload(h)
    r = client.get(f"/pdf/{sid}/page/0?zoom=1000", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    img = Image.open(io.BytesIO(base64.b64decode(body["image_base64"])))
    assert img.width <= body["width"] * 8 + 1
