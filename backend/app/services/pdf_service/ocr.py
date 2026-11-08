"""pdf_service.ocr — OCR พื้นที่ที่เลือก (Gemini ถ้ามี key ส่วนตัว ไม่งั้น Tesseract) และชั้นข้อความ OCR ของรูปภาพ

ชั้นข้อความ OCR (add_ocr_text_layer): อ่านข้อความในรูปภาพบนหน้า (ลายเซ็น+ชื่อผู้ลงนาม ตราประทับ ภาพสแกน) ด้วย
Tesseract แล้ววางเป็นข้อความล่องหน (render mode 3) ทับตำแหน่งเดิม → ค้นหา/เซ็นเซอร์/คัดลอก/PDPA ใช้ได้ และ
เซ็นเซอร์จะทาดำพิกเซลของรูปตรงนั้นด้วย (apply_redactions images=PIXELS) — หน้าตาเอกสารไม่เปลี่ยน

การอ่านด้วย Tesseract ทุกทาง (ปุ่มคัดลอก/OCR, ชั้นข้อความ, อัปโหลดไฟล์รูป) ใช้ app/services/ocr_thai.py
(ตัดบรรทัดเอง, deskew, ลบเส้นตาราง/จุดไข่ปลา, แก้คำด้วยพจนานุกรม) — วัดผลด้วย scripts/ocr_eval.py
"""
from __future__ import annotations

from PIL import Image
import fitz
from app.core.heavy import heavy_slot
from app.core.session import PDFSession
from app.models.schemas import Rect
from app.services import ocr_thai, thai_text
from app.services.pdf_service.core import PDFError, require_unlocked

import logging

logger = logging.getLogger("pdf_service")


def extract_text_ocr(session: PDFSession, page_number: int, rect: Rect, user=None) -> str:
    """ดึงข้อความจากภาพ โดยใช้ Gemini AI (ถ้ามี API Key ส่วนตัว) หรือ Tesseract (สำรอง)"""
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    page = doc[page_number]
    zoom = OCR_COPY_ZOOM
    matrix = fitz.Matrix(zoom, zoom)
    clip_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1).normalize() & page.rect
    if clip_rect.is_empty or clip_rect.width < 2 or clip_rect.height < 2:
        raise PDFError("พื้นที่ที่เลือกเล็กเกินไป หรืออยู่นอกหน้ากระดาษ — ลากคลุมข้อความให้ใหญ่ขึ้น")

    # (เดิมลบ AP ของกล่องข้อความทุกตัวทิ้งก่อนจับภาพ — ข้อความในไฟล์หายถาวร) ตอนนี้กล่องข้อความมี AP ของตัวเองแล้ว
    pixmap = page.get_pixmap(matrix=matrix, clip=clip_rect)

    if pixmap.n - pixmap.alpha < 4:
        mode = "RGBA" if pixmap.alpha else "RGB"
    else:
        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
        mode = "RGBA" if pixmap.alpha else "RGB"
        
    img = Image.frombytes(mode, [pixmap.width, pixmap.height], pixmap.samples)
    
    # AI ส่วนตัวของผู้ใช้ (ค่ายไหนก็ได้ — ดู ai_client) อ่านภาพได้แม่นกว่า Tesseract · ไม่มี/ล้มเหลว → Tesseract
    from app.core.config import settings
    from app.services import ai_client

    user_ai = ai_client.user_config(user) if settings.AI_USER_KEYS_ENABLED else None
    if user_ai:
        try:
            prompt = "Please extract the text from this image accurately. Return ONLY the extracted text exactly as it appears (both Thai and English). Do not include any explanations, markdown formatting, or introductory words."
            text = ai_client.generate(user_ai, prompt, img)
            if text:
                return thai_text.normalize(text)
        except Exception as e:
            logger.error("AI OCR (%s) failed: %s", user_ai.provider, e)
            # ถ้าพัง ให้ตกไปใช้ Tesseract ต่อ

    # Fallback Tesseract — ตัดบรรทัดเอง/deskew/ลบเส้นตาราง/แก้คำด้วยพจนานุกรม (ดู app/services/ocr_thai.py)
    logger.info("Using Tesseract as fallback for OCR")
    return ocr_thai.recognize_text(img.convert("L"))


# ---------------------------------------------------------------- ชั้นข้อความ OCR ของรูปภาพ

OCR_DPI = 300
OCR_MAX_PIXELS = 4200          # ด้านยาวสุดของภาพที่ส่งให้ Tesseract (กันหน่วยความจำ/เวลา)
OCR_MIN_CONF = 50              # ตัดคำที่ Tesseract ไม่มั่นใจ (เช่น ลายมือชื่อที่อ่านเป็นขยะ)
OCR_COPY_ZOOM = 4.0            # ปุ่มคัดลอก/OCR: render พื้นที่ที่เลือกที่ 288 dpi
OCR_MIN_IMAGE_AREA = 0.02      # ข้ามรูปเล็กกว่า 2% ของหน้า (ไอคอน โลโก้)
OCR_MAX_PAGES = 30
OCR_TIME_BUDGET = 75.0         # วินาที — เริ่มหน้าใหม่เฉพาะเมื่อยังไม่เกินนี้ (หน้าสแกนเต็มหน้า ~5 วินาที)
OCR_FONT_NAME = "ocrtext"


def _ocr_font_path() -> str:
    from app.services import fonts

    _name, path = fonts.resolve_font_path("sarabun")
    return path


def _image_regions(page: fitz.Page) -> list[fitz.Rect]:
    """รูปบนหน้าที่ควรอ่าน: ใหญ่พอ และยังไม่มีข้อความ (หรือชั้น OCR) ทับอยู่ — รันซ้ำจึงไม่เพิ่มซ้ำ"""
    area = abs(page.rect) or 1
    regions = []
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"]) & page.rect
        if r.is_empty or abs(r) / area < OCR_MIN_IMAGE_AREA:
            continue
        if len(page.get_text("text", clip=r).strip()) > 10:
            continue
        if any(abs(r & q) > 0.8 * min(abs(r), abs(q)) for q in regions):
            continue
        regions.append(r)
    return regions


def _ocr_words(page: fitz.Page, region: fitz.Rect) -> list[tuple[fitz.Rect, str, int]]:
    """[(กรอบบนหน้า, คำ, หมายเลขบรรทัด)] จาก ocr_thai — พิกัดแปลงกลับเป็นพิกัดหน้า"""
    zoom = OCR_DPI / 72
    longest = max(region.width, region.height) * zoom
    if longest > OCR_MAX_PIXELS:
        zoom *= OCR_MAX_PIXELS / longest
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=region, colorspace=fitz.csGRAY, alpha=False)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    words = []
    for line_no, line in enumerate(ocr_thai.recognize(img)):
        for w in line.words:
            if w.conf < OCR_MIN_CONF:
                continue
            x0, y0, x1, y1 = w.box
            r = fitz.Rect(region.x0 + x0 / zoom, region.y0 + y0 / zoom, region.x0 + x1 / zoom, region.y0 + y1 / zoom)
            words.append((r & region, w.text, line_no))
    return words


SPARSE_MIN_CONF = 75            # คำจากรอบ "ข้อความกระจาย" ต้องมั่นใจสูงกว่านี้
SPARSE_TRIGGER_MEAN = 70        # รอบหลักมั่นใจเฉลี่ยต่ำกว่านี้ → อ่านซ้ำแบบข้อความกระจาย
SPARSE_TRIGGER_LOW = 0.3        # หรือคำที่มั่นใจต่ำ (<60) เกินสัดส่วนนี้


def _tsv_words(img: Image.Image, lang: str, psm: int, min_conf: float) -> list[tuple[tuple[float, float, float, float], str, int, float]]:
    """Tesseract ทั้งภาพ (ผลแบบ TSV) → [(กรอบ px, คำ, บรรทัด, conf)] เฉพาะคำที่มั่นใจ ≥ min_conf"""
    import csv
    import io
    import subprocess
    import tempfile

    import pytesseract

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        img.save(tmp.name)
        with heavy_slot("tesseract"):
            out = subprocess.run([pytesseract.pytesseract.tesseract_cmd, tmp.name, "-", "-l", lang,
                                  "--psm", str(psm), "tsv"], capture_output=True, text=True, timeout=180).stdout
    words = []
    for row in csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf") or -1)
        except ValueError:
            continue
        if not text or conf < min_conf:
            continue
        x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
        line = psm * 1_000_000 + int(row["block_num"]) * 10_000 + int(row["par_num"]) * 100 + int(row["line_num"])
        words.append(((x, y, x + w, y + h), thai_text.normalize(text), line, conf))
    return words


def _sparse_words(img: Image.Image) -> list[tuple[tuple[float, float, float, float], str, int, float]]:
    """Tesseract --psm 11 (ข้อความกระจาย ไม่ต้องเรียงเป็นบรรทัด) ทั้งภาพ — ใช้กับหน้าที่อ่านทีละบรรทัดไม่ได้ผล
    เช่น สารบัญที่มีจุดไข่ปลายาว แบบฟอร์ม ตาราง"""
    return _tsv_words(img, ocr_thai.LANG, 11, SPARSE_MIN_CONF)


ENGLISH_PAGE_RATIO = 3          # ตัวอักษรละตินมากกว่าไทย ≥ 3 เท่า = หน้าภาษาอังกฤษ
ENGLISH_MIN_CONF = 60


def _osd_script(img: Image.Image) -> str | None:
    """ชนิดอักษรหลักของหน้า จาก Tesseract OSD (--psm 0): "Latin", "Thai", ... หรือ None ถ้าตรวจไม่ได้
    (ไม่มีไฟล์ osd / หน้ามีตัวอักษรน้อยเกิน)"""
    import subprocess
    import tempfile

    import pytesseract

    small = img.copy()
    small.thumbnail((2000, 2000))
    try:
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            small.save(tmp.name)
            with heavy_slot("tesseract"):
                out = subprocess.run([pytesseract.pytesseract.tesseract_cmd, tmp.name, "-", "--psm", "0"],
                                     capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    script, conf = None, 0.0
    for line in out.splitlines():
        if line.startswith("Script:"):
            script = line.split(":", 1)[1].strip()
        elif line.startswith("Script confidence:"):
            try:
                conf = float(line.split(":", 1)[1])
            except ValueError:
                pass
    return script if script and conf >= 1.0 else None


def _letters(words) -> tuple[int, int]:
    thai = latin = 0
    for _b, text, _l, conf in words:
        if conf < 60:
            continue
        thai += sum(1 for c in text if "\u0E01" <= c <= "\u0E4E")
        latin += sum(1 for c in text if c.isascii() and c.isalpha())
    return thai, latin


def _english_words(img: Image.Image):
    """หน้าภาษาอังกฤษ: อ่านด้วยโมเดลอังกฤษอย่างเดียว (โมเดลไทย+อังกฤษอ่านจุด/เส้นเป็นอักษรไทยปนมา และพลาดคำอย่าง
    "We're") — ลองทั้งแบบจัดหน้า (psm 3) และข้อความกระจาย (psm 11 สำหรับสารบัญ/ตาราง) ใช้แบบที่ได้คำมากกว่า"""
    best = []
    for psm in (3, 11):
        words = _tsv_words(img, "eng", psm, ENGLISH_MIN_CONF)
        real = [w for w in words if sum(c.isalpha() for c in w[1]) >= 2]
        if len(real) > len([w for w in best if sum(c.isalpha() for c in w[1]) >= 2]):
            best = words
    return best


def _words_score(words) -> float:
    """คะแนนผล OCR: อักษรไทยในคำที่มีในพจนานุกรม + อักษรละติน/ตัวเลขครึ่งน้ำหนัก (คำมั่นใจ ≥ OCR_MIN_CONF)"""
    from app.services import thai_text

    text = " ".join(w[1] for w in words if w[3] >= OCR_MIN_CONF)
    thai = sum(1 for c in text if "\u0e01" <= c <= "\u0e4e")
    latin = sum(1 for c in text if c.isascii() and c.isalnum())
    return (thai_text.dictionary_coverage(text) if thai else 0.0) * thai + 0.5 * latin


def _looks_like_leader(text: str) -> bool:
    """จุดไข่ปลา/เส้นประที่ OCR อ่านเป็นตัวอักษรซ้ำๆ ("จจจจจ", "๑๑๑๑๑", ".....") — ไม่ใช่คำ ไม่ต้องใส่ในชั้นข้อความ
    ตัวเลข ("๕๐๐", "00001", "1,000") ไม่ใช่จุดไข่ปลา เว้นแต่เป็นตัวเดียวซ้ำยาวมาก"""
    t = text.replace(" ", "")
    if len(t) < 3:
        return False
    if any(c.isdigit() for c in t):
        return len(set(t)) == 1 and len(t) >= 6
    most = max(t.count(c) for c in set(t))
    return len(set(t)) <= 2 or most / len(t) >= 0.7


def _ocr_words_robust(page: fitz.Page, region: fitz.Rect) -> list[tuple[fitz.Rect, str, int]]:
    """เหมือน _ocr_words แต่ถ้ารอบหลัก (ocr_thai ทีละบรรทัด) มั่นใจต่ำ อ่านซ้ำแบบข้อความกระจายแล้วรวมผล:
    ตรงไหนรอบใหม่มั่นใจกว่า ใช้คำของรอบใหม่แทน — ใช้กับภาพสแกนเต็มหน้า (สารบัญ ฟอร์ม เอกสารอังกฤษ)"""
    img, zoom = _region_image(page, region)
    return _ocr_words_from_image(img, region, zoom)


def _region_image(page: fitz.Page, region: fitz.Rect) -> tuple[Image.Image, float]:
    """ภาพเทาของพื้นที่บนหน้า ที่ความละเอียดสำหรับ OCR — (ภาพ, zoom)"""
    zoom = OCR_DPI / 72
    longest = max(region.width, region.height) * zoom
    if longest > OCR_MAX_PIXELS:
        zoom *= OCR_MAX_PIXELS / longest
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=region, colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples), zoom


def _ocr_words_from_image(img: Image.Image, region: fitz.Rect, zoom: float) -> list[tuple[fitz.Rect, str, int]]:
    """ส่วนอ่านข้อความของ _ocr_words_robust จากภาพที่เรนเดอร์แล้ว — ไม่แตะเอกสาร PDF (เรียกพร้อมกันหลายเธรดได้)"""
    script = _osd_script(img)
    primary = [(w.box, w.text, n, w.conf) for n, line in enumerate(ocr_thai.recognize(img)) for w in line.words]
    thai, latin = _letters(primary)
    english = []
    # OSD บอกว่าเป็นอักษรละติน: ยืนยันด้วยผลรอบแรก (โมเดลไทย+อังกฤษ) ว่าเห็นละตินมากกว่าไทยจริง
    # — ภาพข้อความไทยสั้น ๆ ไม่กี่บรรทัด OSD มักทายผิดเป็น Latin แล้วทั้งภาพถูกอ่านด้วยโมเดลอังกฤษ
    if script == "Latin" and latin >= thai:
        english = _english_words(img)
        if english:
            primary = english      # หน้าภาษาอังกฤษ: ใช้โมเดลอังกฤษอย่างเดียว
    elif script is None and latin >= ENGLISH_PAGE_RATIO * max(thai, 1):
        # ตรวจ OSD ไม่ได้ แต่รอบแรกเห็นเป็นอักษรละตินเกือบทั้งหมด
        english = _english_words(img)
        if english:
            thai_kept = [w for w in primary if w[3] >= 85 and any("\u0E01" <= c <= "\u0E4E" for c in w[1])
                         and not any(abs(fitz.Rect(w[0]) & fitz.Rect(e[0])) > 0 for e in english)]
            primary = english + thai_kept
    confs = [c for *_, c in primary]
    low = sum(c < 60 for c in confs) / len(confs) if confs else 1.0
    if not english and (not confs or sum(confs) / len(confs) < SPARSE_TRIGGER_MEAN or low > SPARSE_TRIGGER_LOW):
        keep = [True] * len(primary)
        extra = []
        for box, text, line, conf in _sparse_words(img):
            sr = fitz.Rect(box)
            hits = [i for i, (b, *_rest) in enumerate(primary)
                    if abs(fitz.Rect(b) & sr) > 0.5 * min(abs(fitz.Rect(b)) or 1, abs(sr) or 1)]
            if hits and any(primary[i][3] >= conf for i in hits):
                continue
            for i in hits:
                keep[i] = False
            extra.append((box, text, line, conf))
        # หน้านี้รอบหลักอ่านได้ไม่ดี — คำของรอบหลักที่มั่นใจไม่สูงมักเป็นขยะ ตัดเกณฑ์ให้เข้มขึ้น
        merged = [w for w, k in zip(primary, keep) if k and w[3] >= 65] + extra
        # ใช้ผลรวมเมื่ออ่านได้ดีกว่าจริง (ภาพข้อความไทยที่เบลอ/มี noise รอบกระจายมักได้คำซ้ำ/ขยะเพิ่ม)
        if _words_score(merged) > _words_score(primary):
            primary = merged
    import statistics

    heights = [b[3] - b[1] for b, t, *_ in primary if len(t) > 1]
    med_h = statistics.median(heights) if heights else 0
    words = []
    for (x0, y0, x1, y1), text, line, conf in primary:
        if conf < OCR_MIN_CONF or _looks_like_leader(text):
            continue
        if len(text) <= 2 and med_h and (y1 - y0) < 0.45 * med_h and not any(c.isalnum() for c in text):
            continue  # จุดเล็กๆ (จุดไข่ปลาทีละจุด) ที่อ่านเป็นเครื่องหมาย — ไม่ตัดตัวเลข/คำสั้นที่ตัวเตี้ย ("๒", "ณ", "4")
        r = fitz.Rect(region.x0 + x0 / zoom, region.y0 + y0 / zoom, region.x0 + x1 / zoom, region.y0 + y1 / zoom)
        words.append((r & region, text, line))
    return words


def ocr_region(page: fitz.Page, region: fitz.Rect, mode: str = "layer") -> str:
    """ข้อความที่ OCR อ่านได้ในกรอบ — ใช้วัดผล (scripts/ocr_eval.py)
    mode="layer": สร้างชั้นข้อความ OCR บนสำเนาหน้า แล้วดึงข้อความแบบเดียวกับการค้นหา/เซ็นเซอร์ (text_index)
    mode="text": แบบปุ่มคัดลอก/OCR
    mode="upload": แบบอัปโหลดรูปภาพ/สแกนเอกสาร (ตรวจหน้าอังกฤษ + อ่านซ้ำเมื่อมั่นใจต่ำ) ไม่ว่ารูปจะใหญ่แค่ไหน"""
    if mode == "text":
        z = OCR_COPY_ZOOM
        pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=region, colorspace=fitz.csGRAY, alpha=False)
        return ocr_thai.recognize_text(Image.frombytes("L", (pix.width, pix.height), pix.samples))
    from app.services.pdf_service import text_index

    copy = fitz.open()
    copy.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
    p2 = copy[0]
    fontfile = _ocr_font_path()
    words = _ocr_words_robust(p2, region) if mode == "upload" else _region_words(p2, region)
    _insert_invisible_words(p2, words, fitz.Font(fontfile=fontfile), fontfile)
    text = text_index.page_text(p2).text
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


def _insert_invisible_words(page: fitz.Page, words, font: fitz.Font, fontfile: str) -> int:
    """วางคำเป็นข้อความล่องหน: ทุกคำในบรรทัดใช้เส้นฐานและขนาดฟอนต์เดียวกัน ยืด/หดแนวนอนให้กว้างเท่ากรอบคำ"""
    by_line: dict[int, list] = {}
    for r, text, line in words:
        by_line.setdefault(line, []).append((r, text))
    count = 0
    for items in by_line.values():
        items.sort(key=lambda it: it[0].x0)
        # Tesseract ภาษาไทยแยกสระบน/ล่าง/วรรณยุกต์เป็น "คำ" ของตัวเอง (กว้าง 0 เมื่อวาด) → ต่อเข้ากับคำก่อนหน้า
        merged: list = []
        for r, text in items:
            if merged and all(c in thai_text.MARKS or c in "\u0E33" for c in text):
                pr, pt = merged[-1]
                merged[-1] = (pr | r, pt + text)
            else:
                merged.append((r, text))
        items = merged
        top = min(r.y0 for r, _ in items)
        bottom = max(r.y1 for r, _ in items)
        size = max(4.0, (bottom - top) * 0.8)
        baseline = top + (bottom - top) * 0.78
        for r, text in items:
            width = font.text_length(text, fontsize=size)
            if width <= 0:
                continue
            sx = max(0.2, min(5.0, r.width / width))
            origin = fitz.Point(r.x0, baseline)
            page.insert_text(origin, text, fontsize=size, fontname=OCR_FONT_NAME, fontfile=fontfile,
                             render_mode=3, morph=(origin, fitz.Matrix(sx, 1)))
            count += 1
    return count


def _ocr_page_regions(page: fitz.Page, regions: list[fitz.Rect], font: fitz.Font, fontfile: str) -> int:
    return sum(_insert_invisible_words(page, _region_words(page, r), font, fontfile) for r in regions)


ROBUST_MIN_PAGE_SHARE = 0.5     # รูปที่กินพื้นที่หน้าอย่างน้อยเท่านี้ = หน้าสแกน → อ่านแบบเดียวกับอัปโหลดรูป/สแกนเอกสาร


def _region_words(page: fitz.Page, region: fitz.Rect):
    """คำ OCR ของรูปบนหน้า — รูปเต็มหน้า (ไฟล์สแกน) ใช้ชุดเดียวกับอัปโหลดรูป/สแกนเอกสาร (ตรวจหน้าอังกฤษ + อ่านซ้ำเมื่อมั่นใจต่ำ)
    รูปเล็ก (ลายเซ็น ตรา ภาพหน้าจอ) ข้อความน้อยเกินกว่าจะตรวจภาษาทั้งหน้าได้แม่น → อ่านทีละบรรทัดตามปกติ"""
    if abs(region) >= ROBUST_MIN_PAGE_SHARE * abs(page.rect):
        return _ocr_words_robust(page, region)
    return _ocr_words(page, region)


IMAGE_UPLOAD_DPI = 200          # รูปที่ไม่ระบุ dpi (ภาพถ่าย/สแกนบางแบบ) ถือว่าเป็น 200 dpi


def image_to_searchable_pdf(content: bytes) -> bytes:
    """ไฟล์รูป (png/jpg) ที่อัปโหลด → PDF หนึ่งหน้าที่มีรูปเดิม + ชั้นข้อความ OCR (วิธีเดียวกับเมนูอ่านข้อความในรูป)
    หมุนตาม EXIF ของภาพถ่ายจากมือถือก่อน · ขนาดหน้าตาม dpi ของรูป"""
    import io

    from PIL import ImageOps

    img = Image.open(io.BytesIO(content))
    upright = ImageOps.exif_transpose(img)
    if upright is not img or img.mode not in ("RGB", "L"):
        buf = io.BytesIO()
        upright.convert("RGB").save(buf, "JPEG", quality=92)
        content = buf.getvalue()
        img = upright
    dpi = img.info.get("dpi", (IMAGE_UPLOAD_DPI,))[0] or IMAGE_UPLOAD_DPI
    dpi = min(600, max(72, float(dpi)))
    doc = fitz.open()
    page = doc.new_page(width=img.width * 72 / dpi, height=img.height * 72 / dpi)
    page.insert_image(page.rect, stream=content)
    fontfile = _ocr_font_path()
    # ภาพถ่าย/สแกนเต็มหน้า: วิธีเดียวกับสแกนเอกสาร (ตรวจภาษาอังกฤษด้วย OSD, อ่านซ้ำเมื่อรอบแรกมั่นใจต่ำ)
    n = _insert_invisible_words(page, _ocr_words_robust(page, page.rect), fitz.Font(fontfile=fontfile), fontfile)
    logger.info("รูปที่อัปโหลด → PDF + ชั้นข้อความ OCR %d คำ", n)
    return doc.tobytes(garbage=3, deflate=True)


def add_ocr_text_layer(session: PDFSession, pages: list[int] | None = None) -> dict:
    """อ่านข้อความในรูปภาพแล้ววางเป็นข้อความล่องหน คืน {"pages": [เลขหน้าเริ่ม 1], "words": n, "skipped_pages": n}
    หยุดเมื่อครบ OCR_MAX_PAGES หน้า หรือใช้เวลาเกิน OCR_TIME_BUDGET (nginx ตัดที่ 120 วินาที) — skipped_pages คือ
    จำนวนหน้าที่มีรูปซึ่งยังไม่ได้อ่าน หน้าเว็บบอกให้กดซ้ำ (หน้าที่อ่านแล้วมีข้อความทับ จึงไม่อ่านซ้ำ)"""
    import time

    doc = require_unlocked(session)
    targets = [p for p in (pages if pages is not None else range(doc.page_count)) if 0 <= p < doc.page_count]
    fontfile = _ocr_font_path()
    font = fitz.Font(fontfile=fontfile)
    done, total, examined = [], 0, 0
    started = time.monotonic()
    stopped_at = None
    for idx, pno in enumerate(targets):
        page = doc[pno]
        regions = _image_regions(page)
        if not regions:
            continue
        if examined >= OCR_MAX_PAGES or time.monotonic() - started > OCR_TIME_BUDGET:
            stopped_at = idx
            break
        examined += 1
        n = _ocr_page_regions(page, regions, font, fontfile)
        if n:
            done.append(pno + 1)
            total += n
    if total:
        session.mark_dirty()
        session.push_history()
    remaining = 0 if stopped_at is None else sum(1 for p in targets[stopped_at:] if _image_regions(doc[p]))
    logger.info("ชั้นข้อความ OCR: %d คำ ใน %d หน้า (%.1f วินาที, เหลือ %d หน้า)", total, len(done),
                time.monotonic() - started, remaining)
    return {"pages": done, "words": total, "skipped_pages": remaining}
