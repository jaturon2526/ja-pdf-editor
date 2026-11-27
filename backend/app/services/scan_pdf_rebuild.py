"""scan_pdf_rebuild — แปลงภาพสแกนเป็น PDF Object จริง (ข้อความเวกเตอร์ + ตารางเวกเตอร์ + รูป/ตรา/ลายเซ็นที่ตัดแยก)

ต่างจาก pdf_service.scan.build_scan_pdf (ภาพเต็มหน้า + ชั้นข้อความ OCR ล่องหน) ตรงที่:
1. วิเคราะห์โครงสร้างหน้าด้วย scan_docx.analyze + scan_docx.layout (ตาราง, กรอบ, โลโก้/ตรา/ลายเซ็น/บาร์โค้ด,
   ย่อหน้า, จัดชิด, เยื้อง, แท็บ/จุดไข่ปลา, ตัวหนา, ขนาดอักษร)
2. ตรวจและจัดรูปคำไทยอัตโนมัติด้วย ocr_thai + thai_text.normalize และเลือกให้ AI ช่วยตรวจแก้คำไทยเพิ่มเติมได้
   (ผ่าน convert_service.fix_thai_text_groups พร้อมตัวกรอง accept_ai_text และโควต้า AI)
3. วาดลงหน้า PDF เป็น Object จริงด้วย fpdf2 + uharfbuzz (Thai OpenType shaping) ฟอนต์ Google Sarabun:
   - ข้อความจริง (แก้ไขข้อความ/ค้นหา/เซ็นเซอร์/PDPA ใน Editor ได้ทันที)
   - เส้นตารางและสีพื้นช่องเป็นเวกเตอร์จริง (page.find_tables() และเครื่องมือแก้ตารางใน Editor ทำงานได้ทันที)
   - รูป/โลโก้/ตราประทับ/ลายเซ็น/บาร์โค้ด ตัดแยกมาวางตรงพิกัดเดิม (ย้าย/ลบในโหมดแก้ไขรูปภาพได้)
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

import fitz
from fpdf import FPDF
from PIL import Image

from app.core.heavy import heavy_slot
from app.services import ai_client, thai_text
from app.services.pdf_service.core import PDFError
from app.services.pdf_service.scan import SCAN_MAX_PAGES, _page_image, check_scan_image, ocr_gray_image
from app.services.scan_docx import analyze, layout
from app.services.scan_docx.layout import PageLayout, Paragraph, Picture, Run, Table
from app.services.scan_docx.writer import FONT_FILES, FONTS_DIR, crop_picture

logger = logging.getLogger("scan_pdf_rebuild")

FONT_NAME = "Sarabun"
_FONT_REG = str(Path(FONTS_DIR) / FONT_FILES["regular"])
_FONT_BOLD = str(Path(FONTS_DIR) / FONT_FILES["bold"])
_TABLE_BORDER_RGB = (45, 45, 45)
_TABLE_BORDER_WIDTH = 0.6
_CELL_PAD_X = 3.0
_CELL_PAD_Y = 2.0


def _hex_to_rgb(hex_color: str | None, default: tuple[int, int, int] = (0, 0, 0)) -> tuple[int, int, int]:
    """แปลง hex 6 หลัก (เช่น 'FFFFFF' หรือ '#1E293B') เป็น (r, g, b)"""
    if not hex_color:
        return default
    clean = hex_color.strip().lstrip("#")
    if len(clean) != 6:
        return default
    try:
        return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)
    except ValueError:
        return default


def _collect_paragraphs(pages: list[tuple[PageLayout, Image.Image]]) -> list[Paragraph]:
    """รวบรวมย่อหน้าทั้งหมดในเอกสาร (ทั้งย่อหน้าปกติและย่อหน้าในช่องตาราง)"""
    out: list[Paragraph] = []
    for pl, _color in pages:
        for block in pl.blocks:
            if isinstance(block, Paragraph):
                out.append(block)
            elif isinstance(block, Table):
                for cell in block.cells:
                    out.extend(cell.paragraphs)
    return out


def _refine_thai_layouts(
    pages: list[tuple[PageLayout, Image.Image]],
    user=None,
    use_ai: bool = False,
) -> str:
    """จัดรูปคำไทยในทุกย่อหน้าด้วย thai_text.normalize และเรียก AI แก้คำไทยเพิ่มเมื่อผู้ใช้เลือก
    คืนค่า ai_status: 'local' | 'ai' | 'fallback' | 'basic'"""
    paras = _collect_paragraphs(pages)
    for p in paras:
        for r in p.runs:
            r.text = thai_text.normalize(r.text)

    if not use_ai:
        return "local"
    if not ai_client.available_for(user):
        return "basic"

    # แยกเฉพาะย่อหน้าที่มีภาษาไทย และแตกตาม "\t" เพื่อให้ AI คงตำแหน่งแท็บ/จุดไข่ปลาไว้ครบ
    targets: list[tuple[Paragraph, list[tuple[Run, list[str]]]]] = []
    groups_list: list[list[str]] = []
    for p in paras:
        full_text = "".join(r.text for r in p.runs)
        if not thai_text.has_thai(full_text):
            continue
        run_parts: list[tuple[Run, list[str]]] = []
        flat: list[str] = []
        for r in p.runs:
            parts = r.text.split("\t")
            run_parts.append((r, parts))
            flat.extend(parts)
        targets.append((p, run_parts))
        groups_list.append(flat)

    if not groups_list:
        return "ai"

    from app.services.convert_service import fix_thai_text_groups

    fixed_groups, status = fix_thai_text_groups(groups_list, user=user, source="ocr")
    for (_p, run_parts), fixed_flat in zip(targets, fixed_groups):
        cursor = 0
        for r, parts in run_parts:
            count = len(parts)
            r.text = "\t".join(fixed_flat[cursor:cursor + count])
            cursor += count
    return status


def _split_thai_tokens(text: str) -> list[str]:
    """แบ่งข้อความเป็นคำ (รองรับคำไทยผ่าน pythainlp/thai_text และช่องว่าง) เพื่อขึ้นบรรทัดไม่ตัดกลางคำ"""
    if not text:
        return []
    marked = thai_text.with_break_opportunities(text)
    tokens: list[str] = []
    for chunk in marked.split("\u200b"):
        if not chunk:
            continue
        # แยกตามช่องว่างโดยเก็บช่องว่างติดไว้ด้านหน้าหรือหลังคำ
        buf = ""
        for ch in chunk:
            if ch == " ":
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(" ")
            else:
                buf += ch
        if buf:
            tokens.append(buf)
    return tokens


def _measure_run(pdf: FPDF, text: str, size: float, bold: bool) -> float:
    if not text:
        return 0.0
    pdf.set_font(FONT_NAME, "B" if bold else "", size)
    return float(pdf.get_string_width(text))


def _wrap_runs(
    pdf: FPDF,
    runs: list[Run],
    first_width: float,
    other_width: float,
) -> list[list[tuple[str, float, bool, str | None]]]:
    """ตัด runs เป็นบรรทัดตามความกว้างที่กำหนด — คืนรายการบรรทัด แต่ละบรรทัดเป็น [(text, size, bold, color), ...]"""
    lines: list[list[tuple[str, float, bool, str | None]]] = []
    cur_line: list[tuple[str, float, bool, str | None]] = []
    cur_w = 0.0
    max_w = max(12.0, first_width)

    def push_line() -> None:
        nonlocal cur_line, cur_w, max_w
        lines.append(cur_line)
        cur_line = []
        cur_w = 0.0
        max_w = max(12.0, other_width)

    def append_segment(seg: str, size: float, bold: bool, color: str | None) -> None:
        if cur_line and cur_line[-1][1:] == (size, bold, color):
            prev_text, s, b, c = cur_line[-1]
            cur_line[-1] = (prev_text + seg, s, b, c)
        else:
            cur_line.append((seg, size, bold, color))

    for r in runs:
        if not r.text:
            continue
        size = max(5.0, float(r.size or 11.0))
        bold = bool(r.bold)
        color = r.color
        for tok in _split_thai_tokens(r.text):
            if tok == " " and not cur_line:
                continue
            tw = _measure_run(pdf, tok, size, bold)
            if cur_line and cur_w + tw > max_w + 0.5:
                push_line()
                if tok == " ":
                    continue
            append_segment(tok, size, bold, color)
            cur_w += tw

    if cur_line:
        lines.append(cur_line)
    return lines


def _line_width(pdf: FPDF, segments: list[tuple[str, float, bool, str | None]]) -> float:
    return sum(_measure_run(pdf, text, size, bold) for text, size, bold, _ in segments)


def _draw_line_segments(
    pdf: FPDF,
    segments: list[tuple[str, float, bool, str | None]],
    x: float,
    y: float,
    line_h: float,
) -> None:
    cx = x
    for text, size, bold, color in segments:
        if not text:
            continue
        pdf.set_font(FONT_NAME, "B" if bold else "", size)
        pdf.set_text_color(*_hex_to_rgb(color))
        w = float(pdf.get_string_width(text))
        pdf.set_xy(cx, y)
        pdf.cell(max(w + 0.5, 0.5), line_h, text, align="L")
        cx += w


def _draw_tabbed_paragraph(pdf: FPDF, p: Paragraph, ml: float, mr: float, page_w: float) -> None:
    """วาดย่อหน้าที่มี tab stop และ/หรือจุดไข่ปลา (dot leader)"""
    base_size = max(5.0, float(p.runs[0].size if p.runs else 11.0))
    line_h = float(p.line or base_size * 1.32)
    y = max(0.0, p.top - max(0.0, (line_h - base_size) / 2))

    # รวม runs เป็นรายการช่วงที่คั่นด้วย "\t"
    slots: list[list[tuple[str, float, bool, str | None]]] = [[]]
    for r in p.runs:
        size = max(5.0, float(r.size or base_size))
        parts = r.text.split("\t")
        for idx, part in enumerate(parts):
            if idx > 0:
                slots.append([])
            if part:
                slots[-1].append((part, size, bool(r.bold), r.color))

    cursor_x = ml + p.left + p.first
    max_x = page_w - mr
    for i, segs in enumerate(slots):
        seg_w = _line_width(pdf, segs)
        if i == 0:
            draw_x = cursor_x
        else:
            tab = p.tabs[i - 1] if i - 1 < len(p.tabs) else None
            stop_x = ml + tab.pos if tab else cursor_x + 18.0
            if tab and tab.align == "right":
                draw_x = max(cursor_x + 4.0, stop_x - seg_w)
            elif tab and tab.align == "center":
                draw_x = max(cursor_x + 4.0, stop_x - seg_w / 2)
            else:
                draw_x = max(cursor_x + 4.0, stop_x)
            draw_x = min(draw_x, max_x - seg_w) if seg_w < max_x - cursor_x else draw_x
            if tab and tab.leader == "dot" and draw_x - cursor_x > 8.0:
                _draw_dot_leader(pdf, cursor_x + 2.0, draw_x - 2.0, y, line_h, base_size)
        _draw_line_segments(pdf, segs, draw_x, y, line_h)
        cursor_x = draw_x + seg_w


def _draw_dot_leader(pdf: FPDF, x0: float, x1: float, y: float, line_h: float, size: float) -> None:
    pdf.set_font(FONT_NAME, "", size)
    pdf.set_text_color(80, 80, 80)
    dot = "."
    dw = max(2.0, float(pdf.get_string_width(dot)) + 1.2)
    count = int((x1 - x0) // dw)
    if count <= 0:
        return
    cx = x0
    for _ in range(count):
        pdf.set_xy(cx, y)
        pdf.cell(dw, line_h, dot, align="L")
        cx += dw


def _draw_paragraph_in_box(
    pdf: FPDF,
    p: Paragraph,
    box_x: float,
    box_y: float,
    box_w: float,
    box_bottom: float | None = None,
    use_indent: bool = True,
) -> float:
    """วาดย่อหน้าในกรอบที่กำหนด คืนค่า y ด้านล่างหลังวาดเสร็จ"""
    if not p.runs:
        return box_y
    base_size = max(5.0, float(p.runs[0].size or 11.0))
    line_h = float(p.line or base_size * 1.28)
    left = p.left if use_indent else 0.0
    first = p.first if use_indent else 0.0
    first_w = max(12.0, box_w - left - first)
    other_w = max(12.0, box_w - left)
    lines = _wrap_runs(pdf, p.runs, first_w, other_w)
    y = box_y
    for idx, segs in enumerate(lines):
        if box_bottom is not None and y + line_h * 0.6 > box_bottom:
            break
        avail_w = first_w if idx == 0 else other_w
        base_x = box_x + left + (first if idx == 0 else 0.0)
        lw = _line_width(pdf, segs)
        if p.align == "center":
            x = base_x + max(0.0, (avail_w - lw) / 2)
        elif p.align == "right":
            x = base_x + max(0.0, avail_w - lw)
        else:
            x = base_x
        _draw_line_segments(pdf, segs, x, y, line_h)
        y += line_h
    return y


def _draw_paragraph(pdf: FPDF, p: Paragraph, pl: PageLayout) -> None:
    if not p.runs:
        return
    ml, _mt, mr, _mb = pl.margins
    if p.tabs and any("\t" in r.text for r in p.runs):
        _draw_tabbed_paragraph(pdf, p, ml, mr, pl.width)
        return
    base_size = max(5.0, float(p.runs[0].size or 11.0))
    line_h = float(p.line or base_size * 1.32)
    y = max(0.0, p.top - max(0.0, (line_h - base_size) / 2))
    content_w = max(20.0, pl.width - ml - mr)
    _draw_paragraph_in_box(pdf, p, ml, y, content_w, box_bottom=pl.height - 2.0, use_indent=True)


def _draw_table(pdf: FPDF, t: Table, pl: PageLayout) -> None:
    nrows = len(t.row_heights)
    ncols = len(t.col_widths)
    if nrows == 0 or ncols == 0:
        return
    ml = pl.margins[0]
    xs = [ml + t.left]
    for w in t.col_widths:
        xs.append(xs[-1] + max(1.0, float(w)))
    ys = [t.top]
    for h in t.row_heights:
        ys.append(ys[-1] + max(1.0, float(h)))

    covered: set[tuple[int, int]] = set()
    cell_rects: list[tuple[tuple[float, float, float, float], object]] = []
    for tc in sorted(t.cells, key=lambda c: (c.row, c.col)):
        if (tc.row, tc.col) in covered or tc.row >= nrows or tc.col >= ncols:
            continue
        r2 = min(tc.row + max(1, tc.row_span), nrows)
        c2 = min(tc.col + max(1, tc.col_span), ncols)
        span = {(r, c) for r in range(tc.row, r2) for c in range(tc.col, c2)}
        if span & covered:
            r2 = tc.row + 1
            c2 = tc.col + 1
            span = {(tc.row, tc.col)}
        covered |= span
        cell_rects.append(((xs[tc.col], ys[tc.row], xs[c2] - xs[tc.col], ys[r2] - ys[tc.row]), tc))

    # วาดพื้นสีและเส้นกรอบตาราง (เวกเตอร์จริงเพื่อให้ Editor ตรวจจับตารางได้)
    pdf.set_draw_color(*_TABLE_BORDER_RGB)
    pdf.set_line_width(_TABLE_BORDER_WIDTH)
    for (cx, cy, cw, ch), tc in cell_rects:
        if tc.shade:
            pdf.set_fill_color(*_hex_to_rgb(tc.shade, (240, 240, 240)))
            pdf.rect(cx, cy, cw, ch, style="DF")
        else:
            pdf.rect(cx, cy, cw, ch, style="D")

    # วาดข้อความในแต่ละช่องตาราง
    for (cx, cy, cw, ch), tc in cell_rects:
        inner_x = cx + _CELL_PAD_X
        inner_w = max(8.0, cw - 2 * _CELL_PAD_X)
        cur_y = cy + _CELL_PAD_Y
        cell_bottom = cy + ch - _CELL_PAD_Y
        for p in tc.paragraphs:
            if cur_y >= cell_bottom:
                break
            cur_y = _draw_paragraph_in_box(
                pdf,
                p,
                inner_x,
                cur_y,
                inner_w,
                box_bottom=cell_bottom,
                use_indent=False,
            )


def _draw_picture(pdf: FPDF, pic: Picture, color: Image.Image) -> None:
    if pic.w <= 1 or pic.h <= 1:
        return
    try:
        cropped = crop_picture(color, pic.box, pic.kind)
        buf = io.BytesIO()
        cropped.save(buf, "PNG", optimize=True)
        buf.seek(0)
        pdf.image(buf, x=pic.x, y=pic.y, w=pic.w, h=pic.h)
    except Exception:
        logger.warning("scan_pdf_rebuild: วาดรูปย่อยไม่สำเร็จ (%s)", pic.kind, exc_info=True)


def render_layouts_to_pdf(pages: list[tuple[PageLayout, Image.Image]], title: str) -> bytes:
    """วาดโครงเอกสาร (PageLayout) ทุกหน้าเป็น PDF Object จริงด้วย fpdf2 + uharfbuzz แล้วตั้ง metadata ด้วย PyMuPDF"""
    pdf = FPDF(unit="pt")
    pdf.set_auto_page_break(False)
    pdf.c_margin = 0
    pdf.add_font(FONT_NAME, "", _FONT_REG)
    pdf.add_font(FONT_NAME, "B", _FONT_BOLD)
    pdf.set_text_shaping(True, script="thai", language="tha")

    for pl, color in pages:
        pdf.add_page(format=(max(72.0, pl.width), max(72.0, pl.height)))
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(0, 0, pl.width, pl.height, style="F")

        # 1. วาดรูปภาพ/โลโก้/ตราประทับ/ลายเซ็น/บาร์โค้ดก่อน เพื่อไม่ทับข้อความที่อยู่ข้างเคียง
        for block in pl.blocks:
            if isinstance(block, Picture):
                _draw_picture(pdf, block, color)

        # 2. วาดตารางและข้อความ
        for block in pl.blocks:
            if isinstance(block, Table):
                _draw_table(pdf, block, pl)
            elif isinstance(block, Paragraph):
                _draw_paragraph(pdf, block, pl)

    raw = bytes(pdf.output())
    now = datetime.now().astimezone().strftime("D:%Y%m%d%H%M%S")
    with fitz.open("pdf", raw) as doc:
        doc.set_metadata({
            "title": title,
            "creator": "JA PDF Editor Scan (Rebuild)",
            "producer": "JA PDF Editor",
            "creationDate": now,
            "modDate": now,
        })
        return doc.tobytes(garbage=3, deflate=True)


def build_rebuilt_scan_pdf(
    images: list[bytes],
    title: str,
    progress: Callable[[int, int], None] | None = None,
    ocr_images: list[bytes | None] | None = None,
    user=None,
    use_ai: bool = False,
) -> tuple[bytes, str]:
    """ภาพสแกนหลายหน้า → PDF Object จริง (ข้อความ + ตาราง + รูปย่อย) พร้อมตรวจคำไทยและเลือกใช้ AI ได้
    คืนค่า (pdf_bytes, ai_status) โดย ai_status = 'local' | 'ai' | 'fallback' | 'basic'"""
    if not images:
        raise PDFError("ไม่มีภาพสแกน")
    if len(images) > SCAN_MAX_PAGES:
        raise PDFError(f"สแกนได้ไม่เกิน {SCAN_MAX_PAGES} หน้าต่อไฟล์")

    total_steps = len(images) + (2 if use_ai else 1)
    pages: list[tuple[PageLayout, Image.Image]] = []

    with heavy_slot("tesseract"):
        for i, data in enumerate(images, 1):
            check_scan_image(data)
            stream, w, h, dpi = _page_image(data)
            color = Image.open(io.BytesIO(stream)).convert("RGB")
            extra = ocr_images[i - 1] if ocr_images and i - 1 < len(ocr_images) else None
            gray = ocr_gray_image(extra).resize(color.size, Image.LANCZOS) if extra else color.convert("L")
            pa = analyze.analyze(gray, color)
            pl = layout.layout_page(pa, dpi, w * 72.0 / dpi, h * 72.0 / dpi)
            pages.append((pl, pa.color))
            if progress:
                progress(i, total_steps)

    ai_status = _refine_thai_layouts(pages, user=user, use_ai=use_ai)
    if use_ai and progress:
        progress(len(images) + 1, total_steps)

    pdf_bytes = render_layouts_to_pdf(pages, title=title)
    if progress:
        progress(total_steps, total_steps)

    logger.info("scan rebuild: %d หน้า ai_status=%s size=%d bytes", len(images), ai_status, len(pdf_bytes))
    return pdf_bytes, ai_status
