"""แปลงไฟล์สแกน → Word (app/services/scan_docx): ข้อความเป็นข้อความจริง, ตารางเป็นตาราง Word, โลโก้/บาร์โค้ดเป็นรูป,
ฟอนต์ Sarabun ฝังในไฟล์ และเมนูแปลงเป็น Word เปลี่ยนไปใช้ทางนี้อัตโนมัติเมื่อเป็นไฟล์สแกน"""
import io
import random
import shutil
import subprocess
import uuid
import zipfile

import fitz
import pytest
from docx import Document
from docx.oxml.ns import qn

from app.services import scan_docx
from app.services.scan_docx.writer import FONT_FILES, FONTS_DIR, _obfuscate


def _no_tones(s: str) -> str:
    return "".join(c for c in s if c not in "\u0e48\u0e49\u0e4a\u0e4b\u200b \n")


def _has_thai_tesseract() -> bool:
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return "tha" in out.split()


needs_ocr = pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย (CI ติดตั้งให้)")


@pytest.fixture(scope="module")
def scanned_pdf(tmp_path_factory):
    from scripts.scan_eval import synthetic_doc, to_scan_pdf

    pdf, _truth, _tables = synthetic_doc("Sarabun", 12, 7, tmp_path_factory.mktemp("synth"))
    return to_scan_pdf(fitz.open(stream=pdf)[0], "bw", random.Random(1))


def _text_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Hello text PDF")
    return doc.tobytes()


def test_detects_scanned_pdf(scanned_pdf):
    assert scan_docx.is_scanned_pdf(scanned_pdf)
    assert not scan_docx.is_scanned_pdf(_text_pdf())
    assert not scan_docx.is_scanned_pdf(b"not a pdf")


def test_invisible_ocr_layer_still_counts_as_scan(scanned_pdf):
    """ไฟล์จากเมนูสแกนมีชั้นข้อความ OCR ล่องหน — ยังเป็นไฟล์สแกน (pdf2docx ได้แต่รูปเต็มหน้า)"""
    doc = fitz.open(stream=scanned_pdf)
    doc[0].insert_text((72, 300), "invisible OCR words " * 5, render_mode=3)
    assert scan_docx.is_scanned_pdf(doc.tobytes())


def test_font_obfuscation_roundtrip():
    data = (FONTS_DIR / FONT_FILES["regular"]).read_bytes()
    key = uuid.uuid4()
    once = _obfuscate(data, key)
    assert once[:32] != data[:32] and once[32:] == data[32:]
    assert _obfuscate(once, key) == data


@needs_ocr
def test_scan_to_editable_word(scanned_pdf):
    data = scan_docx.convert_scan_to_docx(scanned_pdf)
    doc = Document(io.BytesIO(data))
    body = doc.element.body
    text = "\n".join("".join(t.text or "" for t in p.iter(qn("w:t"))) for p in body.iter(qn("w:p")))
    # OCR อาจพลาดวรรณยุกต์บางตัว — เทียบโดยไม่นับวรรณยุกต์ และต้องเจออย่างน้อย 4 ใน 5 วลี
    plain = _no_tones(text)
    phrases = ("ค่าธรรมเนียมการจดจำนอง", "ค่าอากรแสตมป์", "ขอแสดงความนับถือ", "2,000.00", "คุณสมชาย")
    found = [p for p in phrases if _no_tones(p) in plain]
    assert len(found) >= 4, (found, text)
    tables = body.findall(qn("w:tbl"))
    assert len(tables) == 1 and len(tables[0].findall(qn("w:tr"))) == 4
    assert len(list(body.iter(qn("pic:pic")))) >= 2          # โลโก้ + บาร์โค้ด เป็นรูป
    # ข้อความไม่ได้กลายเป็นรูป: รูปทั้งหมดรวมกันเล็กกว่าหน้ากระดาษมาก
    page_area = doc.sections[0].page_width * doc.sections[0].page_height
    pics = sum(int(e.get("cx")) * int(e.get("cy")) for e in body.iter(qn("wp:extent")))
    assert pics < 0.1 * page_area
    # ฟอนต์ Sarabun + ฝังในไฟล์
    assert {r.get(qn("w:cs")) for r in body.iter(qn("w:rFonts"))} == {"Sarabun"}
    z = zipfile.ZipFile(io.BytesIO(data))
    assert any(n.startswith("word/fonts/") and n.endswith(".odttf") for n in z.namelist())
    assert "embedTrueTypeFonts" in z.read("word/settings.xml").decode()
    assert "obfuscatedFont" in z.read("[Content_Types].xml").decode()
    assert len(doc.sections) == 1                             # หนึ่งหน้าสแกน = หนึ่งหน้า Word


@needs_ocr
def test_conversion_task_routes_scans_to_ocr(client, make_user, upload, scanned_pdf):
    _, headers = make_user()
    sid = upload(headers, scanned_pdf, name="สแกน.pdf")
    files = client.get("/pdf/files", headers=headers).json()["files"]
    fid = next(f["id"] for f in files if f["session_id"] == sid)

    info = client.post("/convert/pdf-to-word/inspect", headers=headers, json={"file_record_id": fid}).json()
    assert info["scanned"] is True and info["pages"] == 1

    # เลือกโหมดปกติ (editable) มาก็ต้องได้ผลแบบไฟล์สแกน — ไม่ใช่รูปเต็มหน้าแบบ pdf2docx
    r = client.post("/convert/pdf-to-word/async", headers=headers, json={"file_record_id": fid})
    st = client.get(f"/convert/pdf-to-word/status/{r.json()['task_id']}", headers=headers).json()
    assert st["status"] == "completed", st
    assert st["error_message"] == "scan"
    data = client.get(f"/convert/pdf-to-word/download/{r.json()['task_id']}", headers=headers).content
    text = "".join(t.text or "" for t in Document(io.BytesIO(data)).element.body.iter(qn("w:t")))
    assert _no_tones("ขอแสดงความนับถือ") in _no_tones(text)


def test_inspect_text_pdf_and_ownership(client, make_user, upload):
    _, headers = make_user()
    _, other = make_user()
    sid = upload(headers)
    assert client.post("/convert/pdf-to-word/inspect", headers=headers, json={"session_id": sid}).json()["scanned"] is False
    assert client.post("/convert/pdf-to-word/inspect", headers=other, json={"session_id": sid}).status_code == 404
    assert client.post("/convert/pdf-to-word/inspect", headers=headers, json={}).status_code == 422


def test_too_many_pages_rejected():
    doc = fitz.open()
    for _ in range(scan_docx.MAX_PAGES + 1):
        doc.new_page()
    with pytest.raises(scan_docx.ScanConvertError):
        scan_docx.convert_scan_to_docx(doc.tobytes())


@pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย")
def test_scanner_text_layer_is_reused():
    """ไฟล์จากเมนูสแกน: ข้อความที่อ่านไว้ตอนสแกน (จากภาพเทา) ดีกว่าการอ่านภาพขาวดำซ้ำ → Word ใช้ข้อความชุดนั้น"""
    from PIL import Image, ImageDraw, ImageFont

    from app.services.pdf_service import build_scan_pdf

    font = ImageFont.truetype(str(FONTS_DIR / "Sarabun-Regular.ttf"), 56)
    gray = Image.new("L", (1240, 1754), 255)
    ImageDraw.Draw(gray).text((120, 200), "หนังสือรับรองการทำงาน", font=font, fill=90)
    page = Image.new("1", (1240, 1754), 1)   # ตัดเป็นขาวดำแล้วตัวอักษรหายหมด
    bufs = []
    for img, fmt in ((page, "PNG"), (gray, "JPEG")):
        b = io.BytesIO()
        img.save(b, fmt, dpi=(200, 200))
        bufs.append(b.getvalue())
    pdf = build_scan_pdf([bufs[0]], "t", ocr_images=[bufs[1]])
    assert fitz.open(stream=pdf).metadata["creator"] == scan_docx.SCANNER_CREATOR
    text = "\n".join(p.text for p in Document(io.BytesIO(scan_docx.convert_scan_to_docx(pdf))).paragraphs)
    assert "หนังสือรับรอง" in _no_tones(text) or "หนังสือรับรอง" in text
