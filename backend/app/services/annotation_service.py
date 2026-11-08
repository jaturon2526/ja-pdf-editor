"""
annotation_service — สร้าง/แสดง/แก้ไข/ลบ annotation บนหน้า PDF (ข้อ 4 ของโจทย์)

รองรับ 4 ชนิดหลักที่ใช้บ่อยในงาน PDF editor:
- highlight : ทำไฮไลท์ข้อความ (ใช้ rect ครอบข้อความ) — เลือก/แก้ไข/ลบ/เปลี่ยนสีย้อนหลังได้ (ดู update_annotation)
- freetext  : กล่องข้อความอิสระ วางที่ไหนก็ได้ ไม่มีกรอบเส้นบังคับ
- rect      : กรอบสี่เหลี่ยม "ที่ใส่ข้อความข้างในได้" — ย่อ/ขยาย/แก้ข้อความ/เปลี่ยนสีกรอบได้ย้อนหลัง
              (ผู้ใช้แจ้งให้เพิ่มความสามารถนี้ — ดูหมายเหตุ "รู้จัก rect ยังไง" ด้านล่าง)
- text_note : ไอคอน comment/sticky note ที่จุดหนึ่ง — โชว์ข้อความตอน hover (ฝั่ง frontend) แก้ไข/ลบได้

เรื่องแก้ไข/ลบ/เปลี่ยนสี annotation ที่มีอยู่แล้ว (ผู้ใช้แจ้งเพิ่มในรอบก่อน): PyMuPDF ไม่มี API แก้ไข
"quad points"/ตำแหน่งของ highlight ที่วางไปแล้วตรงๆ (ต่างจาก text/rect ที่มี set_rect ปกติ) — เพื่อให้
ทุกชนิด annotation แก้ไขได้ด้วยกลไกเดียวกันสม่ำเสมอ (ย่อ/ขยาย, เปลี่ยนสี, แก้ข้อความ) จึง implement
update_annotation() แบบ "ลบของเดิมทิ้งแล้วสร้างใหม่ด้วยค่าที่ผสมระหว่างของเดิม+ค่าที่ส่งมาใหม่" — xref
จะเปลี่ยนไปหลังแก้ไขทุกครั้ง (frontend ต้องอัปเดต xref ที่เก็บไว้ในเครื่องด้วย ดู App.jsx)

เรื่อง "รู้จัก rect ยังไง" (กรอบสี่เหลี่ยมที่ใส่ข้อความได้ ย่อ/ขยาย/เปลี่ยนสีได้): เดิม rect ใช้
page.add_rect_annot() สร้าง Square annot ธรรมดา (มีแค่กรอบ ไม่มีข้อความในตัว) ผู้ใช้แจ้งว่าต้องการวาด
กรอบแล้ว "ใส่ข้อความข้างในได้ด้วย" — Square annot ของ PDF ไม่รองรับข้อความในตัวที่มองเห็นได้ (มีแค่
popup content ที่ไม่แสดงผลบนหน้า) จึงเปลี่ยนมาสร้าง rect ด้วย add_freetext_annot() เหมือน freetext
แต่เปิดเส้นขอบ (set_border) ให้เห็นเป็นกรอบชัดเจน — ผลคือทั้ง freetext และ rect ที่บันทึกจริงในไฟล์
PDF เป็นชนิด FreeText annot เหมือนกันหมด แยกไม่ออกจาก field มาตรฐานของ PDF อย่างเดียว จึงต้องแอบ
"แปะป้าย" ไว้ในฟิลด์ subject (metadata มาตรฐานของ annotation ที่ viewer ทั่วไปไม่โชว์เป็นข้อความบนหน้า)
เป็น "rect_box" ตอนสร้าง แล้วอ่านกลับมาดูใน list_annotations()/update_annotation() (ดู
_RECT_BOX_SUBJECT/_get_annot_type_name ด้านล่าง) เพื่อให้รู้ว่า FreeText annot ตัวไหนคือ "rect" ตัวไหน
คือ "freetext" ธรรมดา — ยังรองรับไฟล์เดิมที่เคยมี Square annot จริงๆ อยู่แล้วด้วย (แสดงเป็น "rect" แต่
แก้ข้อความในตัวไม่ได้ เพราะ Square annot ไม่มีข้อความให้แก้)

เรื่อง "กล่องข้อความ (freetext) ปรับ font/ขนาด/สีตัวอักษรเองได้" (ผู้ใช้แจ้งเพิ่ม): เดิมตัวหนังสือจริง
ของ freetext วาดด้วย font/ขนาดตายตัว (_ANNOT_TEXT_FONTSIZE เสมอ ไม่ว่า payload.fontsize จะส่งอะไรมา)
เพราะแค่ใช้ font default (sarabun) ผ่าน fonts.resolve_font_path(None) ตอนนี้การวาดตัวหนังสือ
รับ fontname/fontsize ที่ผู้ใช้เลือกจริง — ปัญหาคือ FreeText annot ของ PDF เอง
ไม่มีฟิลด์มาตรฐานที่ viewer อื่นอ่านชื่อ font/ขนาดที่ "เราใช้จริง" กลับมาได้ (DA string ของ annot ใช้
กับ appearance ของตัว annot เอง ซึ่งเราตั้งใจปล่อยว่างอยู่แล้ว) จึงเก็บ "fontname:fontsize" ที่ใช้จริง
ไว้ในฟิลด์ metadata "title" (ผู้แต่ง — มาตรฐาน PDF ไม่แสดงผลบนหน้า ไม่มีใครใช้อยู่แล้วในแอปนี้ เหมือน
แนวทาง subject ที่ใช้แยก rect/freetext ด้านบน) อ่านกลับมาตอน list_annotations()/update_annotation()
ผ่าน _encode_font_meta/_decode_font_meta ด้านล่าง ให้ frontend โชว์ค่า font/ขนาดปัจจุบันถูกต้องตอน
เลือกกล่องข้อความเดิมกลับมาแก้ไข — ใช้เฉพาะ freetext เท่านั้น (rect ยังคง font/ขนาดตายตัวเหมือนเดิม
เพราะผู้ใช้ขอเพิ่มความสามารถนี้ให้เฉพาะ "กล่องข้อความ" ไม่รวมกรอบสี่เหลี่ยม)

เรื่อง "ข้อความใน freetext/rect อ่านไม่ออก (ขึ้นเป็นจุดไข่ปลา ...)" (ผู้ใช้แจ้งเพิ่มหลัง deploy รอบก่อน):
PyMuPDF สร้าง appearance ของ FreeText annot เองผ่าน `add_freetext_annot()`/`Annot.update()` โดยวาด
ข้อความด้วย simple font (base-14 หรือ font ที่ฝังแบบ 1-byte encoding) เท่านั้น — ตัวอักษรที่ font/
encoding นั้นไม่มี glyph รองรับ (เช่นภาษาไทยแทบทั้งหมด) จะถูกแทนที่ด้วยจุดแทนเงียบๆ แม้จะฝัง font ไทย
เข้าไปเองด้วย `page.insert_font()` แล้วก็ตาม (ต่างจาก `page.insert_text()`/`insert_textbox()` ที่วาด
ตรงลงเนื้อหน้าซึ่งรองรับ font ที่ฝังเองแบบเต็มได้จริง) จึงเปลี่ยนวิธี: ให้ FreeText annot ของ freetext/
rect มี "เนื้อหาว่างเปล่า" เสมอ (ใช้แค่ track ตำแหน่ง/ให้คลิกเลือก-ลบ-ย้ายได้ตามกลไกเดิม + วาดกรอบเส้น
ของ rect ซึ่งไม่มีปัญหาภาษา) เนื้อหาจริงเก็บใน `annot.set_info(content=...)` และ appearance (AP) ของ
FreeText ถูกตั้งเป็น null:
- บนหน้าเว็บ ตัวหนังสือวาดโดย frontend (components/AnnotationBox.jsx) ทับตำแหน่งของ annotation
- ตอนรวมเลเยอร์ (pdf_service.optimize.flatten_pdf) เขียนลงหน้าเป็นข้อความเวกเตอร์ด้วย fpdf2 + uharfbuzz
  (_draw_annotation_text_as_pdf) — ยังเลือก/ค้นหาข้อความได้
(รุ่นก่อนวาดตัวหนังสือเป็นรูปภาพทับหน้าเอกสารทันทีที่สร้าง — ไฟล์เก่าที่ยังมีรูปนั้นอยู่ ลบด้วย
_erase_annotation_text ตาม xref ที่เก็บไว้ใน metadata "title")
"""
from __future__ import annotations

import logging
from fpdf import FPDF

import fitz  # PyMuPDF

from app.core.session import PDFSession
from app.models.schemas import AnnotationCreate, AnnotationInfo, AnnotationUpdateRequest, Rect, WordInfo
from app.services import edit_service, fonts
from app.services.pdf_service import PDFError, require_unlocked

logger = logging.getLogger("annotation_service")

_ANNOT_TYPE_NAMES = {
    fitz.PDF_ANNOT_HIGHLIGHT: "highlight",
    fitz.PDF_ANNOT_SQUARE: "rect",  # ไฟล์เก่า/ภายนอกที่มี Square annot จริงๆ อยู่แล้ว ยังอ่านมาเป็น "rect" ได้
    fitz.PDF_ANNOT_TEXT: "text_note",
}

# ป้ายกำกับใน annot "subject" (metadata มาตรฐานของ PDF ไม่แสดงผลบนหน้า) แยก FreeText annot ที่เป็น
# "กรอบสี่เหลี่ยมใส่ข้อความ" (rect) ออกจาก FreeText ธรรมดา (freetext) — ดูหมายเหตุด้านบนของไฟล์
_RECT_BOX_SUBJECT = "rect_box"

_DEFAULT_HIGHLIGHT_COLOR = (1, 0.92, 0.3)
_DEFAULT_RECT_COLOR = (0.9, 0.3, 0.15)
_DEFAULT_TEXT_COLOR = (0, 0, 0)

# ขนาด/ระยะเผื่อขอบตอนวาดข้อความจริงของ freetext/rect (ดูหมายเหตุหัวไฟล์ "ข้อความใน freetext/rect
# อ่านไม่ออก") — ใช้ font/เอนจิน fpdf2 + uharfbuzz เดียวกับ edit_service.replace_text
_ANNOT_TEXT_FONTSIZE = 11.0
_ANNOT_TEXT_INSET = 3.0


def _get_annot_type_name(annot: "fitz.Annot") -> str:
    base = annot.type[0]
    if base == fitz.PDF_ANNOT_FREE_TEXT:
        info = annot.info or {}
        if info.get("subject") == _RECT_BOX_SUBJECT:
            return "rect"
        return "freetext"
    return _ANNOT_TYPE_NAMES.get(base, f"other({annot.type[1]})")


def _get_annot_color(annot: "fitz.Annot") -> tuple[float, float, float] | None:
    try:
        colors = annot.colors or {}
        stroke = colors.get("stroke")
        if stroke:
            return tuple(stroke)
    except Exception:
        pass
    return None


def _decode_font_meta_legacy(raw: str | None) -> tuple[str | None, float | None]:
    """แกะค่า font/ขนาดตัวอักษรแบบรูปแบบเดิม (ก่อนรอบนี้) "<fontname>:<fontsize>" ไม่มี xref ต่อท้าย —
    ใช้เป็น fallback อ่าน title metadata ของ annotation ที่สร้างไว้ก่อนฟีเจอร์ "ลบข้อความด้วย xref แม่นยำ"
    ด้านล่าง (ดูหมายเหตุ _encode_annot_meta/_decode_annot_meta) คืน (None, None) ถ้า title ว่าง/ไม่ใช่
    รูปแบบที่คาดไว้ ไม่ error ในทุกกรณี
    """
    if not raw or ":" not in raw:
        return None, None
    name, _, size_str = raw.rpartition(":")
    if not name:
        return None, None
    try:
        return name, float(size_str)
    except ValueError:
        return name, None


def _encode_annot_meta(image_xrefs: list[int], fontname: str | None = None, fontsize: float | None = None) -> str:
    """เก็บ (1) font/ขนาดตัวอักษรจริงของกล่องข้อความ (freetext เท่านั้น — ดูหมายเหตุหัวไฟล์) และ (2)
    xref ของรูปภาพที่รุ่นก่อนวาดทับหน้าเอกสารจริง (ทั้ง freetext และ rect) ไว้ในฟิลด์
    metadata "title" ของ annot ฟิลด์เดียวกัน (แทนที่จะเดาสีพื้นหลังตอนลบ — ดูหมายเหตุ _erase_annotation_text
    ด้านล่างว่าทำไมต้อง track xref แม่นยำแทนการสุ่มสี) รูปแบบ "<fontname>:<fontsize>|<xref1>,<xref2>,..."
    (ส่วนก่อน "|" ว่างได้สำหรับ rect ที่ไม่มี font meta) xref เหล่านี้อยู่ในไฟล์ PDF เอง (ไม่ใช่ state
    ฝั่ง Python) จึงรอดจากการโหลด byte snapshot ใหม่ตอน undo/redo (xref คงเดิมเพราะเป็นไฟล์ไบต์เดียวกัน)
    """
    font_part = f"{fontname}:{fontsize:g}" if fontname and fontsize is not None else ""
    xref_part = ",".join(str(x) for x in image_xrefs) if image_xrefs else ""
    return f"{font_part}|{xref_part}"


def _decode_annot_meta(raw: str | None) -> tuple[str | None, float | None, list[int]]:
    """แกะค่ากลับจาก _encode_annot_meta — คืน (fontname, fontsize, image_xrefs) รองรับ annotation เก่า
    ที่ยังเป็นรูปแบบก่อนรอบนี้ (ไม่มี "|" เลย เพราะสร้างไว้ก่อนมีการ track xref) โดย fallback ไปแกะแบบเดิม
    ด้วย _decode_font_meta_legacy และคืน image_xrefs เป็น [] (ให้ _erase_annotation_text รู้ว่าต้องใช้วิธี
    เดิม/redact แทน เพราะไม่มี xref ให้ลบตรงๆ) ไม่ error ในทุกกรณี
    """
    if not raw:
        return None, None, []
    if "|" not in raw:
        name, size = _decode_font_meta_legacy(raw)
        return name, size, []
    font_part, _, xref_part = raw.partition("|")
    fontname, fontsize = _decode_font_meta_legacy(font_part) if font_part else (None, None)
    image_xrefs: list[int] = []
    for tok in xref_part.split(","):
        tok = tok.strip()
        if tok.isdigit():
            image_xrefs.append(int(tok))
    return fontname, fontsize, image_xrefs


def _get_annot_meta(annot: "fitz.Annot") -> tuple[str | None, float | None, list[int]]:
    """คืน (fontname, fontsize, image_xrefs) ปัจจุบันของ annotation จากฟิลด์ title — fontname/fontsize
    มีความหมายเฉพาะ freetext (rect ไม่เคยเข้ารหัส font ไว้ จึงได้ None, None เสมอโดยธรรมชาติของรูปแบบ
    ไม่ต้องเช็คชนิดแยก) ส่วน image_xrefs ใช้ได้ทั้ง freetext และ rect
    """
    info = annot.info or {}
    return _decode_annot_meta(info.get("title"))


def _draw_annotation_text_as_pdf(
    rect: "fitz.Rect",
    text: str,
    color: tuple[float, float, float],
    fontname: str | None = None,
    fontsize: float | None = None,
    user_id: int | None = None,
) -> tuple["fitz.Document", "fitz.Rect"] | None:
    """ตัวหนังสือของกล่องข้อความ/กรอบ (freetext/rect) เป็น PDF เวกเตอร์หนึ่งหน้า (fpdf2 + uharfbuzz จัดรูปไทย)
    คืน (เอกสาร, กรอบปลายทางบนหน้า) ให้ flatten_pdf วางด้วย show_pdf_page — ข้อความยังเลือก/ค้นหาได้"""
    if not text.strip():
        return None
    _, font_path = fonts.resolve_font_path(fontname, user_id=user_id)
    if not font_path:
        return None

    size = fontsize or _ANNOT_TEXT_FONTSIZE
    usable_width = max(rect.width - 2 * _ANNOT_TEXT_INSET, 10.0)
    wrapped_lines = edit_service._wrap_text(text, font_path, size, usable_width)

    headroom_pt = size * 1.2
    
    num_lines = len([l for l in wrapped_lines if l.strip()])
    if num_lines == 0:
        return None

    last_baseline = headroom_pt + (num_lines - 1) * (size * edit_service._LINE_HEIGHT_RATIO)
    micro_height = last_baseline + size * 0.5
    micro_width = usable_width + 2 * _ANNOT_TEXT_INSET

    # สร้าง Micro-PDF
    pdf = FPDF(format=(micro_width, micro_height), unit="pt")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.add_font("Custom", "", font_path)
    pdf.set_font("Custom", size=size)
    r, g, b = [max(0, min(255, int(c * 255))) for c in color]
    pdf.set_text_color(r, g, b)
    
    pdf.set_text_shaping(True, script="thai", language="tha")

    line_count = 0
    for line_text in wrapped_lines:
        if not line_text.strip():
            continue
        micro_baseline_y = headroom_pt + line_count * size * edit_service._LINE_HEIGHT_RATIO
        line_x = _ANNOT_TEXT_INSET
        pdf.c_margin = 0
        pdf.set_xy(line_x, micro_baseline_y - 0.3 * size)
        pdf.cell(w=0, h=0, text=line_text, align="L")
        line_count += 1

    overlay_y0 = (rect.y0 + _ANNOT_TEXT_INSET + size * 0.85) - headroom_pt
    micro_pdf_bytes = pdf.output()
    import fitz
    micro_doc = fitz.open("pdf", micro_pdf_bytes)
    overlay_rect = fitz.Rect(rect.x0, overlay_y0, rect.x0 + micro_width, overlay_y0 + micro_height)
    
    return micro_doc, overlay_rect


# ---------- appearance stream (AP) ของกล่องข้อความ/กรอบ ----------
# เดิม FreeText ของแอปตั้ง AP เป็น null และวาดตัวหนังสือฝั่งเว็บเท่านั้น: ไฟล์ที่ดาวน์โหลดไปเปิดใน Chrome/Edge/
# Acrobat/Preview ข้อความไทยในกล่องข้อความหายหมด (เหลือแต่ตัวอังกฤษ) และข้อความในกรอบสี่เหลี่ยมไม่ขึ้นเลย
# ตอนนี้สร้าง AP เองด้วย fpdf2 + uharfbuzz (ฟอนต์ไทยฝังจริง เหมือนตอนรวมเลเยอร์) — ทุกโปรแกรมเห็นเหมือนกัน
# หน้าเว็บก็แสดงจากรูปหน้าเอกสารที่ render แล้ว (ไม่ต้องวาดทับ) · _AP_MARK บอกว่า AP นี้เป็นของแอปที่มีข้อความแล้ว
_AP_MARK = "JAPdfTextAP"
_RECT_BORDER_WIDTH = 1.5


def _appearance_pdf(rect: "fitz.Rect", text: str, color, fontname: str | None, fontsize: float | None,
                    border_color=None, user_id: int | None = None) -> "fitz.Document":
    """PDF หนึ่งหน้าขนาดเท่ากรอบพอดี: ข้อความ (ตำแหน่งบรรทัดเดียวกับ _draw_annotation_text_as_pdf) + เส้นกรอบ (rect)"""
    w, h = max(rect.width, 1.0), max(rect.height, 1.0)
    pdf = FPDF(format=(w, h), unit="pt")
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)
    pdf.add_page()
    if border_color is not None:
        r, g, b = [max(0, min(255, int(c * 255))) for c in border_color]
        pdf.set_draw_color(r, g, b)
        pdf.set_line_width(_RECT_BORDER_WIDTH)
        half = _RECT_BORDER_WIDTH / 2
        pdf.rect(half, half, max(w - _RECT_BORDER_WIDTH, 0.5), max(h - _RECT_BORDER_WIDTH, 0.5))
    _, font_path = fonts.resolve_font_path(fontname, user_id=user_id) if text.strip() else (None, None)
    if text.strip() and font_path:
        size = fontsize or _ANNOT_TEXT_FONTSIZE
        usable = max(w - 2 * _ANNOT_TEXT_INSET, 10.0)
        pdf.add_font("Custom", "", font_path)
        pdf.set_font("Custom", size=size)
        r, g, b = [max(0, min(255, int(c * 255))) for c in (color or _DEFAULT_TEXT_COLOR)]
        pdf.set_text_color(r, g, b)
        pdf.set_text_shaping(True, script="thai", language="tha")
        pdf.c_margin = 0
        i = 0
        for line in edit_service._wrap_text(text, font_path, size, usable):
            if not line.strip():
                continue
            baseline = _ANNOT_TEXT_INSET + 0.85 * size + i * size * edit_service._LINE_HEIGHT_RATIO
            if baseline - size > h:
                break  # ล้นกรอบ (กรอบสี่เหลี่ยมที่ผู้ใช้ลากเล็กกว่าข้อความ) — ส่วนที่เหลือถูกตัดอยู่แล้ว
            pdf.set_xy(_ANNOT_TEXT_INSET, baseline - 0.3 * size)
            pdf.cell(w=0, h=0, text=line, align="L")
            i += 1
    return fitz.open("pdf", pdf.output())


def _set_text_appearance(page: "fitz.Page", annot: "fitz.Annot", text: str, color, fontname, fontsize,
                         border_color=None, user_id: int | None = None) -> int:
    """ตั้ง AP ของ annotation เป็นข้อความ/กรอบที่วาดเอง (นำเข้าเป็น Form XObject ผ่านหน้าชั่วคราว) คืน xref ของ annot

    หมายเหตุ: เพิ่ม/ลบหน้าชั่วคราวทำให้ object Page/Annot เดิมของ PyMuPDF ใช้ไม่ได้ — ผู้เรียกห้ามใช้ page/annot ต่อ
    (ใช้ xref ที่คืนไป แล้ว load ใหม่)"""
    doc = page.parent
    xref = annot.xref
    rect = fitz.Rect(annot.rect)
    flags = annot.flags
    micro = _appearance_pdf(rect, text or "", color, fontname, fontsize, border_color, user_id)
    tmp = doc.new_page(width=micro[0].rect.width, height=micro[0].rect.height)
    try:
        tmp.show_pdf_page(tmp.rect, micro, 0)
        outer = [x for x in tmp.get_xobjects() if x[2] == 0]
        if not outer:
            raise PDFError("สร้างภาพของกล่องข้อความไม่สำเร็จ")
        form_xref = outer[0][0]
    finally:
        doc.delete_page(doc.page_count - 1)
        micro.close()
    doc.xref_set_key(xref, "AP", f"<</N {form_xref} 0 R>>")
    doc.xref_set_key(xref, _AP_MARK, "true")
    doc.xref_set_key(xref, "F", str((flags | fitz.PDF_ANNOT_IS_PRINT) & ~fitz.PDF_ANNOT_IS_HIDDEN))
    return xref


def _is_app_text_annot(annot: "fitz.Annot") -> bool:
    t = _get_annot_type_name(annot)
    if t == "freetext":
        doc = annot.parent.parent
        ap = doc.xref_get_key(annot.xref, "AP")
        return ap[0] in ("null", "none") or doc.xref_get_key(annot.xref, _AP_MARK)[0] != "null"
    return t == "rect" and (annot.info or {}).get("subject") == _RECT_BOX_SUBJECT


def ensure_text_appearances(doc: "fitz.Document", pages=None, user_id: int | None = None) -> bool:
    """สร้าง AP ให้กล่องข้อความ/กรอบของแอปที่ยังไม่มี (สร้างไว้ก่อนเวอร์ชันนี้) — คืน True ถ้ามีการเปลี่ยน
    FreeText จากโปรแกรมอื่นที่มี AP อยู่แล้วไม่ถูกแตะ (เดิม render ทุกครั้งลบ AP ของมันทิ้ง ข้อความหายในไฟล์ที่ดาวน์โหลด)"""
    changed = False
    for pno in (range(doc.page_count) if pages is None else pages):
        page = doc[pno]
        todo = []
        for annot in page.annots() or []:
            if not _is_app_text_annot(annot) or doc.xref_get_key(annot.xref, _AP_MARK)[0] != "null":
                continue
            fontname, fontsize, _ = _get_annot_meta(annot)
            t = _get_annot_type_name(annot)
            todo.append((annot.xref, (annot.info or {}).get("content") or "", _get_annot_color(annot),
                         fontname, fontsize, t))
        for xref, content, color, fontname, fontsize, t in todo:
            page = doc[pno]  # หน้าชั่วคราวใน _set_text_appearance ทำให้ object เดิมใช้ไม่ได้
            annot = page.load_annot(xref)
            if annot is None:
                continue
            if t == "rect":
                _set_text_appearance(page, annot, content, _DEFAULT_TEXT_COLOR, None, None,
                                     border_color=color or _DEFAULT_RECT_COLOR, user_id=user_id)
            else:
                _set_text_appearance(page, annot, content, color or _DEFAULT_TEXT_COLOR, fontname,
                                     fontsize or 12, user_id=user_id)
            changed = True
    return changed


def _fit_text_height(rect: "fitz.Rect", text: str, font_path: str | None, size: float,
                     page_bottom: float, grow_only: bool = False) -> "fitz.Rect":
    """ความสูงกรอบที่พอดีกับข้อความของกล่องข้อความ — ใช้ตำแหน่งบรรทัดเดียวกับ _draw_annotation_text_as_pdf
    (บรรทัดแรกที่ inset + 0.85·size, บรรทัดถัดไปห่าง _LINE_HEIGHT_RATIO·size, เผื่อสระล่าง/หาง 0.4·size)
    grow_only: ขยายเมื่อข้อความล้นเท่านั้น ไม่หดกรอบที่ผู้ใช้ลากไว้ใหญ่กว่า"""
    lines = 1
    if text.strip() and font_path:
        usable_width = max(rect.width - 2 * _ANNOT_TEXT_INSET, 10.0)
        wrapped = edit_service._wrap_text(text, font_path, size, usable_width)
        lines = max(1, len([ln for ln in wrapped if ln.strip()]))
    needed = 2 * _ANNOT_TEXT_INSET + 1.25 * size + (lines - 1) * size * edit_service._LINE_HEIGHT_RATIO
    if grow_only and rect.height >= needed:
        return rect
    y1 = min(rect.y0 + needed, max(page_bottom, rect.y0 + size))
    return fitz.Rect(rect.x0, rect.y0, rect.x1, y1)


def _erase_annotation_text(page: "fitz.Page", rect: "fitz.Rect", image_xrefs: list[int] | None = None) -> None:
    """ลบรูปตัวหนังสือที่รุ่นก่อนวาดทับหน้าเอกสาร (ไฟล์ที่สร้าง annotation ไว้ก่อนเลิกวาดเป็นรูป) ในกรอบเดิมทิ้ง — เรียกก่อนลบ/ก่อนวาดใหม่ทุกครั้งที่
    annotation ชนิด freetext/rect ถูกลบหรือแก้ไข (ย้าย/ปรับขนาด/เปลี่ยนสี/แก้ข้อความ) ไม่งั้นข้อความเก่า
    จะค้างอยู่บนหน้าเอกสาร (ข้อความนี้ไม่ใช่ appearance ของ annotation จึงไม่หายไปเองตอนลบ annotation)

    (ผู้ใช้แจ้งบั๊ก): วิธีเดิมใช้ redact ทั้งกรอบด้วยสีพื้นหลังที่ "เดา" จากมุมกรอบ (ไล่สีเดียวทั้งกรอบ)
    ถ้ากรอบ annotation คาบเกี่ยวรอยต่อสี/พื้นหลังในหน้าเอกสาร (เช่น แถบสีชมพูต่อกับพื้นขาว) การ fill
    สีเดียวทั้งกรอบจะทำให้เกิดเป็นแผ่นสีที่ผิดเพี้ยนไปจากพื้นหลังจริง (เช่น เห็นเป็นแผ่นสีขาวทับพื้นที่ควร
    เป็นสีชมพู) จึงเปลี่ยนมาลบเฉพาะรูปภาพที่วาดไปจริงๆ ทีละรูปด้วย page.delete_image(xref) แทน (xref มา
    จากการวาดรุ่นก่อน เก็บไว้ใน metadata ของ annot — ดู _encode_annot_meta/_get_annot_meta)
    ซึ่งจะเผยเนื้อหาเดิมที่อยู่ใต้รูปในลำดับการวาดของหน้าออกมาได้ตรงๆ แม่นยำ ไม่กระทบเนื้อหาอื่นบนหน้าเลย

    image_xrefs ว่าง/None ได้สำหรับ annotation เก่าที่สร้างไว้ก่อนฟีเจอร์นี้ (title ยังเป็นรูปแบบเดิม ไม่มี
    xref ให้ลบตรงๆ) — กรณีนี้ fallback กลับไปใช้วิธี redact+สุ่มสีแบบเดิม (ยังดีกว่าปล่อยข้อความเก่าค้าง)
    """
    if image_xrefs is not None:
        try:
            for xref in image_xrefs:
                page.delete_image(xref)
            return
        except Exception:
            logger.warning(
                "ลบรูปข้อความเดิมด้วย xref ไม่สำเร็จ (rect=%s, xrefs=%s) จะลองใช้วิธี redact แทน",
                rect,
                image_xrefs,
                exc_info=True,
            )

    try:
        padded = fitz.Rect(rect.x0 - 4, rect.y0 - 4, rect.x1 + 4, rect.y1 + 4)
        bg_color = edit_service._sample_background_color(page, rect)
        page.add_redact_annot(padded, fill=bg_color)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    except Exception:
        logger.warning("ลบข้อความเดิมของ annotation ไม่สำเร็จ (rect=%s)", rect, exc_info=True)


def _highlight_quad(page: "fitz.Page", rect: "fitz.Rect"):
    """กรอบไฮไลต์ → quad ที่หันตามทิศของข้อความใต้กรอบ

    MuPDF วาดไฮไลต์โดยถือว่าด้าน ul→ur คือแนวบรรทัด และใช้ "ความสูง" ของ quad ทำปลายมน — ข้อความแนวตั้ง
    (หน้าที่หมุน 90/270) ถ้าส่งเป็นสี่เหลี่ยมธรรมดา ไฮไลต์จะออกมาเป็นวงรีอ้วนกว่าตัวอักษรมาก จึงหันมุมของ quad ตาม
    ทิศบรรทัด (line["dir"]) ที่ซ้อนกับกรอบมากที่สุด — ข้อความแนวนอนปกติคืนสี่เหลี่ยมเดิม"""
    best, best_area = None, 0.0
    try:
        blocks = page.get_text("dict", clip=rect + (-2, -2, 2, 2)).get("blocks", [])
    except Exception:
        return rect
    for block in blocks:
        for line in block.get("lines", []):
            area = (fitz.Rect(line["bbox"]) & rect).get_area()
            if area > best_area:
                best, best_area = line.get("dir", (1, 0)), area
    if best is None:
        return rect
    dx, dy = round(best[0]), round(best[1])
    r = rect
    if (dx, dy) == (0, 1):     # บรรทัดวิ่งลง (หน้าที่หมุน 90°) — ด้านบนของตัวอักษรหันไปทางขวา
        return fitz.Quad(fitz.Point(r.x1, r.y0), fitz.Point(r.x1, r.y1), fitz.Point(r.x0, r.y0), fitz.Point(r.x0, r.y1))
    if (dx, dy) == (0, -1):    # บรรทัดวิ่งขึ้น (หมุน 270°)
        return fitz.Quad(fitz.Point(r.x0, r.y1), fitz.Point(r.x0, r.y0), fitz.Point(r.x1, r.y1), fitz.Point(r.x1, r.y0))
    if (dx, dy) == (-1, 0):    # กลับหัว (หมุน 180°)
        return fitz.Quad(fitz.Point(r.x1, r.y1), fitz.Point(r.x0, r.y1), fitz.Point(r.x1, r.y0), fitz.Point(r.x0, r.y0))
    return rect


def add_annotation(session: PDFSession, payload: AnnotationCreate, grow_to_fit: bool = False) -> AnnotationInfo:
    """grow_to_fit: (ใช้ตอนแก้ไข) กล่องข้อความที่ข้อความ/ฟอนต์เปลี่ยนจนล้นกรอบ ขยายกรอบลงให้พอดี"""
    doc = require_unlocked(session)
    if not (0 <= payload.page_number < doc.page_count):
        raise PDFError(f"page_number {payload.page_number} อยู่นอกช่วง")

    page = doc[payload.page_number]
    # กรอบกลับด้าน (ลากจากขวาล่างไปซ้ายบน) / ล้นนอกหน้า / เล็กเป็นศูนย์ — เดิม MuPDF error เป็น 500
    rect = fitz.Rect(payload.rect.x0, payload.rect.y0, payload.rect.x1, payload.rect.y1).normalize()
    if payload.type == "text_note":
        x = min(max(rect.x0, page.rect.x0), page.rect.x1 - 20)
        y = min(max(rect.y0, page.rect.y0), page.rect.y1 - 20)
        rect = fitz.Rect(x, y, x + 20, y + 20)
    else:
        rect = rect & page.rect
        if rect.is_empty or rect.width < 1 or rect.height < 1:
            raise PDFError("กรอบเล็กเกินไป หรืออยู่นอกหน้ากระดาษ — ลากให้ใหญ่ขึ้น")
    content = payload.content or ""
    result_color: tuple[float, float, float]
    result_fontname: str | None = None
    result_fontsize: float | None = None

    if payload.type == "highlight":
        color = payload.color or _DEFAULT_HIGHLIGHT_COLOR
        quads = [_highlight_quad(page, r) for r in (
            (fitz.Rect(lr.x0, lr.y0, lr.x1, lr.y1).normalize() & page.rect) for lr in (payload.line_rects or [])
        ) if not r.is_empty] or [_highlight_quad(page, rect)]
        annot = page.add_highlight_annot(quads)
        annot.set_colors(stroke=color)
        annot.set_opacity(0.8)
        try:
            annot.set_blendmode(fitz.PDF_BM_Multiply)
        except Exception:
            pass
        annot.update()
        annot_xref = annot.xref
        rect = fitz.Rect(annot.rect)
        result_color = color

    elif payload.type == "freetext":
        color = payload.color or _DEFAULT_TEXT_COLOR
        font_key, font_path = fonts.resolve_font_path(payload.fontname, user_id=session.user_id)
        size = payload.fontsize or _ANNOT_TEXT_FONTSIZE
        if payload.auto_height or grow_to_fit:
            rect = _fit_text_height(rect, content, font_path, size, page.rect.y1, grow_only=not payload.auto_height)

        annot = page.add_freetext_annot(rect, content or "", fontsize=size, text_color=color)
        annot.set_border(width=0)
        annot.update(border_color=None, fill_color=None, text_color=color)
        
        annot.set_info(content=content, title=_encode_annot_meta([], fontname=font_key, fontsize=size))
        annot_xref = _set_text_appearance(page, annot, content, color, font_key, size, user_id=session.user_id)
        result_color = color
        result_fontname = font_key
        result_fontsize = size

    elif payload.type == "rect":
        color = payload.color or _DEFAULT_RECT_COLOR
        annot = page.add_rect_annot(rect)
        annot.set_border(width=1.5)
        annot.set_colors(stroke=color)
        annot.update(border_color=color, fill_color=None)
        
        annot.set_info(subject=_RECT_BOX_SUBJECT, content=content, title=_encode_annot_meta([]))
        # AP = เส้นกรอบ + ข้อความข้างใน (เดิม AP มีแต่เส้นกรอบ ข้อความไม่อยู่ในไฟล์ที่ดาวน์โหลด/รวมเลเยอร์เลย)
        annot_xref = _set_text_appearance(page, annot, content, _DEFAULT_TEXT_COLOR, None, None,
                                          border_color=color, user_id=session.user_id)
        result_color = color

    elif payload.type == "text_note":
        color = payload.color or _DEFAULT_HIGHLIGHT_COLOR
        annot = page.add_text_annot(rect.tl, content)
        try:
            annot.set_colors(stroke=color)
        except Exception:
            pass
        annot.set_name("Note")
        annot.set_info(content=content)
        annot.update()
        annot_xref = annot.xref
        result_color = color

    else:
        raise PDFError(f"ไม่รู้จักชนิด annotation: {payload.type}")

    session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดูหมายเหตุ _doc_dirty ใน session.py
    return AnnotationInfo(
        xref=annot_xref,
        page_number=payload.page_number,
        type=payload.type,
        rect=Rect(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1),
        content=payload.content,
        color=result_color,
        fontname=result_fontname,
        fontsize=result_fontsize,
    )


def list_annotations(session: PDFSession, page_number: int) -> list[AnnotationInfo]:
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    page = doc[page_number]
    results: list[AnnotationInfo] = []
    for annot in page.annots():
        rect = annot.rect
        type_name = _get_annot_type_name(annot)
        info = annot.info or {}
        fontname, fontsize, _image_xrefs = _get_annot_meta(annot)
        results.append(
            AnnotationInfo(
                xref=annot.xref,
                page_number=page_number,
                type=type_name,
                rect=Rect(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1),
                content=info.get("content"),
                color=_get_annot_color(annot),
                fontname=fontname,
                fontsize=fontsize,
            )
        )
    return results


def get_words(session: PDFSession, page_number: int) -> list[WordInfo]:
    """คืนทุกคำในหน้าพร้อมตำแหน่งและ line_key (block_no-line_no) — ให้ frontend ใช้คำนวณตอนผู้ใช้
    "ลากเลือก" พื้นที่ด้วยเมาส์ (เครื่องมือไฮไลท์/โน้ต) ว่าครอบคำไหนบ้าง แล้ว snap เป็นกรอบรวมทีละบรรทัด
    (ดูหมายเหตุใน WordInfo) ผลคือไฮไลท์/โน้ตจะเกาะติดข้อความจริงเสมอ ไม่ใช่กรอบดิบตามพิกัดที่ลากเป๊ะๆ
    """
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    page = doc[page_number]
    results: list[WordInfo] = []
    # จัดรูปข้อความไทยทีละอักขระ (ตัวที่ถูกรวมเป็น "" แล้วถูกข้ามด้านล่าง) — กรอบของแต่ละตัวยังตรงตำแหน่งเดิม
    from app.services import thai_text

    raw_dict = thai_text.normalize_page_dict(page.get_text("rawdict"), page)
    for block_no, block in enumerate(raw_dict.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for line_no, line in enumerate(block.get("lines", [])):
            for span in line.get("spans", []):
                for char in span.get("chars", []):
                    c = char.get("c", "")
                    if not c.strip():
                        continue
                    bbox = char.get("bbox")
                    results.append(
                        WordInfo(
                            rect=Rect(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
                            text=c,
                            line_key=f"{block_no}-{line_no}",
                        )
                    )
    return results


def delete_annotation(session: PDFSession, page_number: int, xref: int) -> bool:
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    page = doc[page_number]
    for annot in page.annots():
        if annot.xref == xref:
            type_name = _get_annot_type_name(annot)
            rect = fitz.Rect(annot.rect)
            _, _, image_xrefs = _get_annot_meta(annot)
            page.delete_annot(annot)
            if type_name in ("freetext", "rect"):
                # ลบ annotation อย่างเดียวไม่พอ — ต้องลบข้อความที่วาดแยกทับหน้าเอกสารเองด้วย (ดู
                # หมายเหตุหัวไฟล์) ไม่งั้นตัวหนังสือรุ่นเก่าจะค้างอยู่
                _erase_annotation_text(page, rect, image_xrefs)
            session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดู _doc_dirty ใน session.py
            return True
    return False


def update_annotation(session: PDFSession, payload: AnnotationUpdateRequest) -> AnnotationInfo:
    """แก้ไข annotation ที่มีอยู่แล้ว — ย่อ/ขยาย (rect ใหม่), เปลี่ยนสี, และ/หรือแก้ข้อความ (สำหรับ
    rect/freetext/text_note) ฟิลด์ที่ไม่ได้ส่งมาใน payload จะคงค่าเดิมไว้ทุกอย่าง

    วิธีทำ (ดูหมายเหตุ "เรื่องแก้ไข/ลบ/เปลี่ยนสี" ที่หัวไฟล์): อ่านค่าปัจจุบันของ annot เดิมไว้ก่อน
    (ชนิด/ตำแหน่ง/ข้อความ/สี) แล้วลบทิ้ง จากนั้นสร้างใหม่ผ่าน add_annotation() ด้วยค่าที่ผสมระหว่าง
    ของเดิม (ฟิลด์ที่ไม่ได้ส่งมา) กับค่าใหม่ (ฟิลด์ที่ส่งมาใน payload) — ได้ xref ใหม่เสมอ

    สำหรับ freetext/rect ต้องลบข้อความที่วาดแยกทับหน้าเอกสารเอง (ตำแหน่ง/กรอบเดิม) ทิ้งก่อนด้วย (ดู
    _erase_annotation_text) ไม่งั้นข้อความเก่าจะค้างอยู่ซ้อนกับข้อความใหม่ที่ add_annotation() วาดให้
    """
    doc = require_unlocked(session)
    if not (0 <= payload.page_number < doc.page_count):
        raise PDFError(f"page_number {payload.page_number} อยู่นอกช่วง")

    page = doc[payload.page_number]
    target = None
    for annot in page.annots():
        if annot.xref == payload.xref:
            target = annot
            break
    if target is None:
        raise PDFError(f"ไม่พบ annotation ตาม xref={payload.xref} ในหน้า {payload.page_number}")

    old_type = _get_annot_type_name(target)
    if old_type not in ("highlight", "freetext", "rect", "text_note"):
        raise PDFError(f"annotation ชนิดนี้ ({old_type}) ยังไม่รองรับการแก้ไข")
    old_rect = fitz.Rect(target.rect)
    old_info = target.info or {}
    old_content = old_info.get("content")
    old_color = _get_annot_color(target)
    old_fontname, old_fontsize, old_image_xrefs = _get_annot_meta(target)

    # ไฮไลต์/โน้ตที่ไม่ได้ย้าย: แก้ในที่เดิม — เดิมลบแล้วสร้างใหม่จากกรอบรวม ไฮไลต์หลายบรรทัด (จากโปรแกรมอื่น)
    # กลายเป็นแถบสี่เหลี่ยมทึบทับทั้งย่อหน้า และโน้ตเสียตำแหน่ง popup/ผู้เขียน
    if payload.rect is None and old_type in ("highlight", "text_note"):
        if payload.color is not None:
            target.set_colors(stroke=payload.color)
        if payload.content is not None and old_type == "text_note":
            target.set_info(content=payload.content)
        target.update()
        session.mark_dirty()
        return AnnotationInfo(
            xref=target.xref, page_number=payload.page_number, type=old_type,
            rect=Rect(x0=old_rect.x0, y0=old_rect.y0, x1=old_rect.x1, y1=old_rect.y1),
            content=payload.content if payload.content is not None else old_content,
            color=payload.color if payload.color is not None else old_color,
        )

    page.delete_annot(target)
    if old_type in ("freetext", "rect"):
        _erase_annotation_text(page, old_rect, old_image_xrefs)

    new_rect = (
        Rect(x0=payload.rect.x0, y0=payload.rect.y0, x1=payload.rect.x1, y1=payload.rect.y1)
        if payload.rect is not None
        else Rect(x0=old_rect.x0, y0=old_rect.y0, x1=old_rect.x1, y1=old_rect.y1)
    )
    new_color = payload.color if payload.color is not None else old_color
    new_content = payload.content if payload.content is not None else old_content
    # font/ขนาดตัวอักษร — เฉพาะ freetext เท่านั้นที่มีค่าเดิมให้คงไว้ (ดูหมายเหตุหัวไฟล์) ฟิลด์ที่ไม่ได้
    # ส่งมาใหม่ใน payload จะคงค่าเดิมไว้เหมือนฟิลด์อื่นๆ ทั้งหมดในฟังก์ชันนี้
    new_fontname = payload.fontname if payload.fontname is not None else old_fontname
    new_fontsize = payload.fontsize if payload.fontsize is not None else old_fontsize

    create_payload = AnnotationCreate(
        page_number=payload.page_number,
        type=old_type,
        rect=new_rect,
        content=new_content,
        color=new_color,
        fontsize=new_fontsize or 12,
        fontname=new_fontname,
    )
    text_changed = (payload.content is not None and payload.content != old_content) or \
        (payload.fontsize is not None and payload.fontsize != old_fontsize) or \
        (payload.fontname is not None and payload.fontname != old_fontname)
    return add_annotation(session, create_payload, grow_to_fit=old_type == "freetext" and text_changed)
