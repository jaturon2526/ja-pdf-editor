"""บาร์โค้ด (services/barcode_service.py + /edit/barcode/*): ทุกประเภทสร้างได้และอ่านกลับได้ตรง (zxing-cpp),
ภาษาไทยใน QR/Data Matrix/PDF417/Aztec (UTF-8 + ECI), ตรวจข้อมูลก่อนสร้าง, สีตัดกันพอ, วางลงหน้าเป็นเวกเตอร์ + undo"""
import io
import shutil

import fitz
import pytest
from PIL import Image

from app.services import barcode_service as bc

zxingcpp = pytest.importorskip("zxingcpp")
pytestmark = pytest.mark.skipif(shutil.which("gs") is None, reason="ต้องมี Ghostscript")


def _decode(png: bytes) -> list[str]:
    return [r.text for r in zxingcpp.read_barcodes(Image.open(io.BytesIO(png)))]


@pytest.mark.parametrize("kind, data, expected", [
    ("qrcode", "สวัสดีครับ ^ https://example.com", "สวัสดีครับ ^ https://example.com"),
    ("datamatrix", "เอกสารเลขที่ ๑๒๓", "เอกสารเลขที่ ๑๒๓"),
    ("pdf417", "ทดสอบ PDF417 ภาษาไทย", "ทดสอบ PDF417 ภาษาไทย"),
    ("azteccode", "ตั๋ว Aztec", "ตั๋ว Aztec"),
    ("qrcode", "PLAIN-ASCII-123", "PLAIN-ASCII-123"),
    ("code128", "INV-2026/001", "INV-2026/001"),
    ("code39", "abc 39", "ABC 39"),
    ("ean13", "885000000001", "8850000000010"),      # เติมเลขตรวจสอบให้
    ("ean8", "1234567", "12345670"),
    ("upca", "03600029145", "036000291452"),
    ("itf", "12345678901231", "12345678901231"),
])
def test_every_type_round_trips(kind, data, expected):
    texts = _decode(bc.render_png(bc.BarcodeSpec(kind, data)))
    assert texts, kind
    got = texts[0]
    if kind == "upca":
        got = got[-12:]  # บางตัวอ่านคืน UPC-A เป็น EAN-13 (เติม 0 หน้า)
    assert got == expected


@pytest.mark.parametrize("kind, data, msg", [
    ("ean13", "8850000000019", "เลขตรวจสอบ"),
    ("ean13", "12345", "12 หลัก"),
    ("code128", "ภาษาไทย", "QR Code"),
    ("itf", "123", "จำนวนหลักเป็นคู่"),
    ("code39", "a_b", "Code 39"),
    ("qrcode", "   ", "กรุณากรอก"),
    ("nope", "x", "ไม่รู้จัก"),
])
def test_validation_messages(kind, data, msg):
    with pytest.raises(bc.BarcodeError) as exc:
        bc.validate(bc.BarcodeSpec(kind, data))
    assert msg in str(exc.value)


def test_colors_must_contrast_and_dark_on_light():
    with pytest.raises(bc.BarcodeError, match="ต่างกันน้อย"):
        bc.validate(bc.BarcodeSpec("qrcode", "x", bar_color="#BBBBBB"))
    with pytest.raises(bc.BarcodeError, match="เข้มกว่า"):
        bc.validate(bc.BarcodeSpec("qrcode", "x", bar_color="#FFFFFF", bg_color="#000000"))
    spec = bc.validate(bc.BarcodeSpec("qrcode", "สี", bar_color="#1e3a8a", bg_color="#fef3c7"))
    assert _decode(bc.render_png(spec)) == ["สี"]


def test_too_long_is_friendly():
    with pytest.raises(bc.BarcodeError, match="ยาวเกิน"):
        bc.render_pdf(bc.BarcodeSpec("datamatrix", "ภาษาไทย" * 140))


def test_api_preview_and_insert_vector_with_undo(client, make_user, upload):
    _, h = make_user()
    r = client.post("/edit/barcode/preview", headers=h, json={"type": "ean13", "data": "885000000001"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["x-barcode-data"] == "8850000000010"
    bad = client.post("/edit/barcode/preview", headers=h, json={"type": "code128", "data": "ไทย"})
    assert bad.status_code == 400 and "QR Code" in bad.json()["detail"]
    assert {t["key"] for t in client.get("/edit/barcode/types", headers=h).json()} >= {"qrcode", "ean13", "datamatrix"}

    sid = upload(h)
    r = client.post(f"/edit/{sid}/page/0/barcode", headers=h, json={
        "type": "qrcode", "data": "ใบแจ้งหนี้ 001", "x0": 400, "y0": 50, "x1": 520, "y1": 170})
    assert r.status_code == 200, r.text
    doc = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    page = doc[0]
    assert not page.get_images(), "ต้องเป็นเวกเตอร์ ไม่ใช่รูป"
    clip = fitz.Rect(390, 40, 530, 180)
    png = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip).tobytes("png")
    assert _decode(png) == ["ใบแจ้งหนี้ 001"]
    assert client.post(f"/pdf/{sid}/undo", headers=h).status_code == 200
    doc = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    assert not _decode(doc[0].get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip).tobytes("png"))
