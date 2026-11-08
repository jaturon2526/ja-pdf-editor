"""คุณภาพไฟล์ Word ที่แปลงจาก PDF ที่ออกแบบด้วยโปรแกรมกราฟิก (รูปทรงโปร่งใส, หัวข้อสีขาวบนแถบสี, ภาษาไทย)"""
import re
import zipfile
from io import BytesIO

import fitz
import pytest
from docx import Document

from app.services.pdf2docx_fixes import (
    normalize_docx_fonts,
    normalize_font_name,
    paragraph_text_groups,
    replace_group_text,
    sanitize_drawings,
)


def _designed_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    # กรอบโปร่งใส 100% สีดำทับเนื้อหา (แบบที่ Canva/PDFium สร้าง)
    page.draw_rect(fitz.Rect(30, 100, 560, 300), color=None, fill=(0, 0, 0), fill_opacity=0)
    page.insert_text((50, 150), "Body text inside a transparent group", fontsize=12)
    # หัวข้อสีขาวบนแถบสีน้ำเงิน
    page.draw_rect(fitz.Rect(0, 320, 400, 350), color=None, fill=(0, 0.33, 1))
    page.insert_text((20, 340), "Section heading white", fontsize=14, color=(1, 1, 1))
    data = doc.tobytes()
    doc.close()
    return data


def test_transparent_shapes_are_dropped():
    with fitz.open("pdf", _designed_pdf()) as doc:
        page = doc[0]
        raw = page.get_cdrawings()
        assert any(d.get("fill_opacity") == 0 for d in raw)
        cleaned = sanitize_drawings(page, raw)
    assert all(d.get("fill_opacity", 1) >= 0.999 for d in cleaned if d.get("fill") is not None)
    assert len(cleaned) == len(raw) - 1


def test_converted_docx_has_no_black_boxes_and_readable_headings(monkeypatch):
    from app.services import convert_service

    monkeypatch.setattr(convert_service.settings, "GEMINI_API_KEY", None)
    docx_bytes, _ = convert_service.convert_pdf_to_docx(_designed_pdf(), None)
    xml = zipfile.ZipFile(BytesIO(docx_bytes)).read("word/document.xml").decode()
    assert 'w:fill="000000"' not in xml
    doc = Document(BytesIO(docx_bytes))
    heading = next(p for p in doc.paragraphs if "Section heading" in p.text) if any(
        "Section heading" in p.text for p in doc.paragraphs) else None
    if heading is None:  # อยู่ในตาราง
        heading = next(p for t in doc.tables for row in t.rows for c in row.cells for p in c.paragraphs
                       if "Section heading" in p.text)
    from app.services.pdf2docx_fixes import _has_dark_background
    assert _has_dark_background(heading)


def _runs(p):
    return [(r.text, bool(r.bold), str(r.font.color.rgb) if r.font.color and r.font.color.rgb else None) for r in p.runs]


def test_replace_group_text_keeps_each_runs_formatting():
    """เดิมรวมข้อความทั้งย่อหน้าไว้ใน run แรก — คำตัวหนา/สีต่างกันกลายเป็นแบบเดียว"""
    from docx.shared import RGBColor

    doc = Document()
    p = doc.add_paragraph()
    r = p.add_run("หมายเหตุ:")
    r.bold = True
    p.add_run(" ส่วนที่ส าคัญ ")
    red = p.add_run("ค าเตือน")
    red.font.color.rgb = RGBColor(0xC0, 0, 0)
    [group] = paragraph_text_groups(p)
    replace_group_text(group, "หมายเหตุ: ส่วนที่สำคัญ คำเตือน")
    assert p.text == "หมายเหตุ: ส่วนที่สำคัญ คำเตือน"
    assert _runs(p) == [("หมายเหตุ:", True, None), (" ส่วนที่สำคัญ ", False, None), ("คำเตือน", False, "C00000")]


def test_inserted_characters_stick_to_the_previous_run():
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("ข้อความ").bold = True
    p.add_run("ภาษาไทย")
    [group] = paragraph_text_groups(p)
    replace_group_text(group, "ข้อความ\u200bภาษา\u200bไทย")
    assert [r.text for r in p.runs] == ["ข้อความ\u200b", "ภาษา\u200bไทย"]


def test_text_groups_split_at_line_breaks_and_tabs_and_keep_their_order():
    """เดิมข้อความไปกองอยู่ก่อน run ที่ขึ้นบรรทัด/tab — สารบัญ "บริการ<tab>2" กลายเป็น "บริการ2<tab>" """
    from docx.enum.text import WD_BREAK

    doc = Document()
    p = doc.add_paragraph()
    p.add_run("การซื้อขายสินค้า")
    p.add_run().add_break(WD_BREAK.LINE)
    p.add_run("TRADE MESSAGE")
    p.add_run("\t")
    p.add_run("ส าหรับ")
    groups = paragraph_text_groups(p)
    assert ["".join(n.text for n in g) for g in groups] == ["การซื้อขายสินค้า", "TRADE MESSAGE", "ส าหรับ"]
    replace_group_text(groups[2], "สำหรับ")
    assert p.text == "การซื้อขายสินค้า\nTRADE MESSAGE\tสำหรับ"


def test_pictures_are_not_part_of_the_text():
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("ก่อนรูป")
    pic = p.add_run()
    pic._r.append(pic._r.makeelement("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing", {}))
    p.add_run("หลังรูป")
    assert ["".join(n.text for n in g) for g in paragraph_text_groups(p)] == ["ก่อนรูปหลังรูป"]


@pytest.mark.parametrize("pdf_name, expected", [
    ("NotoSansThai", ("Noto Sans", "Noto Sans Thai")),
    ("ABCDEF+Sarabun-Bold", ("Sarabun", "Sarabun")),
    ("THSarabunNew", ("TH Sarabun New", "TH Sarabun New")),
    ("OpenSans", ("Open Sans", "Open Sans")),
])
def test_normalize_font_name(pdf_name, expected):
    assert normalize_font_name(pdf_name) == expected


def test_thai_runs_get_complex_script_size_and_font():
    doc = Document()
    run = doc.add_paragraph().add_run("ภาษาไทย 123")
    run.font.size = __import__("docx.shared", fromlist=["Pt"]).Pt(16)
    run.font.name = "NotoSansThai"
    run.bold = True
    normalize_docx_fonts(doc)
    xml = run._r.xml
    assert 'w:szCs w:val="32"' in xml and "<w:bCs/>" in xml
    assert re.search(r'w:cs="Noto Sans Thai"', xml) and re.search(r'w:ascii="Noto Sans"', xml)
