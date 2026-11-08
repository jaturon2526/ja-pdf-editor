"""ใส่เลขหน้า — ข้อความจริงในไฟล์ (ค้นหา/คัดลอกได้) วาดด้วย fpdf2 + uharfbuzz (สระ/วรรณยุกต์ไทยถูกต้อง)
แล้ววางทับหน้าด้วย show_pdf_page เหมือนการแก้ไขข้อความ

ค่าเริ่มต้นตามที่ผู้ใช้กำหนด:
- เริ่มใส่ที่หน้า start_page → หน้านั้นขึ้นเลข start_number (ค่าเริ่มต้น 1 — หน้าที่ไม่ใส่ไม่นับ)
- จำนวนหน้าทั้งหมด (N ใน "1/N") = เลขของหน้าสุดท้ายที่ใส่ (start_number = 1 → นับเฉพาะหน้าที่ใส่เลข)
- หน้าคู่สลับข้าง (mirror_even) ใช้ลำดับหน้าจริงในไฟล์: หน้าคี่อยู่ฝั่งที่เลือก หน้าคู่อยู่ฝั่งตรงข้าม (พิมพ์สองหน้า)
- หน้าที่หมุน (/Rotate) วางตามที่ผู้ใช้มองเห็น"""
from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF
from fpdf import FPDF

from app.core.session import PDFSession
from app.services import fonts
from app.services.pdf_service import PDFError, require_unlocked

_THAI_DIGITS = str.maketrans("0123456789", "๐๑๒๓๔๕๖๗๘๙")
FORMATS = ("n", "n_total")
H_POSITIONS = ("left", "center", "right")
V_POSITIONS = ("top", "bottom")


@dataclass
class PageNumberOptions:
    fmt: str = "n"                 # "n" = 1, 2, 3 · "n_total" = 1/9
    separator: str = "/"
    prefix: str = ""
    suffix: str = ""
    thai_digits: bool = False
    start_page: int = 1            # หน้าแรกที่ใส่ (นับจาก 1)
    end_page: int | None = None    # หน้าสุดท้ายที่ใส่ (None = หน้าสุดท้ายของไฟล์)
    start_number: int = 1          # เลขที่แสดงบนหน้า start_page
    vpos: str = "bottom"
    hpos: str = "center"
    mirror_even: bool = False      # หน้าคู่ (ลำดับจริง) วางฝั่งตรงข้าม — ใช้เมื่อ hpos เป็น left/right
    margin_pt: float = 28.0        # ระยะจากขอบกระดาษ
    font_size: float = 11.0
    color: tuple[float, float, float] = (0.2, 0.2, 0.2)
    font: str = "sarabun"


def format_label(number: int, total: int, opts: PageNumberOptions) -> str:
    text = str(number) if opts.fmt == "n" else f"{number}{opts.separator}{total}"
    text = f"{opts.prefix}{text}{opts.suffix}"
    return text.translate(_THAI_DIGITS) if opts.thai_digits else text


def page_plan(page_count: int, opts: PageNumberOptions) -> list[tuple[int, str, str]]:
    """[(index หน้า 0-based, ข้อความ, ฝั่ง left/center/right)] — แยกไว้ให้หน้าเว็บพรีวิว/ทดสอบได้"""
    if opts.fmt not in FORMATS or opts.hpos not in H_POSITIONS or opts.vpos not in V_POSITIONS:
        raise PDFError("ตัวเลือกเลขหน้าไม่ถูกต้อง")
    first = max(1, int(opts.start_page))
    last = min(page_count, int(opts.end_page or page_count))
    if first > page_count:
        raise PDFError(f"เอกสารมี {page_count} หน้า — เริ่มที่หน้า {first} ไม่ได้")
    if last < first:
        raise PDFError("หน้าสุดท้ายต้องไม่น้อยกว่าหน้าเริ่มต้น")
    total = opts.start_number + (last - first)
    plan = []
    for idx in range(first - 1, last):
        number = opts.start_number + (idx - (first - 1))
        side = opts.hpos
        if opts.mirror_even and side != "center" and (idx + 1) % 2 == 0:
            side = "right" if side == "left" else "left"
        plan.append((idx, format_label(number, total, opts), side))
    return plan


def _label_pdf(text: str, font_path: str, size: float, color) -> tuple[fitz.Document, float, float]:
    measure = FPDF(unit="pt")
    measure.add_font("PN", "", font_path)
    measure.add_page()
    measure.set_font("PN", size=size)
    measure.set_text_shaping(True, script="thai", language="tha")
    width = max(measure.get_string_width(text), size * 0.6) + 2
    height = size * 1.5
    pdf = FPDF(format=(width, height), unit="pt")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.add_font("PN", "", font_path)
    pdf.set_font("PN", size=size)
    pdf.set_text_shaping(True, script="thai", language="tha")
    pdf.set_text_color(*[max(0, min(255, int(c * 255))) for c in color])
    pdf.c_margin = 0
    pdf.set_xy(1, (height - size) / 2)
    pdf.cell(w=width - 2, h=size, text=text, align="C")
    return fitz.open("pdf", pdf.output()), width, height


def apply_page_numbers(session: PDFSession, opts: PageNumberOptions) -> int:
    """ใส่เลขหน้าตาม opts — คืนจำนวนหน้าที่ใส่"""
    doc = require_unlocked(session)
    plan = page_plan(doc.page_count, opts)
    _, font_path = fonts.resolve_font_path(opts.font or "sarabun", user_id=session.user_id)
    cache: dict[str, tuple[fitz.Document, float, float]] = {}
    try:
        for idx, text, side in plan:
            if text not in cache:
                cache[text] = _label_pdf(text, font_path, opts.font_size, opts.color)
            label, w, h = cache[text]
            page = doc[idx]
            vis = page.rect  # ขนาดตามที่มองเห็น (หลังหมุน)
            m = max(0.0, min(opts.margin_pt, min(vis.width, vis.height) / 3))
            if side == "left":
                x0 = vis.x0 + m
            elif side == "right":
                x0 = vis.x1 - m - w
            else:
                x0 = vis.x0 + (vis.width - w) / 2
            y0 = vis.y0 + m if opts.vpos == "top" else vis.y1 - m - h
            target = fitz.Rect(x0, y0, x0 + w, y0 + h)
            if page.rotation:
                # แปลงกรอบจากพิกัดที่มองเห็นกลับเป็นพิกัดของหน้า แล้วหมุนเนื้อหาตามหน้า (ไม่งั้นตัวเลขเอียง/ผิดตำแหน่ง)
                page.show_pdf_page(target * page.derotation_matrix, label, 0, rotate=page.rotation)
            else:
                page.show_pdf_page(target, label, 0)
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError(f"ใส่เลขหน้าไม่สำเร็จ: {exc}")
    finally:
        for label, _, _ in cache.values():
            label.close()
    session.mark_dirty()
    return len(plan)
