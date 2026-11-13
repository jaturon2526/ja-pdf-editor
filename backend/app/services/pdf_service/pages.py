"""pdf_service.pages — bookmark และจัดการหน้า (ลบ/หมุน/เรียง/ส่งออก/แยกไฟล์)"""
from __future__ import annotations

import zipfile
from pathlib import Path
import fitz
from app.core.session import PDFSession
from app.services.pdf_service.core import (
    PDFError,
    _flush_mupdf_warnings,
    has_digital_signatures,
    normalize_page_rotation,
    require_unlocked,
)


# ---------- Bookmark (ผู้ใช้แจ้งบั๊ก: bookmark หายหลังกด Save แล้ว Download แล้วเปิดไฟล์ใหม่) ----------
#
# ฟีเจอร์เปลี่ยนชื่อ bookmark ที่ทำไปก่อนหน้านี้เก็บ bookmark เป็น React state ล้วนๆ ฝั่ง frontend
# (App.jsx: useState([])) ไม่เคยถูกเขียนลงไปในตัวไฟล์ PDF จริงเลย ดังนั้นพอดาวน์โหลดไฟล์แล้วเปิดใหม่
# (ไม่ว่าในแอปนี้เองหรือโปรแกรมอื่น) bookmark ที่เพิ่มไว้จึงหายไปเสมอ — ทางแก้ที่ถูกต้องคือย้าย bookmark
# ไปเก็บเป็น PDF outline/TOC จริง (สิ่งเดียวกับที่ Acrobat/โปรแกรมอ่าน PDF อื่นเรียกว่า "Bookmarks panel")
# ผ่าน fitz.Document.get_toc()/set_toc() ซึ่งเป็นส่วนหนึ่งของโครงสร้างไฟล์ PDF จริง (ไม่ใช่ metadata
# แยกต่างหากที่แอปนี้เก็บเอง) — เพราะ set_toc() แก้ไข fitz.Document ที่เปิดอยู่ในหน่วยความจำทันที
# (เหมือน annotation/text edit) bookmark จึงติดไปกับ session.doc.tobytes()/saveIncr() โดยอัตโนมัติ
# ทั้งตอน undo/redo snapshot และไฟล์ที่ได้จาก get_download_path ด้านบน โดยไม่ต้อง special-case เพิ่ม
# (ต่างจากฟีเจอร์รหัสผ่านที่ต้องรอ "ตอนดาวน์โหลด" เท่านั้น) และเป็นผลพลอยได้ที่ไฟล์ที่ upload เข้ามา
# ซึ่งมี bookmark ติดมาอยู่แล้ว (จากที่อื่น หรือเคยดาวน์โหลดจากแอปนี้เอง) จะโชว์ใน Bookmarks tab ทันที
BOOKMARK_LABEL_MAX = 300


def _normalize_toc_levels(toc: list[list]) -> list[list]:
    """set_toc() ต้องการ: รายการแรก level 1 และแต่ละรายการลึกกว่ารายการก่อนหน้าได้ไม่เกิน 1 ชั้น
    (ลบบุ๊กมาร์กแม่ออกแล้ว ลูกต้องเลื่อนขึ้นมาแทน ไม่งั้น set_toc error)"""
    prev = 0
    for entry in toc:
        entry[0] = max(1, min(int(entry[0]), prev + 1))
        prev = entry[0]
    return toc


def _shown_in_panel(entry: list) -> bool:
    """บุ๊กมาร์กที่แสดงในแผง = ชี้ไปหน้าในเอกสารนี้ (ที่เหลือ เช่น ลิงก์เว็บ/ไฟล์อื่น เก็บไว้ในไฟล์ตามเดิมแต่ไม่แสดง)"""
    return entry[2] >= 1


def get_bookmarks(session: PDFSession) -> list[dict]:
    """บุ๊กมาร์ก (PDF outline/TOC) ปัจจุบัน → [{"page", "label", "level", "ref"}]

    - page 0-based ตรงกับเลขหน้าที่ frontend ใช้ · level = ชั้น (1 = บนสุด) ให้แผงแสดงย่อหน้าตามโครงสร้างเดิม
    - ref = ตำแหน่งในสารบัญเดิม ส่งกลับมาตอนบันทึกเพื่อคงจุดหมายเดิมไว้ (ตำแหน่งบนหน้า/ซูม/ยุบ-ขยาย)
    - รายการที่ไม่ได้ชี้หน้าในเอกสาร (ลิงก์เว็บ ฯลฯ) ไม่แสดง แต่ set_bookmarks เก็บไว้ให้ ไม่หายตอนแก้บุ๊กมาร์กอื่น"""
    doc = require_unlocked(session)
    n = doc.page_count
    result: list[dict] = []
    for ref, (level, title, page_1based, *_rest) in enumerate(doc.get_toc(simple=False)):
        if 1 <= page_1based <= n:
            result.append({"page": page_1based - 1, "label": title, "level": level, "ref": ref})
    return result


def set_bookmarks(session: PDFSession, items: list[dict]) -> list[dict]:
    """เขียนบุ๊กมาร์กทั้งชุดใหม่ทับของเดิม (full replace — PyMuPDF TOC ไม่มี id ต่อรายการ)

    เดิมเขียนใหม่ทุกรายการเป็นชั้นเดียว ชี้หัวหน้ากระดาษ: แก้/ลบ/เพิ่มบุ๊กมาร์กอันเดียว โครงสร้างหลายชั้นของไฟล์
    (เช่น บทที่ 1 > 1.1) ยุบหมด, จุดหมายกลางหน้ากลายเป็นหัวหน้า, และบุ๊กมาร์กลิงก์เว็บหายไปเลย — ตอนนี้รายการที่มี
    ref ใช้ชั้นและจุดหมายเดิม (ถ้าย้ายหน้าค่อยชี้หัวหน้าใหม่) และรายการที่ไม่แสดงในแผงคงอยู่ตำแหน่งเดิม"""
    doc = require_unlocked(session)
    n = doc.page_count
    old = doc.get_toc(simple=False)
    for item in items:
        page0 = item.get("page")
        if page0 is None or not (0 <= page0 < n):
            raise PDFError(f"เลขหน้า bookmark {page0} อยู่นอกช่วง (มีทั้งหมด {n} หน้า)")
        label = str(item.get("label", "")).strip()
        if not label:
            raise PDFError("ชื่อ bookmark ห้ามว่าง")
        if len(label) > BOOKMARK_LABEL_MAX:
            raise PDFError(f"ชื่อ bookmark ยาวได้ไม่เกิน {BOOKMARK_LABEL_MAX} ตัวอักษร")

    toc: list[list] = []
    placed: dict[int, int] = {}  # ref เดิม → ตำแหน่งในรายการใหม่
    for item in items:
        label = str(item["label"]).strip()
        page1 = item["page"] + 1
        ref = item.get("ref")
        src = old[ref] if isinstance(ref, int) and 0 <= ref < len(old) and _shown_in_panel(old[ref]) else None
        level = item.get("level") or (src[0] if src else 1)
        if src is not None and src[2] == page1 and len(src) > 3:
            dest = dict(src[3])
            dest.pop("xref", None)
            toc.append([level, label, page1, dest])
        else:
            toc.append([level, label, page1])
        if src is not None:
            placed[ref] = len(toc) - 1

    # รายการที่ไม่แสดงในแผง (ลิงก์เว็บ/ไฟล์อื่น) แทรกกลับหลังรายการที่อยู่ก่อนหน้ามันในสารบัญเดิม
    keyed = [((i, 0, 0), e) for i, e in enumerate(toc)]
    for ref, entry in enumerate(old):
        if _shown_in_panel(entry) or (len(entry) > 3 and entry[3].get("kind") == fitz.LINK_GOTO):
            continue  # บุ๊กมาร์กภายในที่หน้าปลายทางหายไปแล้ว ไม่ต้องเก็บ
        anchor = max((placed[r] for r in placed if r < ref), default=-1)
        dest = {k: v for k, v in (entry[3] if len(entry) > 3 else {}).items() if k != "xref"}
        keyed.append(((anchor, 1, ref), [entry[0], entry[1], -1, dest] if dest else [entry[0], entry[1], -1]))
    toc = [e for _k, e in sorted(keyed, key=lambda kv: kv[0])]

    doc.set_toc(_normalize_toc_levels(toc))
    session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดูหมายเหตุ _doc_dirty ใน session.py
    _flush_mupdf_warnings(f"set_bookmarks session={session.session_id}")
    return get_bookmarks(session)


def export_pages(session: PDFSession, page_numbers: list[int]) -> bytes:
    """ส่งออกเฉพาะหน้าที่เลือก (page_numbers, 0-based) เป็นไบต์ไฟล์ PDF ใหม่แยกต่างหาก (ผู้ใช้แจ้งขอ
    ฟีเจอร์นี้: เลือกหลายหน้าในแผงเอกสารด้านซ้าย คลิกขวา ส่งออกเป็นไฟล์ใหม่) — ไม่แตะเอกสารต้นฉบับ/
    working ที่กำลังแก้ไขอยู่เลย (ดู pages_document) เรียงตามลำดับเลขหน้าจากน้อยไปมากเสมอ (ไม่ใช่ลำดับที่ผู้ใช้คลิกเลือก) ให้ไฟล์ผลลัพธ์
    อ่านง่าย/เรียงถูกต้องเสมอไม่ว่าจะคลิกเลือกหน้าตามลำดับไหนก็ตาม
    """
    doc = require_unlocked(session)
    if not page_numbers:
        raise PDFError("ไม่ได้เลือกหน้าที่จะส่งออก")

    unique_sorted_pages = sorted(set(page_numbers))
    for page_number in unique_sorted_pages:
        if not (0 <= page_number < doc.page_count):
            raise PDFError(f"page_number {page_number} อยู่นอกช่วง (มีทั้งหมด {doc.page_count} หน้า)")

    return pages_document(session, unique_sorted_pages)


def pages_document(session: PDFSession, page_numbers: list[int]) -> bytes:
    """PDF ใหม่ที่มีเฉพาะหน้าที่ระบุ ตามลำดับที่ให้มา — สำเนาเอกสารปัจจุบัน (รวมการแก้ไขที่ยังไม่บันทึก) แล้ว select()

    เดิมสร้างเอกสารเปล่าแล้ว insert_pdf() ทีละหน้า: ช่องกรอกฟอร์มหาย, ลิงก์ไปหน้าอื่นและบุ๊กมาร์กหาย, ฟอนต์/รูปถูก
    คัดลอกซ้ำทุกหน้า (3 หน้าใหญ่กว่าต้นฉบับ 12 หน้าเกือบ 3 เท่า) — select() เก็บฟอร์ม ลิงก์และบุ๊กมาร์กที่ชี้หน้าที่
    เหลืออยู่ (เลขหน้าเปลี่ยนตาม) และใช้ฟอนต์/รูปร่วมกัน · เอกสารที่ตั้งรหัสผ่านไว้ (ไฟล์ > เข้ารหัส PDF) ไฟล์ที่ได้
    เข้ารหัสด้วยรหัสผ่านเดียวกัน เหมือนตอนดาวน์โหลดทั้งไฟล์"""
    doc = require_unlocked(session)
    work = fitz.open("pdf", doc.tobytes())
    try:
        work.select(page_numbers)
        data = work.tobytes(garbage=3, deflate=True)
    finally:
        work.close()
    if session.output_password:
        import os
        import tempfile

        from app.services.pdf_service.core import encrypt_pdf_file

        fd, src = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        out = src + ".enc.pdf"
        try:
            Path(src).write_bytes(data)
            encrypt_pdf_file(src, out, session.output_password, session.output_encryption or "aes256")
            data = Path(out).read_bytes()
        finally:
            for p in (src, out):
                if os.path.exists(p):
                    os.remove(p)
    return data


def delete_pages(session: PDFSession, page_numbers: list[int]) -> bool:
    """ลบหน้าตามที่ระบุ แล้วเรียงหน้าใหม่

    - ต้องเหลืออย่างน้อย 1 หน้า (เดิมลบได้หมด แล้วบันทึก/ดาวน์โหลดไม่ได้อีก: "cannot save with zero pages")
    - เอกสารที่ลงลายเซ็นดิจิทัลแล้วลบหน้าไม่ได้ (ลายเซ็นจะเสีย) — เหมือนย้ายหน้า
    - บุ๊กมาร์กที่ชี้หน้าที่ลบถูกลบด้วย (เดิมค้างอยู่ในไฟล์ กดแล้วไม่ไปไหน) · ทะเบียนย่อหน้าที่แก้ไขเลื่อนตามเลขหน้าใหม่"""
    doc = require_unlocked(session)
    n = doc.page_count
    doomed = sorted({p for p in page_numbers if 0 <= p < n})
    if not doomed:
        return False
    if len(doomed) >= n:
        raise PDFError("ลบทุกหน้าไม่ได้ — เอกสารต้องเหลืออย่างน้อย 1 หน้า")
    if session.signed_pdf_bytes is not None or has_digital_signatures(doc):
        raise PDFError(
            "เอกสารนี้มีลายเซ็นดิจิทัลฝังอยู่ ลบหน้าไม่ได้ เพราะลายเซ็นจะใช้งานไม่ได้ — "
            "กด Undo ย้อนไปก่อนจุดที่เซ็นถ้าต้องการลบหน้า"
        )

    before = doc.get_toc(simple=False)
    doc.delete_pages(doomed)
    toc = doc.get_toc(simple=False)
    if len(toc) == len(before):
        dead = [
            i for i, (b_entry, a_entry) in enumerate(zip(before, toc))
            if b_entry[2] >= 1 and a_entry[2] < 1
        ]
        if dead:
            kept = [e[:3] + ([{k: v for k, v in e[3].items() if k != "xref"}] if len(e) > 3 else [])
                    for i, e in enumerate(toc) if i not in set(dead)]
            doc.set_toc(_normalize_toc_levels(kept))

    gone = set(doomed)
    old_to_new, shift = {}, 0
    for old in range(n):
        if old in gone:
            shift += 1
        else:
            old_to_new[old] = old - shift
    session.text_edits = {old_to_new[p]: e for p, e in session.text_edits.items() if p in old_to_new}
    session.mark_dirty()
    _flush_mupdf_warnings(f"delete_pages session={session.session_id}")
    return True


def rotate_pages(session: PDFSession, page_numbers: list[int], angle: int) -> bool:
    """หมุนหน้า (ผู้ใช้แจ้งขอฟีเจอร์หมุนหน้า) - เปลี่ยน 90, 180, 270 องศา"""
    doc = require_unlocked(session)
    if not page_numbers:
        return False
        
    normalize = session.signed_pdf_bytes is None and not has_digital_signatures(doc)
    for p in page_numbers:
        if 0 <= p < doc.page_count:
            page = doc[p]
            new_rotation = (page.rotation + angle) % 360
            page.set_rotation(new_rotation)
            if normalize:
                # หมุนเข้าเนื้อหน้าจริง (/Rotate กลับเป็น 0) — พิกัดบนจอ = พิกัดใน PDF (ดู core.normalize_page_rotation)
                to_visible = page.rotation_matrix
                if normalize_page_rotation(page):
                    # ทะเบียนย่อหน้าที่เคยแก้ไข (กรอบในพิกัดหน้าเดิม) หมุนตามเนื้อหน้า ให้คลิกแก้ซ้ำได้ตรงตำแหน่ง
                    for rec in session.text_edits.get(p, {}).values():
                        r = rec.get("rect")
                        if r:
                            nr = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"]) * to_visible
                            rec["rect"] = {"x0": nr.x0, "y0": nr.y0, "x1": nr.x1, "y1": nr.y1}

    session.mark_dirty()
    return True


def reorder_pages(
    session: PDFSession,
    page_numbers: list[int],
    target_page: int | None = None,
    direction: str | None = None,
) -> bool:
    """ย้ายตำแหน่งหน้า (page_numbers, 0-based, อาจเลือกหลายหน้าพร้อมกัน) ไปยังตำแหน่งใหม่จริงในเอกสาร
    (ผู้ใช้แจ้งขอฟีเจอร์นี้จากแผงหน้าเอกสารด้านซ้าย: กดเมาส์ค้างที่ thumbnail แล้วลากไปวาง หรือคลิกขวา
    เลือกเลื่อนหน้าขึ้น/ลง) คืน True ถ้ามีการเปลี่ยนแปลงจริง, False ถ้าเป็น no-op (เช่น ลากวางที่เดิม หรือ
    กด "เลื่อนขึ้น" ตอนหน้าที่เลือกอยู่บนสุดแล้ว) — no-op ไม่ถือเป็นข้อผิดพลาด แค่ไม่ต้อง push_history()

    วิธีคิด: มองหน้าที่ "ไม่ได้ถูกย้าย" (remaining) เป็นแกนอ้างอิงเดิมตามลำดับเดิม แล้วหาว่ากลุ่มหน้าที่จะ
    ย้าย (moving) ควรไปแทรกอยู่ตำแหน่งไหนใน remaining นั้น:
    - target_page (ใช้ตอนลากวาง): แทรกก่อนหน้าเลขนี้ (นับจาก "จำนวนหน้าใน remaining ที่เลขน้อยกว่า
      target_page") — คำนวณแบบนี้ทำให้ถูกต้องเสมอไม่ว่า target_page จะเป็นหน้าที่ไม่ได้ย้ายจริงๆ (กรณีปกติ)
      หรือบังเอิญตรงกับหน้าที่กำลังถูกย้ายเอง (ลากวางใกล้ตัวเอง — ผลลัพธ์จะเป็น no-op หรือใกล้เคียงเดิม)
    - direction (ใช้ตอนคลิกขวาเลื่อนขึ้น/ลง): มองกลุ่มหน้าที่เลือกเป็นก้อนเดียว หาตำแหน่งปัจจุบันในแกน
      remaining (นับจำนวนหน้าที่เหลือซึ่งอยู่ก่อนหน้าแรกสุดของกลุ่ม) แล้วขยับก้อนนั้นข้ามหน้าเดียวที่อยู่
      ติดกันไปทีละ 1 ตำแหน่ง (ใช้ได้ทั้งกลุ่มที่ติดกันและไม่ติดกัน — non-contiguous multi-select ก็ขยับเป็น
      ก้อนเดียวกันเสมอ)

    ใช้ fitz.Document.select(new_order) ซึ่งรับ list ของเลขหน้าเดิม (0-based) เรียงเป็นลำดับใหม่ที่ต้องการ
    แล้ว rebuild เอกสารให้ตรงตามนั้น — ครอบคลุมทุกหน้าในเอกสาร (permutation เต็ม ไม่ใช่แค่ subset แบบ
    export_pages ด้านบน) จากนั้นต้องแปลง key ของ session.text_edits (ทะเบียนย่อหน้าที่เคยแก้ไขไปแล้ว คีย์
    เป็นเลขหน้า — ดู app/core/session.py) ให้ตรงกับเลขหน้าใหม่หลังสลับตำแหน่งด้วย ไม่งั้นย่อหน้าที่เคยแก้ไข
    ไว้จะ "ค้าง" อยู่ที่เลขหน้าเดิมซึ่งตอนนี้กลายเป็นเนื้อหาอื่นไปแล้ว (คลิกกลับมาแก้ไขซ้ำจะผิดหน้า)

    ข้อจำกัดทางเทคนิคจริง (ไม่ใช่การล็อกตามใจ เหมือนกับ add_password() ด้านบน): doc.select() คือการ
    rebuild โครงสร้างเอกสารใหม่ทั้งหมด (ลบ/เรียงหน้าใหม่จริงๆ ในระดับ object) ไม่ใช่การแก้ไขแบบ incremental
    เหมือนการแก้ข้อความ/แทรกรูป/annotation ทั่วไป ถ้าเอกสารมีลายเซ็นดิจิทัลฝังอยู่แล้ว การสลับหน้าจะทำให้
    ลายเซ็นเดิมใช้งานไม่ได้ทันทีโดยผู้ใช้ไม่รู้ตัว จึงยังต้องกันไว้ตรงนี้
    """
    if session.signed_pdf_bytes is not None:
        raise PDFError(
            "เอกสารนี้มีลายเซ็นดิจิทัล (PAdES) ฝังอยู่แล้ว ไม่สามารถย้าย/สลับลำดับหน้าได้ เพราะจะทำให้"
            "ลายเซ็นดิจิทัลที่ฝังไว้ใช้งานไม่ได้อีกต่อไป กรุณา Undo ย้อนกลับไปก่อนจุดที่เซ็นถ้าต้องการสลับหน้า"
        )
    doc = require_unlocked(session)
    n = doc.page_count
    moving = sorted(set(page_numbers))
    if not moving:
        raise PDFError("ไม่ได้เลือกหน้าที่จะย้าย")
    for p in moving:
        if not (0 <= p < n):
            raise PDFError(f"page_number {p} อยู่นอกช่วง (มีทั้งหมด {n} หน้า)")

    moving_set = set(moving)
    remaining = [i for i in range(n) if i not in moving_set]

    if direction is not None:
        current_pos = sum(1 for r in remaining if r < moving[0])
        pos = current_pos + (1 if direction == "down" else -1)
    elif target_page is not None:
        pos = sum(1 for r in remaining if r < target_page)
    else:
        pos = len(remaining)  # fallback: ไม่ได้ระบุปลายทางมาเลย — วางท้ายสุด

    pos = max(0, min(pos, len(remaining)))
    new_order = remaining[:pos] + moving + remaining[pos:]

    if new_order == list(range(n)):
        return False  # no-op (เช่น ลากวางตำแหน่งเดิม หรือกดเลื่อนขึ้น/ลงตอนอยู่ขอบสุดของเอกสารแล้ว)

    doc.select(new_order)
    session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดูหมายเหตุ _doc_dirty ใน session.py
    _flush_mupdf_warnings(f"reorder_pages session={session.session_id}")

    old_to_new = {old: new for new, old in enumerate(new_order)}
    session.text_edits = {
        old_to_new[old_page]: edits
        for old_page, edits in session.text_edits.items()
        if old_page in old_to_new
    }
    return True


_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-", "~": "-", "，": ",", "、": ",", ";": ",",
                         **{chr(0x0E50 + i): str(i) for i in range(10)}})  # เลขไทย ๐-๙


def parse_page_range(range_str: str, max_pages: int) -> list[int]:
    """แปลงข้อความเช่น '1,2,4-6' เป็นเลขหน้า (0-based) ตามลำดับที่พิมพ์ ไม่ซ้ำ

    - เรียงตามที่พิมพ์ ("5,1-3" → หน้า 5,1,2,3) — เดิมเรียงจากน้อยไปมากเสมอ จัดลำดับหน้าใหม่ตอนแยกไม่ได้
    - ช่วงถอยหลังได้ ("6-4" → 6,5,4) · เลขไทย ๑-๓ และขีด –/— ใช้ได้ · "-3" = หน้า 1-3, "8-" = หน้า 8 ถึงหน้าสุดท้าย"""
    pages: list[int] = []
    seen: set[int] = set()

    def add(i: int) -> None:
        if i not in seen:
            seen.add(i)
            pages.append(i)

    def num(tok: str, part: str) -> int:
        try:
            n = int(tok)
        except ValueError:
            raise PDFError(f"รูปแบบเลขหน้าไม่ถูกต้อง: {part}") from None
        if not 1 <= n <= max_pages:
            raise PDFError(f"ไม่มีหน้า {n} (เอกสารมี {max_pages} หน้า)")
        return n - 1

    for part in (range_str or "").translate(_DASHES).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            bits = part.split("-")
            if len(bits) != 2 or not (bits[0] or bits[1]):
                raise PDFError(f"รูปแบบช่วงหน้าไม่ถูกต้อง: {part}")
            start = num(bits[0], part) if bits[0] else 0
            end = num(bits[1], part) if bits[1] else max_pages - 1
            step = 1 if end >= start else -1
            for i in range(start, end + step, step):
                add(i)
        else:
            add(num(part, part))
    return pages


ZIP_MAX_PAGES = 500


IMAGE_FORMATS = {"png": ("png", "image/png"), "jpg": ("jpg", "image/jpeg")}
IMAGE_MAX_PAGES = 200       # ส่งออกเป็นรูปครั้งละไม่เกินนี้ (ไฟล์ zip ใหญ่ + ใช้เวลาเรนเดอร์)
IMAGE_MAX_SIDE_PX = 5000    # หน้าขนาดใหญ่มาก (A0, แบบแปลน) ลดความละเอียดลงให้ด้านยาวไม่เกินนี้
IMAGE_DPI_CHOICES = (100, 150, 300)


def page_image(doc, pno: int, fmt: str, dpi: int) -> bytes:
    """เรนเดอร์หน้า pno เป็นรูป PNG/JPG (พื้นขาว ไม่โปร่งใส รวม annotation/ช่องกรอกฟอร์มตามที่เห็นในหน้าจอ)"""
    page = doc[pno]
    long_side_pt = max(page.rect.width, page.rect.height) or 1
    scale = min(dpi / 72, IMAGE_MAX_SIDE_PX / long_side_pt)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    if fmt == "png":
        return pix.tobytes("png")
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(
        out, "JPEG", quality=90, optimize=True, dpi=(round(scale * 72), round(scale * 72)))
    return out.getvalue()


def extract_pages(session: PDFSession, page_range: str, mode: str, fmt: str = "pdf", dpi: int = 150) -> tuple[bytes, str, str]:
    """ดึงหน้า PDF ตามช่วงที่ระบุ คืน (file_bytes, filename, mime_type)
    fmt pdf: single = ไฟล์เดียวตามลำดับที่พิมพ์ · split = ไฟล์ละหน้าใน .zip (ชื่อไฟล์เติมเลขศูนย์ให้เรียงถูก)
    fmt png/jpg: รูปหน้าละ 1 ไฟล์ — หน้าเดียวได้ไฟล์รูปตรง ๆ (เปิด/แชร์จากมือถือได้เลย) หลายหน้ารวมเป็น .zip (ไม่ใช้ mode)"""
    doc = require_unlocked(session)
    if fmt not in ("pdf", *IMAGE_FORMATS):
        raise PDFError(f"ไม่รองรับรูปแบบไฟล์: {fmt}")
    if mode not in ("single", "split"):
        raise PDFError(f"ไม่รองรับโหมด: {mode}")
    pages = parse_page_range(page_range, doc.page_count)
    if not pages:
        raise PDFError("ไม่ได้ระบุหน้าที่ต้องการดึง")
    base = Path(session.original_filename or "document.pdf").stem or "document"
    width = len(str(doc.page_count))
    import io

    if fmt in IMAGE_FORMATS:
        ext, mime = IMAGE_FORMATS[fmt]
        if dpi not in IMAGE_DPI_CHOICES:
            raise PDFError(f"ความละเอียดต้องเป็น {', '.join(map(str, IMAGE_DPI_CHOICES))} dpi")
        if len(pages) > IMAGE_MAX_PAGES:
            raise PDFError(f"ส่งออกเป็นรูปภาพได้ครั้งละไม่เกิน {IMAGE_MAX_PAGES} หน้า")
        if len(pages) == 1:
            return page_image(doc, pages[0], fmt, dpi), f"{base} (หน้า {pages[0] + 1}).{ext}", mime
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:  # PNG/JPG บีบอัดอยู่แล้ว
            for pno in pages:
                zf.writestr(f"{base}_หน้า_{pno + 1:0{width}d}.{ext}", page_image(doc, pno, fmt, dpi))
        return buf.getvalue(), f"{base} (รูปภาพ {len(pages)} หน้า).zip", "application/zip"

    if mode == "single":
        label = _range_label(pages)
        return pages_document(session, pages), f"{base} (หน้า {label}).pdf", "application/pdf"

    if len(pages) > ZIP_MAX_PAGES:
        raise PDFError(f"แยกเป็นไฟล์ละหน้าได้ครั้งละไม่เกิน {ZIP_MAX_PAGES} หน้า")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pno in pages:
            zf.writestr(f"{base}_หน้า_{pno + 1:0{width}d}.pdf", pages_document(session, [pno]))
    return buf.getvalue(), f"{base} (แยก {len(pages)} หน้า).zip", "application/zip"


def _range_label(pages: list[int]) -> str:
    """[0,1,2,4] → "1-3,5" (ใช้ตั้งชื่อไฟล์) — ยาวเกินไปย่อเป็น "1-3,5 ..." """
    parts, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        parts.append(f"{pages[i] + 1}" if i == j else f"{pages[i] + 1}-{pages[j] + 1}")
        i = j + 1
    label = ",".join(parts)
    return label if len(label) <= 40 else label[:40].rsplit(",", 1)[0] + " ..."


# ---------- ไฟล์สำหรับพิมพ์ ----------

def build_print_pdf(session: PDFSession, layout: str = "as_shown") -> bytes:
    """PDF สำหรับพิมพ์แบบ "ตามที่เห็นบนจอ"

    ปัญหาเดิม: หน้าที่หมุน 90°/270° เป็นหน้าแนวนอน ตอนพิมพ์ลงกระดาษแนวตั้ง macOS/เครื่องพิมพ์จะหมุนหน้า
    ให้เองทวนเข็ม 90° — หน้าที่ผู้ใช้ "หมุนซ้าย" จึงออกมากลับหัวในตัวอย่างก่อนพิมพ์
    วิธีนี้วางแต่ละหน้า "ตามที่เห็นบนจอ" (รวม annotation) ลงกระดาษแนวตั้งขนาดเดียวกับหน้าเดิม
    ย่อให้พอดีแล้วจัดกึ่งกลาง ไม่มีหน้าแนวนอนเหลือให้เครื่องพิมพ์หมุนอีก

    layout "auto": หน้าตามไฟล์ (เครื่องพิมพ์หมุนหน้าแนวนอนเอง) — เดิมพิมพ์จากไฟล์ดาวน์โหลด ซึ่งถ้าตั้งรหัสผ่านไว้
    จะเป็นไฟล์เข้ารหัส หน้าต่างพิมพ์ (iframe ซ่อน) ขึ้นช่องรหัสผ่านที่มองไม่เห็น พิมพ์ไม่ออก · ไฟล์พิมพ์ไม่เข้ารหัส
    และไม่ถูกเก็บที่ไหน
    """
    if layout not in ("as_shown", "auto"):
        raise PDFError("รูปแบบการพิมพ์ไม่รองรับ")
    require_unlocked(session)
    session.flush_to_disk()
    src = fitz.open(session.working_path)
    out = fitz.open()
    try:
        from app.services import annotation_service
        annotation_service.ensure_text_appearances(src, user_id=session.user_id)  # กล่องข้อความรุ่นเก่า
        src.bake(annots=True, widgets=True)  # ไฮไลต์/โน้ต/ฟอร์ม → เนื้อหาหน้า (show_pdf_page ไม่รวม annotation)
        if layout == "auto":
            return src.tobytes(garbage=3, deflate=True)
        for page in src:
            if page.rotation:
                page.remove_rotation()  # ทำให้เนื้อหาหมุนจริงตามที่เห็นบนจอ (ไม่พึ่งค่า /Rotate)
            w, h = page.rect.width, page.rect.height
            sheet_w, sheet_h = min(w, h), max(w, h)
            scale = min(sheet_w / w, sheet_h / h)
            tw, th = w * scale, h * scale
            target = fitz.Rect((sheet_w - tw) / 2, (sheet_h - th) / 2, (sheet_w + tw) / 2, (sheet_h + th) / 2)
            out.new_page(width=sheet_w, height=sheet_h).show_pdf_page(target, src, page.number)
        return out.tobytes(garbage=3, deflate=True)
    finally:
        out.close()
        src.close()
