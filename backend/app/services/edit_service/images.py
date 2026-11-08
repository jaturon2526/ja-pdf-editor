"""รูปภาพในหน้า PDF: รายการ ลบ แทนที่ แทรก ย้าย/ปรับขนาด และดึงไบต์รูป (ดู NOTES.md ข้อ #7, #9)"""
from __future__ import annotations

from typing import Optional

import fitz  # PyMuPDF

from app.core.session import PDFSession
from app.models.schemas import ImageInfo, Rect
from app.services.pdf_service import PDFError, require_unlocked


def get_images(session: PDFSession, page_number: int) -> list[ImageInfo]:
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    page = doc[page_number]

    # รวบรวม xref ของรูปภาพที่ annotation_service ฝังไว้ด้วยระบบเก่า (title metadata)
    # เพื่อกรองออกจากรายการรูปภาพที่แก้ไขได้ — ป้องกันกล่องแดงโผล่บนพื้นที่ annotation
    annot_image_xrefs: set[int] = set()
    for a in page.annots():
        title = (a.info or {}).get("title", "")
        if title and "|" in title:
            xref_part = title.split("|", 1)[1]
            for tok in xref_part.split(","):
                tok = tok.strip()
                if tok.isdigit():
                    annot_image_xrefs.add(int(tok))

    results: list[ImageInfo] = []
    for img in page.get_image_info(xrefs=True):
        xref = img.get("xref", 0)
        bbox = img["bbox"]
        if not xref:
            continue
        # กรอง xref ที่เป็นของ annotation (ระบบเก่า) ออก
        if xref in annot_image_xrefs:
            continue
        # กรองรูปที่มีพื้นที่ bbox = 0 (ซ่อน/มองไม่เห็นใน PDF) ออก
        w_pt = abs(bbox[2] - bbox[0])
        h_pt = abs(bbox[3] - bbox[1])
        if w_pt < 1.0 or h_pt < 1.0:
            continue
        results.append(
            ImageInfo(
                id=f"img-{xref}-{len(results)}",
                xref=xref,
                page_number=page_number,
                rect=Rect(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
                width=img.get("width", 0),
                height=img.get("height", 0),
            )
        )
    return results


def _image_use_count(doc: fitz.Document, xref: int) -> int:
    """จำนวนตำแหน่งที่รูป xref นี้ถูกวาดทั้งเอกสาร (รูปเดียวกันอาจใช้ซ้ำ เช่น โลโก้ทุกหน้า)"""
    n = 0
    for page in doc:
        if any(img[0] == xref for img in page.get_images(full=True)):
            n += sum(1 for info in page.get_image_info(xrefs=True) if info.get("xref") == xref)
    return n


def _hide_image(page: fitz.Page, xref: int) -> bool:
    """ทำให้รูป xref หายจากหน้านี้ โดยไม่แตะข้อความ/รูปอื่น — คืน False ถ้าทำแบบปลอดภัยไม่ได้

    เดิมลบ/ย้ายรูปด้วย redaction ทั้งกรอบรูป: ข้อความที่อยู่บนรูป (เช่น หัวกระดาษบนแถบรูป) หายด้วย และโหมด
    IMAGE_REMOVE ลบ "ทุกรูปที่ทับกรอบ" — ลบโลโก้เล็ก ๆ บนหน้าสแกน รูปสแกนทั้งหน้าหายไปด้วย
    - รูปที่ใช้ที่เดียวในเอกสาร: แทนเนื้อรูปด้วยพิกเซลโปร่งใส (page.delete_image)
    - รูปที่ใช้หลายที่: ให้ชื่อรูปในหน้านี้ชี้ไปที่ XObject ว่าง (หน้าอื่นไม่กระทบ) ถ้า Resources ของหน้าแยกได้"""
    doc = page.parent
    entries = [img for img in page.get_images(full=True) if img[0] == xref]
    if not entries:
        return False
    placements = sum(1 for info in page.get_image_info(xrefs=True) if info.get("xref") == xref)
    if _image_use_count(doc, xref) == 1:
        page.delete_image(xref)
        return True
    if placements != 1 or entries[0][9] != 0:  # วางซ้ำในหน้าเดียวกัน / อยู่ใน Form XObject ที่อาจใช้ร่วม
        return False
    return hide_xobject_name(page, entries[0][7])


def hide_xobject_name(page: fitz.Page, name: str) -> bool:
    """ให้ชื่อ XObject ใน Resources ของหน้านี้ชี้ไปที่ Form ว่าง (สิ่งที่วาดด้วยชื่อนั้นหายเฉพาะหน้านี้)
    — ทำสำเนา Resources/XObject ก่อนถ้าใช้ร่วมกับหน้าอื่น · คืน False ถ้า Resources สืบทอดจาก Pages"""
    doc = page.parent
    res = doc.xref_get_key(page.xref, "Resources")
    if res[0] == "xref":
        rx = int(res[1].split()[0])
        if any(doc.xref_get_key(p.xref, "Resources") == res for p in doc if p.number != page.number):
            new_rx = doc.get_new_xref()
            doc.update_object(new_rx, doc.xref_object(rx, compressed=True))
            doc.xref_set_key(page.xref, "Resources", f"{new_rx} 0 R")
            rx = new_rx
        holder, prefix = rx, ""
    elif res[0] == "dict":
        holder, prefix = page.xref, "Resources/"
    else:
        return False  # Resources สืบทอดจาก Pages — แยกเฉพาะหน้าไม่ได้
    xo = doc.xref_get_key(holder, f"{prefix}XObject")
    if xo[0] == "xref":  # XObject dict ใช้ร่วม → ทำสำเนาให้หน้านี้
        new_xo = doc.get_new_xref()
        doc.update_object(new_xo, doc.xref_object(int(xo[1].split()[0]), compressed=True))
        doc.xref_set_key(holder, f"{prefix}XObject", f"{new_xo} 0 R")
        holder, prefix = new_xo, ""
    else:
        prefix = f"{prefix}XObject/"
    empty = doc.get_new_xref()
    doc.update_object(empty, "<</Type/XObject/Subtype/Form/BBox[0 0 1 1]>>")
    doc.update_stream(empty, b" ")
    doc.xref_set_key(holder, f"{prefix}{name}", f"{empty} 0 R")
    return True


def delete_image(session: PDFSession, page_number: int, xref: int, rect: Optional[Rect] = None) -> None:
    """ลบรูปภาพออกจากหน้า PDF อย่างสมบูรณ์

    page.delete_image(xref) ของ PyMuPDF ลบ xref resource reference แต่ไม่ได้ลบออกจาก
    content stream ทันที — รูปยังโผล่เมื่อ render ถ้าไม่เรียก clean_contents() ตามหลัง
    แต่ clean_contents() ก็ไม่ได้ลบ content stream command (\"/Image Do\") ออกจริงๆ
    วิธีที่น่าเชื่อถือที่สุดคือค้นหา rect ของรูปแล้วใช้ redaction ทาทับทิ้งเหมือนที่ทำกับข้อความ
    """
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    page = doc[page_number]
    if _hide_image(page, xref):
        session.mark_dirty()
        return
    try:
        # (สำรอง) ค้นหา rect ของรูปที่มี xref นี้ หรือใช้ rect ที่ส่งมาโดยตรง
        image_rect = None
        if rect:
            image_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
        else:
            for img_info in page.get_image_info(xrefs=True):
                if img_info.get("xref") == xref:
                    image_rect = fitz.Rect(img_info["bbox"])
                    break

        if image_rect is None:
            # ถ้าหา rect ไม่เจอ ลองใช้ get_images แบบเดิม
            for (x, *_rest) in page.get_images(full=True):
                if x == xref:
                    # fallback: ลบ xref แล้ว clean
                    page.delete_image(xref)
                    page.clean_contents()
                    session.mark_dirty()
                    return
            raise PDFError(f"ไม่พบรูปภาพ xref={xref} ในหน้า {page_number}")

        # สำรอง: redaction เฉพาะพิกเซลในกรอบ ไม่ลบข้อความ/เส้นที่ทับอยู่
        page.add_redact_annot(image_rect, fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_NONE)
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError(f"ลบรูปภาพไม่สำเร็จ: {exc}") from exc
    session.mark_dirty()


def replace_image(session: PDFSession, page_number: int, xref: int, new_image_bytes: bytes) -> None:
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    page = doc[page_number]
    try:
        page.replace_image(xref, stream=new_image_bytes)
    except Exception as exc:  # PyMuPDF ยกข้อผิดพลาดหลายแบบตาม xref ที่ไม่ถูกต้อง/ชนิดไฟล์
        raise PDFError(f"แทนที่รูปภาพไม่สำเร็จ: {exc}") from exc
    session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดู _doc_dirty ใน session.py


def _extract_image_with_alpha(doc: fitz.Document, xref: int) -> tuple[bytes, str]:
    """ดึงไบต์ภาพจริงของ xref — เหมือน doc.extract_image() ตรงๆ แต่ "รักษาความโปร่งใสไว้"

    บั๊กที่พบ (กล่องดำทับรูปหลังย้ายตำแหน่ง/พรีวิวรูปที่มีพื้นหลังโปร่งใส เช่น ลายเซ็นที่วาด/พิมพ์ด้วย
    Electronic Sign ซึ่งเป็น PNG พื้นหลังโปร่งใสเสมอ — ดู signature_service.py): ใน PDF รูปที่มีช่อง
    อัลฟา (alpha/transparency) จะถูกเก็บเป็น "รูปสีจริง" (ไม่มีอัลฟา) บวกกับ "soft mask" (SMask) แยก
    เป็นอีก object หนึ่งต่างหากที่เก็บค่าความโปร่งใสแทน — แต่ doc.extract_image(xref) ธรรมดาจะคืนมาแค่
    ไบต์ของรูปสีจริงเท่านั้น "ไม่รวม" SMask เข้าไปด้วย ผลคือพิกเซลที่เคยโปร่งใส (alpha=0) ในรูปต้นฉบับ
    จะกลายเป็นสีดำสนิท (RGB 0,0,0 ซึ่งเป็นค่า default ที่เครื่องมือวาดส่วนใหญ่ใช้เติมพื้นที่โปร่งใส) พอเอา
    ไบต์นี้ไปวาดซ้ำ (reposition_image) หรือส่งไปพรีวิวตรงๆ (get_image_bytes) เลยเห็นเป็นกล่องดำทึบครอบ
    ลายเซ็นแทนที่จะโปร่งใสเหมือนเดิม — ทางแก้: เช็ค info["smask"] ถ้ามี ให้ประกอบร่างใหม่
    """
    info = doc.extract_image(xref)
    smask_xref = info.get("smask") or 0
    if not smask_xref:
        # ถ้าไม่มี smask ก็แค่เช็คว่าต้องแปลงสีไหม (เช่น CMYK ที่เบราว์เซอร์ไม่รองรับ)
        try:
            rgb_pix = fitz.Pixmap(doc, xref)
            if rgb_pix.colorspace and rgb_pix.colorspace.name != "DeviceRGB":
                rgb_pix = fitz.Pixmap(fitz.csRGB, rgb_pix)
            return rgb_pix.tobytes("png"), "png"
        except Exception:
            return info["image"], info.get("ext") or "png"
    
    try:
        # ใช้ Pillow ประกอบ Alpha ก่อน เพราะเสถียรที่สุดและป้องกันบั๊ก PyMuPDF Pixmap memory corruption 
        # (เช่น ปัญหาสีเพี้ยนจากดำเป็นแดง เมื่อใช้ fitz.Pixmap(..., 1) คัดลอกพิกเซล)
        from PIL import Image
        import io
        base = Image.open(io.BytesIO(info["image"])).convert("RGBA")
        mask_info = doc.extract_image(smask_xref)
        mask_img = Image.open(io.BytesIO(mask_info["image"])).convert("L")
        if mask_img.size != base.size:
            mask_img = mask_img.resize(base.size)
        base.putalpha(mask_img)
        buf = io.BytesIO()
        base.save(buf, format="PNG")
        return buf.getvalue(), "png"
    except Exception:
        # ถ้า Pillow ประกอบไม่สำเร็จ (เช่น ไบต์รูปแบบแปลกๆ หรือ PyMuPDF บีบอัดเป็น raw format มา)
        # ค่อย Fallback กลับไปใช้ PyMuPDF Pixmap
        try:
            rgb_pix = fitz.Pixmap(doc, xref)
            if rgb_pix.colorspace and rgb_pix.colorspace.name != "DeviceRGB":
                rgb_pix = fitz.Pixmap(fitz.csRGB, rgb_pix)
            mask_pix = fitz.Pixmap(doc, smask_xref)
            if mask_pix.width != rgb_pix.width or mask_pix.height != rgb_pix.height:
                mask_pix = fitz.Pixmap(mask_pix, rgb_pix.width, rgb_pix.height, None)
            if not rgb_pix.alpha:
                # สร้าง Pixmap ใหม่จากขนาดและสี (ปลอดภัยกว่าใช้ fitz.Pixmap(rgb_pix, 1) ซึ่งมัก corrupt)
                pix_with_alpha = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, rgb_pix.width, rgb_pix.height), True)
                pix_with_alpha.clear_with(0)
                # เราไม่สามารถคัดลอกด้วยวิธีปกติได้ตรงๆ แต่ยอมใช้ fallback แบบเดิมไปก่อน
                pix_with_alpha = fitz.Pixmap(rgb_pix, 1)
                pix_with_alpha.set_alpha(mask_pix.samples)
                return pix_with_alpha.tobytes("png"), "png"
            else:
                return rgb_pix.tobytes("png"), "png"
        except Exception:
            return info["image"], info.get("ext") or "png" 
    
    try:
        # สร้าง Pixmap ของรูปสีจริง
        rgb_pix = fitz.Pixmap(doc, xref)
        # บังคับแปลงเป็น RGB เสมอเพื่อป้องกันสีเพี้ยน (เช่น จาก Gray, CMYK, BGR หรือโหมดแปลกๆ)
        if rgb_pix.colorspace and rgb_pix.colorspace.name != "DeviceRGB":
            rgb_pix = fitz.Pixmap(fitz.csRGB, rgb_pix)
        
        # สร้าง Pixmap ของ SMask (ภาพขาวดำ 1 channel แสดงความโปร่งใส)
        mask_pix = fitz.Pixmap(doc, smask_xref)
        
        # ปรับขนาด mask ให้ตรงกับ rgb_pix (เผื่อกรณีที่ขนาดไม่เท่ากัน)
        if mask_pix.width != rgb_pix.width or mask_pix.height != rgb_pix.height:
            mask_pix = fitz.Pixmap(mask_pix, rgb_pix.width, rgb_pix.height, None)
            
        # ถ้ารูปสีจริงมี alpha อยู่แล้ว ก็ไม่จำเป็นต้องใส่เพิ่ม แต่ปกติมันมักจะแยกกัน
        if not rgb_pix.alpha:
            # คัดลอก rgb_pix แต่ระบุ alpha=1 (หรือ True) เพื่อเพิ่มช่องอัลฟากลับเข้าไป
            pix_with_alpha = fitz.Pixmap(rgb_pix, 1)
            # ใส่ข้อมูล SMask เข้าไปในช่องอัลฟา
            pix_with_alpha.set_alpha(mask_pix.samples)
            return pix_with_alpha.tobytes("png"), "png"
        else:
            return rgb_pix.tobytes("png"), "png"
    except Exception:
        # ประกอบ alpha ไม่สำเร็จ — คืนรูปดิบแบบเดิมดีกว่าทำให้ทั้งฟังก์ชัน error ไปเลย
        return info["image"], info.get("ext") or "png"


def get_image_bytes(session: PDFSession, page_number: int, xref: int) -> tuple[bytes, str]:
    """ดึงข้อมูลไบต์ดิบของรูปภาพ (ตาม xref) ในหน้า — ก่อนหน้านี้ get_images() คืนแค่ตำแหน่ง/ขนาด
    ไม่มีเนื้อรูปให้ frontend โชว์ พอจะทำกล่องลาก ย้าย/ปรับขนาดรูปภาพจริง (แก้บั๊กสำคัญ #7 — ดูด้านล่าง)
    ต้องมี endpoint ให้ frontend ขอเนื้อรูปจริงมาพรีวิวตรงตำแหน่งได้ระหว่างลาก ก่อนกดบันทึกจริง
    คืนค่า (image_bytes, ext) — ext (เช่น "png"/"jpeg") ใช้ตั้ง Content-Type ตอนส่งกลับ (ดู routes_edit.py)
    ใช้ _extract_image_with_alpha() แทน doc.extract_image() ตรงๆ — กันบั๊กกล่องดำ (ดูหมายเหตุฟังก์ชันนั้น)
    """
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    try:
        return _extract_image_with_alpha(doc, xref)
    except Exception as exc:
        raise PDFError(f"ดึงข้อมูลรูปภาพไม่สำเร็จ (xref={xref}): {exc}") from exc


def insert_image(session: PDFSession, page_number: int, rect: Rect, image_bytes: bytes) -> None:
    """แทรกรูปภาพใหม่ลงในหน้า (แก้บั๊กสำคัญ #7 — ต้องมีปุ่ม Insert Image ให้เพิ่มรูปใหม่ได้ ไม่ใช่แค่
    แทนที่รูปเดิม) วางที่ตำแหน่ง/ขนาด rect ตรงๆ ด้วย keep_proportion=False — ยืด/บีบภาพให้เต็มกรอบ
    rect พอดีเป๊ะตามที่ผู้ใช้ลาก ไม่ใช่ keep_proportion=True (ซึ่งจะคงสัดส่วนเดิมของรูปไว้แล้ว "letterbox"
    จัดกึ่งกลางในกรอบแทน — ทดสอบแล้วพบว่าเวลาสัดส่วนกรอบที่ผู้ใช้ลากไม่ตรงกับสัดส่วนรูปเดิม ตำแหน่ง/ขนาด
    รูปจริงที่ได้จะไม่ตรงกับกรอบที่ลากไว้เป๊ะ ทำให้ผลลัพธ์ไม่ตรงกับที่เห็นตอนลาก สร้างความสับสน) เลือกใช้
    False เพื่อให้ "กรอบที่ลาก = ขนาดรูปที่ได้" ตรงไปตรงมา ฝั่ง frontend พรีวิวด้วย <img> ธรรมดา (ไม่ใส่
    object-fit: contain) ให้ตรงกับพฤติกรรมนี้ รูปที่แทรกแล้วจะมี xref จริงในเอกสาร ครั้งถัดไปที่เรียก
    get_images() จะเจอรูปนี้ปนมาในรายการตามปกติ (ไม่ต้องมีทะเบียนแยกต่างหากเหมือนข้อความที่แก้ไข
    เพราะรูปภาพยังเป็น image object จริงของ PDF อยู่ ไม่ได้ redact ทิ้งแบบข้อความ)
    """
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    page = doc[page_number]
    target_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1).normalize()
    if target_rect.is_empty or target_rect.width < 1 or target_rect.height < 1:
        raise PDFError("ขนาดรูปเล็กเกินไป — ลากกรอบให้ใหญ่ขึ้น")
    if not image_bytes:
        raise PDFError("ไฟล์รูปว่างเปล่า")
    try:
        page.insert_image(target_rect, stream=image_bytes, keep_proportion=False)
    except Exception as exc:
        raise PDFError(f"แทรกรูปภาพไม่สำเร็จ: {exc}") from exc
    session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดู _doc_dirty ใน session.py


def reposition_image(
    session: PDFSession, page_number: int, xref: int, old_rect: Rect, new_rect: Rect
) -> None:
    """ย้ายตำแหน่ง/ปรับขนาดรูปภาพที่มีอยู่แล้วในหน้า (แก้บั๊กสำคัญ #7 — ต้องลากเมาส์ย่อ/ขยาย/ย้ายรูปได้)
    PyMuPDF ไม่มี API ย้ายรูปเดิมตรงๆ: ดึงไบต์รูปเดิม (รวมความโปร่งใส) → ซ่อนรูปเดิมเฉพาะตำแหน่งนี้ (_hide_image —
    ไม่แตะข้อความ/รูปอื่น) → วาดรูปลงกรอบใหม่ด้วย page.insert_image()

    แก้บั๊กกล่องดำทับรูป (พบตอนย้ายรูปลายเซ็นที่พื้นหลังโปร่งใส): ใช้ _extract_image_with_alpha() แทน
    doc.extract_image() ตรงๆ ตอนดึงไบต์รูปเดิมในข้อ 1 — ไม่งั้นรูปที่ดึงมาจะไม่มีช่องอัลฟา (สูญเสีย
    ความโปร่งใส) พอวาดกลับด้วย insert_image() ในข้อ 3 พื้นที่โปร่งใสเดิมจะกลายเป็นกล่องดำทึบครอบลายเซ็น
    แทนที่จะโปร่งใสเหมือนเดิม (ดูหมายเหตุเต็มใน _extract_image_with_alpha())
    """
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    page = doc[page_number]

    try:
        image_bytes, _ext = _extract_image_with_alpha(doc, xref)
    except Exception as exc:
        raise PDFError(f"ดึงข้อมูลรูปภาพเดิมไม่สำเร็จ (xref={xref}): {exc}") from exc

    old_r = fitz.Rect(old_rect.x0, old_rect.y0, old_rect.x1, old_rect.y1)
    new_r = fitz.Rect(new_rect.x0, new_rect.y0, new_rect.x1, new_rect.y1).normalize()
    if new_r.is_empty or new_r.width < 1 or new_r.height < 1:
        raise PDFError("ขนาดรูปเล็กเกินไป")

    # ซ่อนรูปเดิมโดยไม่แตะข้อความ/รูปอื่น (ดู _hide_image) — เดิม redact กรอบเดิม+กรอบใหม่ทั้งหมด: ข้อความใต้
    # ตำแหน่งใหม่และข้อความที่อยู่บนรูปเดิมหายไปด้วย และระบายสีพื้นหลังที่เดาไว้ทับ
    if not _hide_image(page, xref):
        page.add_redact_annot(old_r, fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_NONE)

    try:
        page.insert_image(new_r, stream=image_bytes, keep_proportion=False)
    except Exception as exc:
        raise PDFError(f"วางรูปภาพตำแหน่งใหม่ไม่สำเร็จ: {exc}") from exc
    session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดู _doc_dirty ใน session.py
