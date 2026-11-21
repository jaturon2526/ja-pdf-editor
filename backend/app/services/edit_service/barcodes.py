"""ย้าย/ลบบาร์โค้ดและ QR ในหน้า (v1.41.0, ผู้ใช้ขอ 2026-11-20: "ลบหรือย้ายได้ก็พอ ถ้าจะเพิ่มใหม่ค่อยกดเพิ่ม")

ใช้ได้กับบาร์โค้ดทุกแบบในหน้า — ที่แทรกจากแอป (เวกเตอร์จาก BWIPP), ที่มีมากับไฟล์ (เวกเตอร์หรือรูปภาพ):
1. ตรวจหา: เรนเดอร์หน้า (ไม่รวม annotation) แล้วอ่านด้วย zxing-cpp (ตัวเดียวกับตรวจสลิป) → ชนิด + ข้อความ + ตำแหน่ง
   แล้ว "ขยายให้พอดีของจริง": รวมกรอบรูปทรง/รูปภาพที่ซ้อนกับตำแหน่งที่อ่านได้ (บาร์โค้ด 1 มิติ zxing อาจให้แค่เส้นสแกน)
   + ตัวเลขใต้/เหนือบาร์โค้ด 1 มิติ (human-readable) ที่อยู่ชิดกันในแนวเดียวกัน
2. ย้าย: สำเนาหน้าที่ตัดทุกอย่างนอกกรอบออก → ``show_pdf_page`` ไปวางที่ใหม่ (ยังเป็นเวกเตอร์ สแกนได้เหมือนเดิม)
   แล้วลบของเดิมในกรอบ (ข้อความ + พิกเซลรูป + รูปทรงที่อยู่ในกรอบ — รูปทรงที่แค่พาดผ่านกรอบวาดคืนตามเดิม)
3. ลบ: ขั้นตอนลบของเดิมอย่างเดียว

ไม่แก้ข้อมูลในบาร์โค้ด — อยากเปลี่ยนให้ลบแล้วแทรกใหม่ (เมนูแทรก › บาร์โค้ด/QR) · หน้าที่หมุนยังไม่รองรับ
"""
from __future__ import annotations

import fitz

from app.core.session import PDFSession
from app.services.edit_service.tables import _drop_degenerate_rects, _redraw
from app.services.pdf_service import PDFError, require_unlocked

_RENDER_LONG_SIDE_PX = 2600  # A4 ≈ 3 เท่า — บาร์โค้ดแท่งบาง 0.25 pt ยังอ่านได้
_MATCH_PT = 3.0
MIN_SIZE_PT = 8.0

_TWO_D = {"QRCode", "MicroQRCode", "RMQRCode", "DataMatrix", "Aztec", "PDF417", "MaxiCode"}


def _rotated_error() -> PDFError:
    return PDFError("ยังย้าย/ลบบาร์โค้ดในหน้าที่หมุนไม่ได้ — หมุนหน้ากลับเป็นแนวเดิมก่อน")


def _content_page(page: fitz.Page) -> fitz.Page:
    from app.services.pdf_service.text_index import content_page

    return content_page(page)


def _span(r: fitz.Rect, other: fitz.Rect) -> bool:
    """เทียบพิกัดเอง — กรอบของเส้นตรง/แท่งกว้าง 0 ว่าง (``Rect.intersects`` ของกรอบว่างเป็นเท็จ)"""
    return not (r.x1 < other.x0 or r.x0 > other.x1 or r.y1 < other.y0 or r.y0 > other.y1)


def _within(r: fitz.Rect, box: fitz.Rect) -> bool:
    return r.x0 >= box.x0 and r.x1 <= box.x1 and r.y0 >= box.y0 and r.y1 <= box.y1


def _snap(seen: fitz.Rect, two_d: bool, drawings: list[dict], images: list[fitz.Rect],
          lines: list[fitz.Rect]) -> fitz.Rect:
    """ขยายกรอบที่ zxing เห็นให้ครอบชิ้นงานจริง (แท่ง/โมดูลทั้งหมด + ตัวเลขประกอบของบาร์โค้ด 1 มิติ)"""
    # บาร์โค้ด 1 มิติ: zxing อาจคืนแค่เส้นสแกนแนวนอน → หาแท่งในแนวตั้งที่ซ้อนกับช่วง x เดียวกันได้ไกลขึ้น
    reach = fitz.Rect(seen.x0 - 2, seen.y0 - (2 if two_d else 40), seen.x1 + 2, seen.y1 + (2 if two_d else 40))
    core = fitz.Rect(seen)
    for d in drawings:
        r = fitz.Rect(d["rect"]).normalize()
        # พื้นหลัง/ขอบว่าง (quiet zone) ของบาร์โค้ดเอง: กรอบที่ครอบสิ่งที่อ่านได้และใหญ่กว่าไม่มาก
        # (1 มิติ: zxing อาจให้แค่เส้นสแกน จึงยอมให้สูงกว่าได้มากกว่า)
        max_h = seen.height * 1.5 if two_d else max(seen.height * 2.5, seen.height + 60)
        if _within(seen, r + (-1, -1, 1, 1)) and r.width <= max(seen.width * 1.5, seen.width + 40) and r.height <= max_h:
            core |= r
            continue
        if r.width > seen.width * 1.6 or r.height > max(seen.height * 3, 80):
            continue  # เส้นกรอบใหญ่ / เส้นตารางที่แค่พาดผ่าน ไม่ใช่ส่วนของบาร์โค้ด
        if _span(r, reach) and _within(r, reach + (-1, -1, 1, 1)) and _span(r, fitz.Rect(seen.x0, reach.y0, seen.x1, reach.y1)):
            core |= r
    for r in images:
        if r.intersects(seen) and r.width * r.height <= max(seen.width * seen.height, 1) * 8 + 400:
            core |= r  # บาร์โค้ดเป็นรูป → ทั้งรูป
    if not two_d:
        # ตัวเลขใต้/เหนือแท่ง (ห่าง ≤ 6 pt, อยู่ในช่วง x ของบาร์โค้ด, ตัวไม่ใหญ่)
        for r in lines:
            if r.height > 16 or r.x0 < core.x0 - 6 or r.x1 > core.x1 + 6:
                continue
            below = r.y1 > core.y1 and r.y0 - core.y1 <= 6 and r.y0 >= core.y0
            above = r.y0 < core.y0 and core.y0 - r.y1 <= 6 and r.y1 <= core.y1
            if below or above:
                core |= r
    return core + (-1, -1, 1, 1)


def find_barcodes(page: fitz.Page) -> list[dict]:
    """บาร์โค้ด/QR ทั้งหมดในหน้า → ``[{id, bbox, format, text}]`` (พิกัดหน้า pt) — หน้าที่หมุนคืนรายการว่าง"""
    import zxingcpp
    from PIL import Image

    if page.rotation:
        return []
    zoom = min(3.0, _RENDER_LONG_SIDE_PX / max(page.rect.width, page.rect.height))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, annots=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    results = zxingcpp.read_barcodes(img)
    if not results:
        return []
    content = _content_page(page)
    drawings = content.get_drawings()
    images = [fitz.Rect(info["bbox"]) for info in content.get_image_info()]
    lines = [fitz.Rect(ln["bbox"]) for b in content.get_text("dict")["blocks"] if b.get("type") == 0
             for ln in b["lines"]]
    found: list[dict] = []
    for res in results:
        p = res.position
        xs = [p.top_left.x, p.top_right.x, p.bottom_left.x, p.bottom_right.x]
        ys = [p.top_left.y, p.top_right.y, p.bottom_left.y, p.bottom_right.y]
        seen = fitz.Rect(min(xs) / zoom, min(ys) / zoom, max(xs) / zoom, max(ys) / zoom)
        fmt = res.format.name if hasattr(res.format, "name") else str(res.format)
        box = _snap(seen, fmt in _TWO_D, drawings, images, lines) & page.rect
        if any(fitz.Rect(f["_rect"]).intersects(box) and (fitz.Rect(f["_rect"]) & box).get_area() > 0.5 * box.get_area()
               for f in found):
            continue  # อ่านซ้ำตัวเดิม (เช่น หมุนแล้วอ่านได้อีกรอบ)
        found.append({
            "id": f"bc-{round(box.x0)}-{round(box.y0)}",
            "bbox": {"x0": round(box.x0, 2), "y0": round(box.y0, 2), "x1": round(box.x1, 2), "y1": round(box.y1, 2)},
            "format": fmt,
            "text": res.text[:200],
            "_rect": box,
        })
    found.sort(key=lambda f: (f["_rect"].y0, f["_rect"].x0))
    for f in found:
        del f["_rect"]
    return found


def get_barcodes(session: PDFSession, page_number: int) -> dict:
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    page = doc[page_number]
    return {"barcodes": find_barcodes(page), "rotated": bool(page.rotation)}


def _match(found: list[dict], bbox: dict) -> fitz.Rect:
    want = fitz.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
    for f in found:
        r = fitz.Rect(f["bbox"]["x0"], f["bbox"]["y0"], f["bbox"]["x1"], f["bbox"]["y1"])
        if all(abs(a - b) <= _MATCH_PT for a, b in zip(r, want)):
            return r
    raise PDFError("ไม่พบบาร์โค้ดนี้ในหน้าแล้ว — โหลดหน้าใหม่แล้วเลือกอีกครั้ง")


def _copy_area(doc: fitz.Document, page_number: int, area: fitz.Rect) -> fitz.Document:
    """สำเนาหน้าเดียวที่เหลือแค่ของในกรอบ ``area`` (ข้อความทั้งหน้าไม่ติดไปใน XObject ของที่วางใหม่)"""
    src = fitz.open()
    src.insert_pdf(doc, from_page=page_number, to_page=page_number, annots=False)
    sp = src[0]
    sp.clean_contents()
    _drop_degenerate_rects(src, sp)
    w, h = sp.rect.width, sp.rect.height
    out = area + (-0.5, -0.5, 0.5, 0.5)
    for rr in (fitz.Rect(0, 0, w, out.y0), fitz.Rect(0, out.y1, w, h),
               fitz.Rect(0, out.y0, out.x0, out.y1), fitz.Rect(out.x1, out.y0, w, out.y1)):
        if rr.width > 0 and rr.height > 0:
            sp.add_redact_annot(rr)
    # COVERED: เก็บรูปทรงที่ยื่นเข้ามาในกรอบไว้ (show_pdf_page ตัดตามกรอบอยู่แล้ว) — แท่งบาร์โค้ดไม่ถูกลบเพราะแตะขอบ
    sp.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)
    return src


def _erase_area(page: fitz.Page, area: fitz.Rect) -> None:
    """ลบของเดิมในกรอบ — รูปทรงที่พาดผ่านกรอบ (เส้นตาราง/กรอบหน้า) วาดคืนตามเดิม"""
    crossing = []
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"]).normalize()
        if _span(r, area) and not _within(r, area):
            crossing.append(d)
    page.add_redact_annot(area, fill=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    _redraw(page, crossing)


def edit_barcode(session: PDFSession, page_number: int, bbox: dict, target: dict | None) -> dict:
    """``target`` = กรอบใหม่ (ย้าย/ย่อขยาย) หรือ ``None`` = ลบ · คืน ``{"bbox": กรอบใหม่ | None}``"""
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    page = doc[page_number]
    if page.rotation:
        raise _rotated_error()
    area = _match(find_barcodes(page), bbox)

    new = None
    src = None
    if target is not None:
        new = fitz.Rect(target["x0"], target["y0"], target["x1"], target["y1"]).normalize()
        if new.width < MIN_SIZE_PT or new.height < MIN_SIZE_PT:
            raise PDFError("บาร์โค้ดเล็กเกินไป")
        if not page.rect.contains(new):
            raise PDFError("บาร์โค้ดเกินขอบกระดาษ — ย้ายให้อยู่ในหน้าก่อน")
        src = _copy_area(doc, page_number, area)
    try:
        _erase_area(page, area)
        if new is not None and src is not None:
            page.show_pdf_page(new, src, 0, clip=area, keep_proportion=False)
    finally:
        if src is not None:
            src.close()
    _drop_registry_overlaps(session, page_number, area)
    session.mark_dirty()
    return {"bbox": None if new is None else {"x0": new.x0, "y0": new.y0, "x1": new.x1, "y1": new.y1}}


def _drop_registry_overlaps(session: PDFSession, page_number: int, area: fitz.Rect) -> None:
    """ข้อความที่เคยแก้ (ทะเบียน text_edits) ที่อยู่ในกรอบที่ลบไปแล้ว — ไม่มีของให้แก้อีก"""
    page_edits = session.text_edits.get(page_number) or {}
    stale = [e for e, rec in page_edits.items() if rec.get("kind") != "table" and rec.get("rect")
             and _within(fitz.Rect(*[rec["rect"][k] for k in ("x0", "y0", "x1", "y1")]), area + (-1, -1, 1, 1))]
    for edit_id in stale:
        page_edits.pop(edit_id, None)
