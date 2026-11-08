"""ชั้นข้อความ OCR ของรูปภาพ (เฟส 5): ข้อความไทยในรูป → ค้นหา/เซ็นเซอร์ได้ และทาดำพิกเซลของรูปตรงนั้น

ต้องมี tesseract + ภาษาไทย (Docker image มีอยู่แล้ว) — เครื่องที่ไม่มีจะข้ามเทสต์นี้
"""
import shutil
import subprocess
from pathlib import Path

import fitz
import pytest

from app.services.pdf_service import text_index


def _has_thai_tesseract() -> bool:
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return "tha" in out.split()


pytestmark = pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย")

FONT = str(Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")
LINES = ["(นางสาวตัวอย่าง ทดสอบระบบ)", "ผู้อำนวยการสำนักเงินสมทบ", "ปฏิบัติราชการแทนเลขาธิการ"]


def _signature_block_png() -> bytes:
    """บล็อกชื่อ+ตำแหน่งผู้ลงนามเป็นรูปภาพ (แบบหนังสือราชการ) — วาดข้อความแบบ shape ด้วย fpdf2 แล้วแปลงเป็นภาพ"""
    from fpdf import FPDF

    pdf = FPDF(unit="pt", format=(420, 120))
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0)
    pdf.add_page()
    pdf.add_font("S", "", FONT)
    pdf.set_font("S", size=16)
    pdf.set_text_shaping(True, script="thai", language="tha")
    for i, line in enumerate(LINES):
        pdf.set_xy(20, 8 + i * 36)
        pdf.cell(380, 30, line, align="C")
    src = fitz.open(stream=bytes(pdf.output()))
    return src[0].get_pixmap(dpi=200).tobytes("png")


def _pdf_with_image_text() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "หนังสือรับรอง (ข้อความปกติ)", fontsize=14, fontname="s", fontfile=FONT)
    page.insert_image(fitz.Rect(90, 400, 510, 520), stream=_signature_block_png())
    return doc.tobytes()


def test_ocr_layer_makes_image_text_searchable_and_redactable(client, make_user):
    from app.core.session import session_manager

    _, headers = make_user()
    r = client.post("/pdf/upload", headers=headers, files={"file": ("sig.pdf", _pdf_with_image_text(), "application/pdf")})
    sid = r.json()["session_id"]
    keyword = "ผู้อำนวยการสำนักเงินสมทบ"

    r = client.post(f"/pdf/{sid}/redact-search", headers=headers, json={"keyword": keyword})
    assert r.json()["redacted_count"] == 0 and r.json()["image_pages"] == [1]

    r = client.post(f"/pdf/{sid}/ocr-text-layer", headers=headers, json={})
    assert r.status_code == 200, r.text
    assert r.json()["pages"] == [1] and r.json()["words"] > 0
    again = client.post(f"/pdf/{sid}/ocr-text-layer", headers=headers, json={})
    assert again.json()["words"] == 0  # รันซ้ำไม่เพิ่มซ้ำ

    page = session_manager.get(sid).doc[0]
    pt = text_index.page_text(page)
    for line in LINES[1:]:
        assert text_index.find(pt, text_index.keyword_pattern(line)), (line, pt.text)
    before = page.get_pixmap(clip=fitz.Rect(90, 400, 510, 520)).samples

    r = client.post(f"/pdf/{sid}/redact-search", headers=headers, json={"keyword": keyword})
    assert r.json()["redacted_count"] == 1
    page = session_manager.get(sid).doc[0]
    assert keyword not in "".join(text_index.page_text(page).text.split())
    assert page.get_pixmap(clip=fitz.Rect(90, 400, 510, 520)).samples != before  # พิกเซลของรูปถูกทาดำ
    assert "หนังสือรับรอง" in page.get_text()  # ข้อความปกติยังอยู่
