"""PDF → Word (เฟส 7b): เส้นใต้/ไฮไลต์ให้ตรงกับข้อความจริง และ bullet ฟอนต์ Symbol ไม่กลายเป็น "?"

ปัญหาจากไฟล์จริง (เอกสารขอบเขตงานที่ export จาก Word/LibreOffice):
- "หมายเหตุ:" — เส้นใต้หาย และมีช่องว่างแทรกก่อน ":" (ช่องว่างปลอมที่ PDF วางซ้อนใต้ตัวอักษร)
- แถบไฮไลต์ที่คลุม bullet + ข้อความ กลายเป็นสีพื้นทั้งเซลล์ตาราง (ยาวเกินข้อความ) และไฮไลต์ขาดที่วรรณยุกต์
- bullet ของฟอนต์ OpenSymbol/Symbol (U+F0B7) แสดงเป็น "?" ใน Word ที่ไม่มีฟอนต์นั้น
"""
import re
import zipfile
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document

from app.services.pdf2docx_fixes import (
    _char_in_rect,
    drop_overlapping_spaces,
    fix_symbol_chars,
    patched_pdf2docx,
)

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")


def _marks_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="sar", fontfile=FONT)
    f = fitz.Font(fontfile=FONT)
    # ไฮไลต์คลุมทั้ง bullet และข้อความ (bullet กับข้อความอยู่คนละคอลัมน์ → pdf2docx ทำเป็นตาราง)
    page.draw_rect(fitz.Rect(71, 96, 232, 114), color=None, fill=(1, 1, 0))
    page.insert_text((72, 110), "\u2022", fontname="sar", fontsize=12)
    page.insert_text((90, 110), "ปรับแก้ข้อมูลที่ต้องส่ง Export", fontname="sar", fontsize=12)
    # "หมายเหตุ" + " :" โดยช่องว่างวางซ้อนใต้ตัวอักษรสุดท้าย และเส้นใต้คลุมถึง ":"
    w = f.text_length("หมายเหตุ", fontsize=12)
    sw = f.text_length(" ", fontsize=12)
    cw = f.text_length(":", fontsize=12)
    page.insert_text((72, 160), "หมายเหตุ", fontname="sar", fontsize=12)
    page.insert_text((72 + w - sw, 160), " :", fontname="sar", fontsize=12)
    page.draw_line((72, 162.5), (72 + w + cw, 162.5), color=(0, 0, 0), width=0.8)
    page.insert_text((72 + w + cw + 4, 160), "ข้อความต่อท้าย", fontname="sar", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def _runs(xml: str, key: str) -> list[tuple[str, str]]:
    """[(ข้อความ, ธง U/H/S)] ของย่อหน้าที่มี key"""
    i = xml.find(key)
    p = xml[xml.rfind("<w:p>", 0, i):xml.find("</w:p>", i)]
    out = []
    for r in re.findall(r"<w:r>(.*?)</w:r>", p):
        t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", r)).replace("\u200b", "")
        if t:
            out.append((t, ("U" if "<w:u " in r else "") + ("H" if "w:highlight" in r else "")))
    return out


def _convert(monkeypatch, pdf: bytes) -> str:
    from app.services import convert_service

    monkeypatch.setattr(convert_service.settings, "GEMINI_API_KEY", None)
    docx_bytes, _ = convert_service.convert_pdf_to_docx(pdf, None)
    return zipfile.ZipFile(BytesIO(docx_bytes)).read("word/document.xml").decode()


def test_underline_reaches_colon_without_phantom_space(monkeypatch):
    xml = _convert(monkeypatch, _marks_pdf())
    runs = _runs(xml, "หมายเหตุ")
    text = "".join(t for t, _ in runs)
    assert "หมายเหตุ:" in text and "หมายเหตุ :" not in text
    underlined = "".join(t for t, f in runs if "U" in f)
    assert underlined.strip() == "หมายเหตุ:"


def test_highlight_over_bullet_and_text_stays_on_the_text(monkeypatch):
    xml = _convert(monkeypatch, _marks_pdf())
    assert 'w:fill="ffff00"' not in xml.lower()      # ไม่ใช่สีพื้นทั้งเซลล์
    runs = _runs(xml, "ปรับ")
    assert "".join(t for t, f in runs if "H" in f).endswith("ปรับแก้ข้อมูลที่ต้องส่ง Export")


def test_zero_width_thai_marks_count_as_inside_the_highlight():
    class _C:
        def __init__(self, x0, x1, y0=0, y1=10):
            self.bbox = fitz.Rect(x0, y0, x1, y1)

    rect = _C(10, 50, 2, 12)
    assert _char_in_rect(_C(30, 30, -4, 3), rect)      # วรรณยุกต์: กว้าง 0 และสูงพ้นแถบ
    assert _char_in_rect(_C(48, 53), rect)              # กึ่งกลาง 50.5 — ยังอยู่ในระยะเผื่อ
    assert not _char_in_rect(_C(52, 58), rect)


def test_underline_spanning_two_lines_in_a_row_is_not_a_table_border():
    from pdf2docx.common.share import RectType
    from pdf2docx.shape.Shape import Stroke

    class _Line:
        is_horizontal_text = True

        def __init__(self, *bbox):
            self.bbox = fitz.Rect(*bbox)

    lines = [_Line(72.1, 482.7, 126.8, 499.8), _Line(122.3, 482.7, 134.5, 499.8)]
    stroke = Stroke({"start": (89.1, 496.9), "end": (131.6, 496.9), "width": 1.0, "color": 0})
    with patched_pdf2docx():
        stroke.parse_semantic_type(lines)
    assert stroke._potential_type & RectType.UNDERLINE.value
    # เส้นที่ยาวเกินข้อความจริง (เช่น เส้นขอบตาราง) ยังเป็นเส้นขอบ
    border = Stroke({"start": (60, 496.9), "end": (540, 496.9), "width": 1.0, "color": 0})
    with patched_pdf2docx():
        border.parse_semantic_type(lines)
    assert border._potential_type == RectType.BORDER.value


def test_phantom_spaces_overlapping_previous_glyphs_are_dropped():
    def ch(c, x0, x1):
        return {"c": c, "bbox": (x0, 0, x1, 10), "origin": (x0, 8)}

    blocks = [{"lines": [
        {"dir": (1, 0), "bbox": (72, 0, 127, 10), "spans": [{"bbox": (72, 0, 127, 10), "chars": [
            ch(" ", 72, 76), ch("ต", 121, 126.8), ch("ุ", 126.8, 126.8)]}]},
        {"dir": (1, 0), "bbox": (122, 0, 135, 10), "spans": [{"bbox": (122, 0, 135, 10), "chars": [
            ch(" ", 122.3, 126.7), ch(":", 126.8, 130.1), ch(" ", 126.7, 131.1), ch(" ", 130.1, 134.5)]}]},
    ]}]
    assert drop_overlapping_spaces(blocks) == 2
    texts = ["".join(c["c"] for s in ln["spans"] for c in s["chars"]) for ln in blocks[0]["lines"]]
    assert texts == [" ตุ", ": "]                 # ช่องว่างนำหน้าบรรทัด (ย่อหน้า) ยังอยู่


def test_symbol_font_bullets_become_unicode():
    doc = Document()
    p = doc.add_paragraph()
    r = p.add_run("\uf0b7")
    r.font.name = "OpenSymbol"
    w = p.add_run("\uf0a7 \uf0fc")
    w.font.name = "Wingdings"
    other = p.add_run("\uf0b7x")                         # ไม่รู้ฟอนต์ — แปลงเฉพาะ bullet ที่พบบ่อย
    assert fix_symbol_chars(doc) == 3
    assert r.text == "\u2022" and r.font.name == "Arial"
    assert w.text == "\u25aa \u2713"
    assert other.text == "\u2022x"


# ---------- โหมด "รักษาหน้าตาเหมือนต้นฉบับ" (layout_docx) ----------
def _layout(pdf: bytes):
    from app.services.layout_docx import convert_pdf_to_layout_docx

    z = zipfile.ZipFile(BytesIO(convert_pdf_to_layout_docx(pdf)))
    xml = z.read("word/document.xml").decode()
    image = next(n for n in z.namelist() if n.startswith("word/media/"))
    return xml, z.read(image)


def test_layout_mode_moves_highlight_and_underline_onto_the_text():
    xml, background = _layout(_marks_pdf())
    runs = _runs(xml, "หมายเหตุ")
    assert "".join(t for t, f in runs if "U" in f) == "หมายเหตุ:"       # กล่องเดียวกัน ไม่มีช่องว่างก่อน ":"
    hl = _runs(xml, "ปรับแก้")
    assert "".join(t for t, f in hl if "H" in f) == "ปรับแก้ข้อมูลที่ต้องส่ง Export"
    # แถบสีเหลืองและเส้นใต้ไม่อยู่ในภาพพื้นหลังแล้ว (ไม่งั้นจะยาวไม่เท่าข้อความเมื่อ Word ใช้ฟอนต์อื่น)
    pix = fitz.Pixmap(background)
    scale = pix.width / 595
    r, g, b = pix.pixel(int(225 * scale), int(99 * scale))[:3]
    assert not (r > 200 and g > 200 and b < 120)
    r, g, b = pix.pixel(int(80 * scale), int(162.5 * scale))[:3]
    assert min(r, g, b) > 200


def test_layout_mode_keeps_table_cell_shading_in_the_background():
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(60, 90, 300, 120), color=None, fill=(0.85, 0.85, 0.85))   # พื้นช่องตาราง (เกินข้อความ)
    page.insert_text((70, 110), "Header cell", fontsize=12)
    xml, background = _layout(doc.tobytes())
    assert "w:shd" not in xml and "w:highlight" not in xml
    pix = fitz.Pixmap(background)
    scale = pix.width / 595
    assert pix.pixel(int(250 * scale), int(105 * scale))[0] < 240


# ---------- การขึ้นบรรทัดที่ pdf2docx พลาด ----------
class _Span:
    def __init__(self, text, bold=False, size=10):
        self.text, self.flags, self.size, self.font = text, 16 if bold else 0, size, "Norasi"


class _L:
    def __init__(self, x0, y0, x1, text, tab=0, bold=False):
        self.bbox = fitz.Rect(x0, y0, x1, y0 + 17)
        self.text, self.tab_stop, self.line_break = text, tab, 0
        self.spans = [_Span(text, bold)]


class _Lines:
    def __init__(self, lines):
        self.lines = lines
        self.parent = type("B", (), {"is_horizontal_text": True})()

    def group_by_physical_rows(self):
        return [[ln] for ln in self.lines]


def test_missing_line_breaks_before_bullets_tabs_and_headings():
    from app.services.pdf2docx_fixes import refine_line_breaks

    page = (72, 72, 540, 770)
    cell = _Lines([
        _L(81, 531, 256, "ปรับแก้รูปแบบ Template Statement"),
        _L(81, 547, 268, "ปรับแก้เงื่อนไขเรื่อง VAT DIF โดยให้ KTC ใส่ค่า DIF"),
        _L(90, 563, 130, "ได้ด้วยตนเอง", tab=1),
    ])
    assert refine_line_breaks(cell, (77, 470, 300, 600)) == 2
    assert [ln.line_break for ln in cell.lines] == [1, 1, 0]

    body = _Lines([
        _L(99, 653, 439, "พิมพ์ Statement และ Tax Invoice (สำหรับงานพิมพ์ที่ต้องอยู่ใน", tab=1),
        _L(72, 670, 314, "2.1.6 Function การจัดลำดับ Priority", bold=True),
    ])
    assert refine_line_breaks(body, page) == 1

    # ย่อหน้าที่เยื้องบรรทัดแรก (บรรทัดต่อไปเยื้องออก รูปแบบเดียวกัน) — ไม่ตัด
    para = _Lines([
        _L(177, 555, 447, "มาตรา ๑๐๒ ยกเลิกโดยพระราชบัญญัติแก้ไขเพิ่มเติม"),
        _L(141, 572, 440, "ประมวลกฎหมายที่ดิน (ฉบับที่ ๒) พ.ศ. ๒๕๒๑"),
    ])
    assert refine_line_breaks(para, page) == 0


def test_table_grid_follows_cell_widths_and_integer_attrs():
    from docx.oxml.ns import qn

    from docx.shared import Twips

    from app.services.pdf2docx_fixes import fix_table_grids

    doc = Document()
    table = doc.add_table(rows=2, cols=3)          # python-docx: grid เท่ากันทุกคอลัมน์
    widths = [4224, 900, 914]
    for row in table.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = Twips(w)
    ind = table._tbl.tblPr.makeelement(qn("w:tblInd"), {qn("w:w"): "10.0", qn("w:type"): "dxa"})
    table._tbl.tblPr.append(ind)
    assert fix_table_grids(doc) == 1
    assert [int(c.get(qn("w:w"))) for c in table._tbl.tblGrid.findall(qn("w:gridCol"))] == widths
    assert ind.get(qn("w:w")) == "10"


def test_bold_numbered_heading_gets_its_own_paragraph():
    from docx.enum.text import WD_BREAK

    from app.services.pdf2docx_fixes import split_heading_paragraphs

    doc = Document()
    p = doc.add_paragraph()
    p.add_run("พิมพ์ Statement (สำหรับงานพิมพ์ Billing) ")
    p.add_run().add_break(WD_BREAK.LINE)
    h = p.add_run("2.1.6 Function การจัดลำดับ Priority")
    h.bold = True
    p.add_run().add_break(WD_BREAK.LINE)
    p.add_run("พัฒนาโปรแกรมการจัดลำดับ")
    # ย่อหน้าที่บรรทัดตัวหนาไม่ใช่เลขหัวข้อ — ไม่แตะ
    q = doc.add_paragraph()
    q.add_run("ข้อความ")
    q.add_run().add_break(WD_BREAK.LINE)
    q.add_run("หมายเหตุ").bold = True
    assert split_heading_paragraphs(doc) == 2
    texts = [x.text for x in doc.paragraphs]
    assert texts == ["พิมพ์ Statement (สำหรับงานพิมพ์ Billing) ", "2.1.6 Function การจัดลำดับ Priority",
                     "พัฒนาโปรแกรมการจัดลำดับ", "ข้อความ\nหมายเหตุ"]
