"""สแกนเอกสาร (POST /pdf/scan): ภาพหลายหน้า → PDF เรียงตามลำดับ + ชั้นข้อความ OCR (ค้นหา/เซ็นเซอร์คำไทยได้)"""
import io
import shutil
import subprocess
from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.api.pdf.scan import clean_scan_filename

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")
WORDS = ["ใบเสนอราคา", "สัญญาเช่า", "หนังสือรับรอง"]


def _page_png(word: str, mode: str = "1") -> bytes:
    """หน้าเอกสารขาวดำแบบที่เครื่องผู้ใช้ส่งมา: 1240x1754 px (A5 @200dpi) ข้อความไทยตัวใหญ่"""
    img = Image.new("L", (1240, 1754), 255)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 64)
    d.text((120, 200), word, font=font, fill=0)
    d.text((120, 340), "เลขที่ 2569/045", font=font, fill=0)
    img = img.convert(mode) if mode != "L" else img
    buf = io.BytesIO()
    if mode == "RGB":
        img.save(buf, "JPEG", quality=85, dpi=(200, 200))
    else:
        img.save(buf, "PNG", dpi=(200, 200))
    return buf.getvalue()


def _scan(client, headers, pages, filename="Scan_20261025_152133"):
    files = [("pages", (f"p{i}.png", data, "image/png")) for i, data in enumerate(pages)]
    return client.post("/pdf/scan", headers=headers, data={"filename": filename}, files=files)


def _file_bytes(client, headers, file_id):
    r = client.get(f"/pdf/files/{file_id}/download", headers=headers)
    assert r.status_code == 200, r.text
    return r.content


def _has_thai_tesseract() -> bool:
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return "tha" in out.split()


@pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย (CI ติดตั้งให้)")
def test_scan_builds_ordered_searchable_pdf(client, make_user):
    _, headers = make_user()
    r = _scan(client, headers, [_page_png(w) for w in WORDS] + [_page_png("ภาพสี", "RGB")])
    assert r.status_code == 200, r.text
    st = client.get(f"/pdf/scan/status/{r.json()['task_id']}", headers=headers).json()
    assert st["status"] == "completed", st
    assert st["file"]["filename"] == "Scan_20261025_152133.pdf"

    doc = fitz.open("pdf", _file_bytes(client, headers, st["file"]["id"]))
    assert doc.page_count == 4
    assert doc.metadata["title"] == "Scan_20261025_152133"
    for i, word in enumerate(WORDS):
        page = doc[i]
        assert page.rect.width == pytest.approx(1240 * 72 / 200, abs=1)   # สัดส่วนจริง ไม่บังคับ A4
        assert page.search_for(word), f"หน้า {i + 1}: ค้นหา '{word}' ไม่เจอ"
        assert not any(page.search_for(w) for w in WORDS if w != word)    # ลำดับหน้าถูก

    # เซ็นเซอร์ด้วยคำค้นหาได้ (เครื่องมือด่วน — สร้างไฟล์ใหม่)
    r = client.post(f"/pdf/files/{st['file']['id']}/quick-action", headers=headers,
                    json={"action": "redact_search", "keyword": "สัญญาเช่า"})
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["count"] >= 1


def test_duplicate_name_gets_suffix(client, make_user):
    _, headers = make_user()
    names = []
    for _ in range(2):
        tid = _scan(client, headers, [_page_png("ทดสอบ")], filename="Scan_X").json()["task_id"]
        names.append(client.get(f"/pdf/scan/status/{tid}", headers=headers).json()["file"]["filename"])
    assert names == ["Scan_X.pdf", "Scan_X (2).pdf"]


def test_rejects_non_image_and_too_many_pages(client, make_user):
    _, headers = make_user()
    r = _scan(client, headers, [_page_png("ก"), b"%PDF-1.4 not an image"])
    assert r.status_code == 400 and "หน้า 2" in r.json()["detail"]
    r = _scan(client, headers, [_page_png("ก")] * 51)
    assert r.status_code == 400


def test_status_is_private(client, make_user):
    _, owner = make_user()
    _, other = make_user()
    tid = _scan(client, owner, [_page_png("ก")]).json()["task_id"]
    assert client.get(f"/pdf/scan/status/{tid}", headers=other).status_code == 404


@pytest.mark.parametrize("raw, expected", [
    ("Scan_20261025_152133", "Scan_20261025_152133.pdf"),
    ("ใบเสร็จ.pdf", "ใบเสร็จ.pdf"),
    ("../../etc/passwd", "_.._etc_passwd.pdf"),
    ("   ", "Scan.pdf"),
])
def test_clean_filename(raw, expected):
    assert clean_scan_filename(raw) == expected


@pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย (CI ติดตั้งให้)")
def test_table_of_contents_with_dot_leaders_is_searchable():
    """สารบัญภาษาอังกฤษที่มีจุดไข่ปลา (ผู้ใช้สแกนแล้วค้นหา "Reply" ไม่เจอ) — อ่านซ้ำแบบข้อความกระจายแล้วต้องค้นหาเจอ"""
    from app.services.pdf_service import build_scan_pdf

    img = Image.new("L", (1240, 760), 255)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 34)
    items = ["Open PDFs", "Split View", "Reply Annotations", "Watermark", "Background", "Compress"]
    for i, item in enumerate(items):
        y = 60 + i * 110
        d.text((80, y), f"{i + 1}) {item}", font=font, fill=0)
        x0 = 80 + int(d.textlength(f"{i + 1}) {item} ", font=font))
        for x in range(x0, 1080, 14):
            d.ellipse((x, y + 30, x + 4, y + 34), fill=0)
        d.text((1110, y), str(5 + i), font=font, fill=0)
    buf = io.BytesIO()
    img.convert("1").save(buf, "PNG", dpi=(200, 200))
    doc = fitz.open("pdf", build_scan_pdf([buf.getvalue()], "toc"))
    found = [w for w in ("Reply", "Annotations", "Watermark", "Background", "Compress") if doc[0].search_for(w)]
    assert len(found) >= 4, f"ค้นหาเจอแค่ {found}\n{doc[0].get_text()}"


@pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย (CI ติดตั้งให้)")
def test_english_page_is_read_with_english_model():
    """หน้าภาษาอังกฤษ (ผู้ใช้คัดลอก "We're thrilled" ได้แค่ "thrilled" และมีอักษรไทยขยะปน) — OSD เห็นเป็น Latin
    แล้วอ่านด้วยโมเดลอังกฤษ: ได้คำครบ ไม่มีอักษรไทยปน"""
    import re

    from app.services.pdf_service import build_scan_pdf

    img = Image.new("L", (1654, 1100), 255)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 40)
    lines = ["We're thrilled to welcome you to the all-new editor.",
             "It is a professional, secure, and all-in-one PDF solution.",
             "The main interface has three sections: Left Side Panel,",
             "Toolbar and Properties Panel. Search Result, Signatures."]
    for i, line in enumerate(lines):
        d.text((100, 120 + i * 90), line, font=font, fill=0)
    buf = io.BytesIO()
    img.convert("1").save(buf, "PNG", dpi=(200, 200))
    page = fitz.open("pdf", build_scan_pdf([buf.getvalue()], "en"))[0]
    text = page.get_text()
    assert not re.search(r"[฀-๿]", text), text
    for word in ("We're", "thrilled", "professional", "Properties", "Signatures"):
        assert page.search_for(word), f"ค้นหา '{word}' ไม่เจอ\n{text}"


def _gray_jpeg(word: str) -> bytes:
    """ภาพเทาสำหรับอ่านข้อความ (แบบที่เครื่องผู้ใช้ส่งมาคู่กับหน้าขาวดำ)"""
    img = Image.new("L", (1240, 1754), 255)
    ImageDraw.Draw(img).text((120, 200), word, font=ImageFont.truetype(FONT, 64), fill=90)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, dpi=(200, 200))
    return buf.getvalue()


@pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย (CI ติดตั้งให้)")
def test_scan_uses_better_text_from_gray_ocr_image(client, make_user):
    """หน้าขาวดำที่ตัวอักษรหายไปตอนตัดสี + ภาพเทาที่อ่านได้ → ชั้นข้อความมาจากภาพเทา แต่ภาพในไฟล์ยังเป็นหน้าขาวดำ
    ภาพเทาที่ชื่อไฟล์ผิด/เกินจำนวนหน้า/ไม่ใช่ภาพ ถูกข้ามไปเฉย ๆ"""
    _, headers = make_user()
    blank = Image.new("1", (1240, 1754), 1)
    buf = io.BytesIO()
    blank.save(buf, "PNG", dpi=(200, 200))
    files = [("pages", ("page-001.png", buf.getvalue(), "image/png")),
             ("pages", ("page-002.png", _page_png("สัญญาเช่า"), "image/png")),
             ("ocr_pages", ("ocr-001.jpg", _gray_jpeg("ใบเสนอราคา"), "image/jpeg")),
             ("ocr_pages", ("ocr-009.jpg", _gray_jpeg("หนังสือรับรอง"), "image/jpeg")),
             ("ocr_pages", ("ocr-002.jpg", b"not an image", "image/jpeg"))]
    r = client.post("/pdf/scan", headers=headers, data={"filename": "Scan_gray"}, files=files)
    assert r.status_code == 200, r.text
    st = client.get(f"/pdf/scan/status/{r.json()['task_id']}", headers=headers).json()
    assert st["status"] == "completed", st
    doc = fitz.open("pdf", _file_bytes(client, headers, st["file"]["id"]))
    assert doc.page_count == 2
    assert doc[0].search_for("ใบเสนอราคา")
    assert doc[1].search_for("สัญญาเช่า")
    assert not any(doc[i].search_for("หนังสือรับรอง") for i in range(2))
