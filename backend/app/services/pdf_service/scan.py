"""pdf_service.scan — ภาพจากการสแกนด้วยกล้องมือถือ (ดัดภาพ/ขาวดำมาแล้วจากเครื่องผู้ใช้) → PDF หลายหน้า + ชั้นข้อความ OCR

- หน้าละหนึ่งภาพ เรียงตามลำดับที่ถ่าย ขนาดหน้าตามสัดส่วนภาพจริง (ไม่บังคับ A4) ที่ความละเอียด SCAN_DPI
- ชั้นข้อความ OCR ไทย/อังกฤษ ด้วยวิธีเดียวกับการอัปโหลดรูปภาพ (_ocr_page_regions) → ค้นหา/เซ็นเซอร์/PDPA ได้
- ภาพ PNG ขาวดำ 1 บิตใส่ตรงๆ (Flate ไม่เสียข้อมูล) ภาพสี/เทาเป็น JPEG ตามที่เครื่องผู้ใช้ส่งมา
- หน้าขาวดำ: เครื่องผู้ใช้ส่งภาพเทา (ลบเงาแล้ว ก่อนตัดเป็นขาวดำ) มาด้วยได้ (ocr_images) — อ่านข้อความทั้งจาก
  ภาพขาวดำและภาพเทาพร้อมกัน แล้วเลือกผลที่อ่านเป็นคำได้มากกว่า (ขาวดำทำให้วรรณยุกต์/สระบนเส้นบางขาดหาย
  แต่ภาพเทาบางหน้ามีลายพื้นหลัง/เงาที่ทำให้อ่านพลาด — เลือกต่อหน้า วัดผลด้วย scripts/scan_eval.py --gray)
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Callable

import fitz
from PIL import Image, ImageOps

from app.core.heavy import heavy_slot, run_in_slot_context
from app.services.pdf_service.core import PDFError
from app.services.pdf_service.ocr import _insert_invisible_words, _ocr_font_path, _ocr_words_robust

logger = logging.getLogger("pdf_service")

SCAN_DPI = 200            # ฝั่งเครื่องผู้ใช้ดัดภาพให้ด้านยาวของ A4 ≈ 2339 px (200 dpi) — ภาพที่ไม่ระบุ dpi ถือค่านี้
SCAN_MAX_PAGES = 50
SCAN_MAX_PAGE_BYTES = 10 * 1024 * 1024
_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")


def check_scan_image(data: bytes) -> None:
    """ปฏิเสธไฟล์ที่ไม่ใช่ PNG/JPEG จริง (ดูจากเนื้อไฟล์ ไม่เชื่อนามสกุล) หรือใหญ่เกิน"""
    if len(data) > SCAN_MAX_PAGE_BYTES:
        raise PDFError("ภาพหน้าหนึ่งใหญ่เกิน 10 MB")
    if not data.startswith(_MAGIC):
        raise PDFError("รองรับเฉพาะภาพ PNG หรือ JPEG")


def _page_image(data: bytes) -> tuple[bytes, int, int, float]:
    """(ข้อมูลภาพที่จะฝัง, กว้าง px, สูง px, dpi) — หมุนตาม EXIF (ภาพจากกล้องระบบผ่านทางสำรอง) ถ้าจำเป็น"""
    img = Image.open(io.BytesIO(data))
    img.load()
    orientation = img.getexif().get(0x0112, 1)
    if orientation not in (1, None):
        upright = ImageOps.exif_transpose(img)
        buf = io.BytesIO()
        if upright.mode in ("1", "L"):
            upright.save(buf, "PNG", optimize=True)
        else:
            upright.convert("RGB").save(buf, "JPEG", quality=88)
        data, img = buf.getvalue(), upright
    if data.startswith(_MAGIC[0]) and img.mode != "1":
        # ภาพขาวดำจาก canvas ของเบราว์เซอร์เป็น PNG RGBA 8 บิต — เก็บเป็น 1 บิตให้ไฟล์ PDF เล็กลงมาก
        gray = img.convert("L")
        hist = gray.histogram()
        extremes = sum(hist[:16]) + sum(hist[240:])
        if extremes >= 0.995 * gray.width * gray.height:   # ขาวดำ (เผื่อพิกเซลขอบที่เกลี่ยสีเล็กน้อย)
            gray = gray.point(lambda v: 255 if v >= 128 else 0)
            buf = io.BytesIO()
            gray.convert("1").save(buf, "PNG", optimize=True, dpi=img.info.get("dpi", (SCAN_DPI, SCAN_DPI)))
            data = buf.getvalue()
    dpi = img.info.get("dpi", (SCAN_DPI,))[0] or SCAN_DPI
    dpi = min(600.0, max(72.0, float(dpi)))
    return data, img.width, img.height, dpi


GRAY_WHITE = 200         # ภาพเทาสำหรับอ่านข้อความ: สว่างกว่านี้ = พื้นขาวล้วน (ตัดเงาจาง/ลายพื้น) หมึกคงระดับเทา


def ocr_gray_image(data: bytes) -> Image.Image:
    """ภาพเทาจากเครื่องผู้ใช้ → ภาพสำหรับ OCR: พื้นขาวล้วน ส่วนหมึกยืดช่วงความเข้มให้เต็ม (เส้นบางยังเป็นสีเทาอยู่)"""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    return img.point(lambda v: 255 if v >= GRAY_WHITE else int(v * 255 / GRAY_WHITE))


def _text_score(words) -> float:
    """คะแนนผล OCR หนึ่งหน้า: จำนวนอักษรไทยที่อยู่ในคำที่มีในพจนานุกรม + อักษรละติน/ตัวเลขครึ่งน้ำหนัก"""
    from app.services import thai_text

    text = " ".join(w[1] for w in words)
    thai = sum(1 for c in text if "\u0e01" <= c <= "\u0e4e")
    latin = sum(1 for c in text if c.isascii() and c.isalnum())
    return (thai_text.dictionary_coverage(text) if thai else 0.0) * thai + 0.5 * latin


def _best_words(page: fitz.Page, ocr_image: bytes | None):
    """คำ OCR ของหน้า — มีภาพเทามาด้วย: อ่านทั้งสองภาพพร้อมกัน (tesseract เป็นโปรเซสแยก) แล้วเลือกผลที่ดีกว่า"""
    if not ocr_image:
        return _ocr_words_robust(page, page.rect)
    from concurrent.futures import ThreadPoolExecutor

    from app.services.pdf_service.ocr import _ocr_words_from_image, _region_image

    bw_img, zoom = _region_image(page, page.rect)      # เรนเดอร์ในเธรดหลัก (PyMuPDF ใช้หลายเธรดพร้อมกันไม่ได้)
    gray = ocr_gray_image(ocr_image).resize(bw_img.size, Image.LANCZOS)
    # ถือช่องคิวงานหนักช่องเดียวให้ทั้งคู่ (เธรดลูกรู้ว่าถือแล้ว ไม่ขอซ้ำ — ถ้าขอแยกกันจะรอกันเองเมื่อมีช่องเดียว)
    with heavy_slot("tesseract"), ThreadPoolExecutor(max_workers=2) as ex:
        a = ex.submit(run_in_slot_context(_ocr_words_from_image), bw_img, page.rect, zoom)
        b = ex.submit(run_in_slot_context(_ocr_words_from_image), gray, page.rect, zoom)
        bw_words, gray_words = a.result(), b.result()
    return gray_words if _text_score(gray_words) > _text_score(bw_words) else bw_words


def build_scan_pdf(images: list[bytes], title: str, progress: Callable[[int, int], None] | None = None,
                   ocr: bool = True, ocr_images: list[bytes | None] | None = None) -> bytes:
    """PDF จากภาพสแกนตามลำดับ + ชั้นข้อความ OCR — progress(หน้าที่เสร็จ, ทั้งหมด)
    ocr_images: ภาพเทาสำหรับอ่านข้อความของแต่ละหน้า (None = ใช้ภาพหน้าเอง)"""
    if not images:
        raise PDFError("ไม่มีภาพสแกน")
    if len(images) > SCAN_MAX_PAGES:
        raise PDFError(f"สแกนได้ไม่เกิน {SCAN_MAX_PAGES} หน้าต่อไฟล์")
    doc = fitz.open()
    fontfile = _ocr_font_path() if ocr else None
    font = fitz.Font(fontfile=fontfile) if fontfile else None
    words = 0
    for i, data in enumerate(images, 1):
        check_scan_image(data)
        stream, w, h, dpi = _page_image(data)
        page = doc.new_page(width=w * 72 / dpi, height=h * 72 / dpi)
        page.insert_image(page.rect, stream=stream)
        if font is not None:
            try:
                extra = ocr_images[i - 1] if ocr_images and i - 1 < len(ocr_images) else None
                words += _insert_invisible_words(page, _best_words(page, extra), font, fontfile)
            except Exception:
                logger.warning("scan: OCR หน้า %d ไม่สำเร็จ (ยังได้ภาพหน้าเดิม)", i, exc_info=True)
        if progress:
            progress(i, len(images))
    now = datetime.now().astimezone().strftime("D:%Y%m%d%H%M%S")
    doc.set_metadata({"title": title, "creator": "JA PDF Editor Scan", "producer": "JA PDF Editor",
                      "creationDate": now, "modDate": now})
    logger.info("scan: %d หน้า ชั้นข้อความ OCR %d คำ", len(images), words)
    return doc.tobytes(garbage=3, deflate=True)
