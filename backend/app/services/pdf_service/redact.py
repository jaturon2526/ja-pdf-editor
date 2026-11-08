"""pdf_service.redact — redaction (ปิดทับข้อความ/พื้นที่แบบถาวร)"""
from __future__ import annotations

import fitz
from app.core.session import PDFSession
from app.services import thai_text
from app.services.pdf_service import text_index
from app.services.pdf_service.core import require_unlocked

import logging

logger = logging.getLogger("pdf_service")


def redact_areas_batch(session: PDFSession, page_number: int, rects: list) -> bool:
    try:
        doc = session.doc
        if page_number < 0 or page_number >= len(doc):
            logger.error(f"Invalid page number: {page_number}")
            return False
            
        page = doc[page_number]
        
        # Add multiple redaction annotations
        for rect in rects:
            fitz_rect = fitz.Rect(rect["x0"], rect["y0"], rect["x1"], rect["y1"])
            page.add_redact_annot(fitz_rect, fill=(0, 0, 0))
            
        # Apply all redactions on this page permanently
        page.apply_redactions(images=2)
        
        session.mark_dirty()
        session.push_history()
        return True
    except Exception as e:
        logger.error(f"Error redacting areas batch: {e}")
        return False


def redact_area(session: PDFSession, page_number: int, rect: dict) -> bool:
    """
    Applies a true redaction (blackout) to a rectangle on a specific page.
    """
    doc = require_unlocked(session)
    try:
        page = doc[page_number]
        fitz_rect = fitz.Rect(rect["x0"], rect["y0"], rect["x1"], rect["y1"])
        
        # Add redaction annotation and apply it
        page.add_redact_annot(fitz_rect, fill=(0, 0, 0))
        page.apply_redactions(images=2)  # images=2 means completely erase images intersecting redaction
        
        # Save history
        session.mark_dirty()
        session.push_history()
        return True
    except Exception as e:
        logger.error(f"Error redacting area: {e}")
        raise


def find_matches(session: PDFSession, keyword: str, match_case: bool = False, is_regex: bool = False) -> list[dict]:
    """ค้นหาทุกหน้า คืน [{page, text, rects}] — ค้นบนข้อความที่จัดรูปภาษาไทยแล้ว (ดู text_index.py)"""
    doc = require_unlocked(session)
    pattern = text_index.keyword_pattern(keyword, match_case, is_regex)
    found = []
    for page in doc:
        pt = text_index.page_text(page)
        for start, end in text_index.find(pt, pattern):
            rects = text_index.rects_for(pt, start, end)
            if rects:
                found.append({"page": page.number, "text": pt.text[start:end], "rects": rects})
    return found


IMAGE_AREA_HINT = 0.05


def pages_with_images(session: PDFSession) -> list[int]:
    """หน้าที่มีรูปภาพกินพื้นที่ ≥5% (เลขหน้าเริ่ม 1) — ข้อความในรูป (ลายเซ็น+ชื่อ ตราประทับ ภาพสแกน)
    ค้นหา/เซ็นเซอร์ด้วยคำไม่ได้ ต้องใช้ OCR หรือปิดทับด้วยมือ — ใช้แจ้งผู้ใช้ตอนค้นไม่เจอ"""
    doc = require_unlocked(session)
    pages = []
    for page in doc:
        area = abs(page.rect)
        covered = sum(abs(fitz.Rect(i["bbox"]) & page.rect) for i in page.get_image_info())
        if area and covered / area >= IMAGE_AREA_HINT:
            pages.append(page.number + 1)
    return pages


MASK = "█"


def _mask(value: str, pattern) -> tuple[str, int]:
    """แทนส่วนที่ตรงกับคำค้นด้วย █ (ค้นบนข้อความที่จัดรูปไทยแล้ว เหมือนค้นในหน้า)"""
    if not value or not isinstance(value, str):
        return value, 0
    norm = thai_text.normalize(value)
    hits = [m for m in pattern.finditer(norm) if m.end() > m.start() and m.group().strip()]
    if not hits:
        return value, 0
    out, last = [], 0
    for m in hits:
        out.append(norm[last:m.start()])
        out.append(MASK * max(3, len(m.group().strip())))
        last = m.end()
    out.append(norm[last:])
    return "".join(out), len(hits)


def _refresh_annot_appearance(page: fitz.Page, annot: fitz.Annot) -> None:
    """หลังแก้ข้อความ: กล่องข้อความ/กรอบของแอปวาดภาพข้อความใหม่ด้วยฟอนต์ไทยของเรา — annot.update() ของ MuPDF
    จะสร้างภาพใหม่ที่ไม่มีอักษรไทย (เหลือแต่ตัวอังกฤษ/ตัวเลข)"""
    from app.services import annotation_service as A

    if not A._is_app_text_annot(annot):
        annot.update()
        return
    content = (annot.info or {}).get("content") or ""
    fontname, fontsize, _ = A._get_annot_meta(annot)
    color = A._get_annot_color(annot)
    if A._get_annot_type_name(annot) == "rect":
        A._set_text_appearance(page, annot, content, (0, 0, 0), None, None, border_color=color or (0.9, 0.3, 0.15))
    else:
        A._set_text_appearance(page, annot, content, color or (0, 0, 0), fontname, fontsize or 12)


def scrub_hidden_text(doc: fitz.Document, pattern) -> int:
    """ลบคำค้นออกจากส่วนที่ "ไม่ใช่ข้อความบนหน้า" ซึ่ง apply_redactions ไม่แตะ — คืนจำนวนจุดที่แก้

    เดิมเซ็นเซอร์แล้วคำยังอยู่ใน: ค่าช่องกรอกฟอร์ม (ยังแสดงบนหน้าด้วย!), โน้ต/ความคิดเห็น (popup),
    บุ๊กมาร์ก, ข้อมูลเมตา (ชื่อเรื่อง/ผู้เขียน) — เปิดดูหรือคัดลอกได้ ถือว่าข้อมูลรั่ว
    ช่องฟอร์มนับแยกไม่ได้ (ข้อความในช่องถูกนับรวมกับผลค้นบนหน้าแล้ว) จึงไม่นับซ้ำ"""
    count = 0
    for pno in range(doc.page_count):
        page = doc[pno]
        for w in list(page.widgets() or []):
            if w.field_type not in (fitz.PDF_WIDGET_TYPE_TEXT, fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
                continue
            changed = False
            if isinstance(w.field_value, str):
                masked, n = _mask(w.field_value, pattern)
                if n:
                    w.field_value, changed = masked, True
            label, n = _mask(w.field_label or "", pattern)
            if n:
                w.field_label, changed = label, True
            if changed:
                w.update()
        edits = []
        for annot in list(page.annots() or []):
            if annot.type[0] in (fitz.PDF_ANNOT_WIDGET, fitz.PDF_ANNOT_REDACT):
                continue
            info, hit = annot.info, 0
            new = {}
            for key in ("content", "title", "subject"):
                masked, n = _mask(info.get(key, ""), pattern)
                if n:
                    new[key], hit = masked, hit + n
            if hit:
                edits.append((annot.xref, new, hit))
        for xref, new, hit in edits:  # วาดภาพใหม่สร้างหน้าชั่วคราว → object เดิมใช้ไม่ได้ ต้อง load ใหม่ทีละตัว
            page = doc[pno]
            annot = page.load_annot(xref)
            if annot is None:
                continue
            annot.set_info(**new)
            _refresh_annot_appearance(page, annot)
            count += hit
    toc = doc.get_toc(simple=False)
    toc_hits = 0
    for item in toc:
        item[1], n = _mask(item[1], pattern)
        toc_hits += n
    if toc_hits:
        doc.set_toc(toc)
        count += toc_hits
    meta = dict(doc.metadata or {})
    meta_hits = 0
    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
        meta[key], n = _mask(meta.get(key) or "", pattern)
        meta_hits += n
    if meta_hits:
        doc.set_metadata({k: meta[k] for k in ("title", "author", "subject", "keywords", "creator", "producer")})
        count += meta_hits
    try:
        xml = doc.get_xml_metadata()
    except Exception:
        xml = ""
    if xml and _mask(xml, pattern)[1]:
        doc.del_xml_metadata()  # XMP ซ้ำกับข้อมูลเมตาด้านบน แก้บางส่วนเสี่ยงทำ XML พัง จึงลบทั้งก้อน
        count += 1
    return count


def redact_by_search(session: PDFSession, keyword: str, match_case: bool = False, is_regex: bool = False) -> int:
    """ค้นหาคำ/regex ทุกหน้าแล้วปิดทับถาวร คืนจำนวนตำแหน่งที่ปิด (-1 = ผิดพลาด, ValueError = คำค้นไม่ถูกต้อง)

    เดิมใช้ page.search_for (เทียบข้อความดิบ) → PDF จาก Word/หนังสือราชการที่เก็บสระอำผิดรูป ค้นไม่เจอเงียบๆ
    ตอนนี้ค้นบนข้อความที่จัดรูปแล้ว ข้ามช่องว่าง/บรรทัดได้ และปิดตามกรอบอักขระจริง
    """
    doc = require_unlocked(session)
    try:
        matches = find_matches(session, keyword, match_case, is_regex)
        by_page: dict[int, list] = {}
        for m in matches:
            by_page.setdefault(m["page"], []).extend(m["rects"])
        for page_no, rects in by_page.items():
            page = doc[page_no]
            for rect in rects:
                page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
        hidden = scrub_hidden_text(doc, text_index.keyword_pattern(keyword, match_case, is_regex))
        total = len(matches) + hidden
        if total:
            session.mark_dirty()
            session.push_history()
        return total
    except ValueError:
        raise
    except Exception:
        logger.exception("redact_by_search ล้มเหลว")
        return -1
