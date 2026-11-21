"""ย้าย/ลบบาร์โค้ดที่มีอยู่ในหน้า (v1.41.0, edit_service/barcodes.py): ตรวจหา (เวกเตอร์ + รูปภาพ) · ย้ายแล้วยังสแกนได้
ที่ใหม่และไม่เหลือที่เดิม · ข้อความ/เส้นรอบ ๆ ไม่หาย · ลบ · undo · หน้าที่หมุน · ตรวจข้อมูล"""
import io
import shutil

import fitz
import pytest
from PIL import Image

from app.services import barcode_service as bc

zxingcpp = pytest.importorskip("zxingcpp")
pytestmark = pytest.mark.skipif(shutil.which("gs") is None, reason="ต้องมี Ghostscript")

QR_BOX = fitz.Rect(400, 60, 500, 160)
C128_BOX = fitz.Rect(60, 60, 260, 110)


def barcode_pdf() -> bytes:
    """Code 128 แบบเวกเตอร์ (มีตัวเลขใต้แท่ง) + QR แบบรูปภาพ + ข้อความ/เส้นยาวผ่านใกล้ ๆ (ข้อมูลสมมติ)"""
    doc = fitz.open()
    page = doc.new_page()
    bc.insert_into_page(page, C128_BOX, bc.validate(bc.BarcodeSpec("code128", "INV-2026-001")))
    page.insert_image(QR_BOX, stream=bc.render_png(bc.validate(bc.BarcodeSpec("qrcode", "https://example.com/doc/42"))))
    page.insert_text((60, 200), "Invoice INV-2026-001 total 1,250.00", fontsize=12)
    page.draw_line((40, 50), (560, 50), color=(0, 0, 0), width=0.75)  # เส้นยาวเหนือบาร์โค้ด ห้ามหาย
    return doc.tobytes()


def _decode(page, clip):
    png = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip, annots=False).tobytes("png")
    return [r.text for r in zxingcpp.read_barcodes(Image.open(io.BytesIO(png)))]


def _doc(client, h, sid):
    return fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)


def _list(client, h, sid):
    r = client.get(f"/edit/{sid}/page/0/barcodes", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _by_text(items, text):
    return next(b for b in items["barcodes"] if b["text"] == text)


def _shift(bbox, dx, dy):
    return {"x0": bbox["x0"] + dx, "y0": bbox["y0"] + dy, "x1": bbox["x1"] + dx, "y1": bbox["y1"] + dy}


@pytest.fixture
def bc_session(client, make_user, upload):
    _, h = make_user()
    return h, upload(h, barcode_pdf())


def test_detect_vector_and_image_barcodes(client, bc_session):
    h, sid = bc_session
    items = _list(client, h, sid)
    assert items["rotated"] is False
    c128 = _by_text(items, "INV-2026-001")
    qr = _by_text(items, "https://example.com/doc/42")
    assert c128["format"] == "Code128" and qr["format"] == "QRCode"
    r = fitz.Rect(*c128["bbox"].values())
    assert r.contains(C128_BOX + (2, 2, -2, -2))  # ครอบทั้งแท่งและตัวเลขใต้แท่ง
    assert r.y1 < 195  # ไม่กินข้อความด้านล่าง
    assert fitz.Rect(*qr["bbox"].values()).contains(QR_BOX + (1, 1, -1, -1))


def test_move_vector_barcode_keeps_surroundings_and_undo(client, bc_session):
    h, sid = bc_session
    c128 = _by_text(_list(client, h, sid), "INV-2026-001")
    target = _shift(c128["bbox"], 0, 400)
    r = client.post(f"/edit/{sid}/page/0/barcodes/edit", headers=h, json={"bbox": c128["bbox"], "target": target})
    assert r.status_code == 200, r.text
    page = _doc(client, h, sid)[0]
    assert _decode(page, fitz.Rect(*target.values()) + (-10, -10, 10, 10)) == ["INV-2026-001"]
    assert _decode(page, C128_BOX + (-10, -5, 10, 5)) == []
    text = page.get_text()
    assert "Invoice INV-2026-001 total 1,250.00" in text
    assert any(abs(d["rect"].y0 - 50) < 1 and d["rect"].width > 500 for d in page.get_drawings())  # เส้นยาวยังอยู่
    # ตรวจหาซ้ำเจอที่ใหม่ แล้ว undo กลับที่เดิม
    moved = _by_text(_list(client, h, sid), "INV-2026-001")
    assert abs(moved["bbox"]["y0"] - target["y0"]) < 3
    assert client.post(f"/pdf/{sid}/undo", headers=h).status_code == 200
    back = _by_text(_list(client, h, sid), "INV-2026-001")
    assert abs(back["bbox"]["y0"] - c128["bbox"]["y0"]) < 1


def test_move_image_qr_and_delete(client, bc_session):
    h, sid = bc_session
    qr = _by_text(_list(client, h, sid), "https://example.com/doc/42")
    target = _shift(qr["bbox"], -50, 450)
    assert client.post(f"/edit/{sid}/page/0/barcodes/edit", headers=h,
                       json={"bbox": qr["bbox"], "target": target}).status_code == 200
    page = _doc(client, h, sid)[0]
    assert _decode(page, fitz.Rect(*target.values()) + (-5, -5, 5, 5)) == ["https://example.com/doc/42"]
    assert _decode(page, QR_BOX + (-5, -5, 5, 5)) == []

    moved = _by_text(_list(client, h, sid), "https://example.com/doc/42")
    r = client.post(f"/edit/{sid}/page/0/barcodes/edit", headers=h, json={"bbox": moved["bbox"], "delete": True})
    assert r.status_code == 200 and r.json()["bbox"] is None
    texts = [b["text"] for b in _list(client, h, sid)["barcodes"]]
    assert texts == ["INV-2026-001"]


def test_validation(client, make_user, bc_session):
    h, sid = bc_session
    c128 = _by_text(_list(client, h, sid), "INV-2026-001")
    url = f"/edit/{sid}/page/0/barcodes/edit"
    assert client.post(url, headers=h, json={"bbox": c128["bbox"]}).status_code == 400  # ไม่ระบุทั้งย้ายและลบ
    assert client.post(url, headers=h, json={"bbox": c128["bbox"], "target": c128["bbox"],
                                             "delete": True}).status_code == 400
    assert client.post(url, headers=h, json={"bbox": c128["bbox"],
                                             "target": _shift(c128["bbox"], 0, 900)}).status_code == 400  # เกินขอบ
    gone = {"x0": 300, "y0": 300, "x1": 350, "y1": 350}
    r = client.post(url, headers=h, json={"bbox": gone, "delete": True})
    assert r.status_code == 400 and "ไม่พบบาร์โค้ด" in r.json()["detail"]
    _, other = make_user()
    assert client.get(f"/edit/{sid}/page/0/barcodes", headers=other).status_code in (403, 404)


def test_rotated_page_not_supported(client, bc_session):
    h, sid = bc_session
    c128 = _by_text(_list(client, h, sid), "INV-2026-001")
    assert client.post(f"/pdf/{sid}/pages/rotate", headers=h, json={"page_numbers": [0], "angle": 90}).status_code == 200
    items = _list(client, h, sid)
    if items["rotated"]:
        assert items["barcodes"] == []
        r = client.post(f"/edit/{sid}/page/0/barcodes/edit", headers=h, json={"bbox": c128["bbox"], "delete": True})
        assert r.status_code == 400
