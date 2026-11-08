"""แปลงไฟล์สแกน (PDF ที่แต่ละหน้าเป็นภาพ) เป็น Word ที่ข้อความแก้ไขได้

pdf2docx (ใช้กับ PDF ทั่วไป) ไม่รองรับไฟล์สแกน — ได้รูปเต็มหน้าและไม่มีข้อความเลย แม้ PDF จะมีชั้นข้อความ OCR
แบบล่องหนอยู่แล้ว โมดูลนี้ทำทีละหน้า:

1. analyze: deskew → หาเส้นตาราง/กรอบ, บาร์โค้ด, โลโก้/ตรา/ลายเซ็น, จุดไข่ปลา, รอยขอบกระดาษ
2. layout: OCR (ocr_thai) → บรรทัด → ย่อหน้า (จัดชิด/เยื้อง/tab/จุดไข่ปลา/ตัวหนา/ขนาด) + ตาราง + รูป
3. writer: Word ฟอนต์ Sarabun (ฝังในไฟล์) ขนาดกระดาษ/ขอบตามต้นฉบับ ทีละหน้า (section ละหน้า)

ใช้ CPU บนเซิร์ฟเวอร์ทั้งหมด (Tesseract + OpenCV) ไม่ส่งข้อมูลออกนอกเครื่อง
"""
from __future__ import annotations

import logging
from typing import Callable

import fitz
from PIL import Image

logger = logging.getLogger("scan_docx")

MAX_DPI = 300
MIN_DPI = 150
SCAN_IMAGE_COVERAGE = 0.85      # รูปเดียวครอบคลุม ≥ 85% ของหน้า
MAX_PAGES = 50                  # กันงานค้างนานเกินไป (≈ 5–15 วินาที/หน้า)


SCANNER_CREATOR = "JA PDF Editor Scan"


def _layer_lines(page: fitz.Page, dpi: float) -> list | None:
    """คำจากชั้นข้อความ OCR (ล่องหน) ของหน้า จัดเป็นบรรทัด — พิกัดเป็นพิกเซลของภาพที่เรนเดอร์ที่ dpi นี้"""
    k = dpi / 72.0
    lines: dict[tuple[int, int], list] = {}
    for x0, y0, x1, y1, text, block, line, _n in page.get_text("words"):
        if text.strip():
            lines.setdefault((block, line), []).append(((x0 * k, y0 * k, x1 * k, y1 * k), text))
    return [lines[key] for key in sorted(lines)] or None


class ScanConvertError(Exception):
    pass


def _visible_text_len(page: fitz.Page) -> int:
    """จำนวนอักขระของข้อความที่มองเห็น (ไม่นับชั้น OCR ล่องหน render mode 3)"""
    n = 0
    for block in page.get_texttrace():
        if block.get("type") == 3:     # invisible
            continue
        n += len(block.get("chars", ()))
    return n


def is_scanned_page(page: fitz.Page) -> bool:
    area = abs(page.rect) or 1
    covered = 0.0
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"]) & page.rect
        covered = max(covered, abs(r) / area)
    return covered >= SCAN_IMAGE_COVERAGE and _visible_text_len(page) < 20


def is_scanned_pdf(pdf_bytes: bytes) -> bool:
    """ไฟล์สแกน = หน้าส่วนใหญ่เป็นภาพเต็มหน้าที่ไม่มีข้อความที่มองเห็น"""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return False
    with doc:
        if doc.needs_pass or doc.page_count == 0:
            return False
        pages = list(doc)[:20]
        scanned = sum(1 for p in pages if is_scanned_page(p))
        return scanned >= max(1, (len(pages) + 1) // 2)


def _page_dpi(page: fitz.Page) -> int:
    best = 0.0
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.width > 0:
            best = max(best, info["width"] / (r.width / 72))
    return int(min(MAX_DPI, max(MIN_DPI, round(best or 200))))


def render_page(page: fitz.Page) -> tuple[Image.Image, float]:
    dpi = _page_dpi(page)
    pix = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples), dpi


def convert_scan_to_docx(pdf_bytes: bytes, progress_callback: Callable[[int], None] | None = None) -> bytes:
    from app.services.scan_docx import analyze, layout, writer

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.needs_pass:
        raise ScanConvertError("ไฟล์มีรหัสผ่าน — ปลดล็อกก่อนแปลง")
    if doc.page_count > MAX_PAGES:
        raise ScanConvertError(f"ไฟล์สแกนแปลงได้ครั้งละไม่เกิน {MAX_PAGES} หน้า (ไฟล์นี้มี {doc.page_count} หน้า)")
    pages = []
    # ไฟล์จากเมนูสแกนของแอป (ชั้นข้อความอ่านไว้แล้วตอนสแกน — ดู pdf_service/scan.py)
    from_scanner = (doc.metadata or {}).get("creator") == SCANNER_CREATOR
    with doc:
        n = doc.page_count
        for i, page in enumerate(doc):
            color, dpi = render_page(page)
            pa = analyze.analyze(color.convert("L"), color)
            if from_scanner:
                pa.layer_lines = _layer_lines(page, dpi)
            pl = layout.layout_page(pa, dpi, page.rect.width, page.rect.height)
            pages.append((pl, pa.color))
            if progress_callback:
                progress_callback(10 + int(80 * (i + 1) / n))
    data = writer.build_docx(pages)
    if progress_callback:
        progress_callback(95)
    return data
