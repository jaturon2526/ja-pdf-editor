"""
signature_service — เมนู "Digital Signature" (ผู้ใช้แจ้งขอ): Electronic Sign และ Digital Sign

## Electronic Sign
เป็นการ "แปะ" เครื่องหมายลายเซ็น (ข้อความที่พิมพ์/รูปภาพที่อัปโหลด/ลายมือที่วาดเอง — ทั้งสามแบบ frontend
เรนเดอร์เป็นรูป PNG ให้เสร็จก่อนส่งมา) ลงในหน้าเอกสารตรงตำแหน่ง/ขนาดที่ผู้ใช้ลากเลือก ใช้กลไกเดียวกับ
"แทรกรูปภาพ" ทุกประการ — เรียก edit_service.insert_image() ตรงๆ (ไม่ใช่ page.insert_image() เอง)
ไม่มีการเข้ารหัส/ยืนยันตัวตนใดๆ ทางเทคนิค (ตรงตามความหมายของ "electronic signature" ทั่วไปที่แค่เป็น
เครื่องหมายแสดงเจตนา ไม่ใช่ลายเซ็นดิจิทัลแบบเข้ารหัส)

(ผู้ใช้แจ้งแก้ไขรอบนี้: กด "ตกลง" แล้วไม่ต้องล็อกเอกสาร และต้องยังคลิกกลับมาย้าย/ปรับขนาดตำแหน่งลายเซ็น
ได้) เดิมฟังก์ชันนี้เรียก page.insert_image() เองตรงๆ แล้วตั้ง session.is_signed=True ไปล็อกทุก service
ที่แก้ไขเอกสาร ตอนนี้เปลี่ยนมาเรียก edit_service.insert_image() แทน (กลไกข้างในเหมือนเดิมทุกประการ —
page.insert_image(..., keep_proportion=False)) เพราะรูปที่แทรกด้วยฟังก์ชันนั้นจะมี xref จริงในเอกสาร
ที่ edit_service.get_images()/หน้าจอ "Tools > แก้ไขรูปภาพ" มองเห็นและคลิกย้าย/ปรับขนาดต่อได้ทันทีโดย
ไม่ต้องเขียนกลไก tracking ใหม่เพิ่ม — ได้ requirement "แก้ไข/เปลี่ยนตำแหน่งได้" มาฟรีจากฟีเจอร์ที่มีอยู่แล้ว

## Digital Sign
เป็นลายเซ็นดิจิทัลแบบเข้ารหัสจริง (PAdES — PDF Advanced Electronic Signatures) โดยใช้ private key จาก
ไฟล์ .p12/.pfx ที่ผู้ใช้อัปโหลด (มาตรฐานเดียวกับที่ Adobe Acrobat ใช้ตรวจสอบได้) ผ่านไลบรารี pyHanko:
  1. โหลด private key + certificate จากไฟล์ p12/pfx ด้วยรหัสผ่านที่ผู้ใช้กรอก (SimpleSigner.load_pkcs12_data
     รับ bytes ตรงๆ ไม่ต้องเขียนไฟล์ชั่วคราวลงดิสก์ — ปลอดภัยกว่า)
  2. เพิ่ม signature field ที่ตำแหน่ง/ขนาดที่ผู้ใช้ลากเลือก (พิกัดใน PDF จริงนับจากมุมล่างซ้าย ต่างจาก
     Rect ที่ frontend/ส่วนอื่นของแอปนี้ใช้กัน ซึ่งนับจากมุมบนซ้ายเหมือนหน้าจอ — ต้องแปลงกลับด้วย
     page_height - y เสมอ ดู _to_pdf_box ด้านล่าง)
  3. เซ็นจริงด้วย pyhanko.sign.signers.PdfSigner — ได้ไบต์ไฟล์ PDF ใหม่ที่มีลายเซ็นฝังอยู่จริง

**เรื่องฟอนต์ภาษาไทยในลายเซ็น (สำคัญ — เจอปัญหาเดียวกับที่ edit_service.py เคยเจอมาก่อน)**: เอนจิน
เรนเดอร์ตัวอักษรของ pyHanko เอง (ใช้กับ TextStampStyle ปกติ) รองรับแค่ WinAnsiEncoding (ละตินล้วน) —
ทดสอบแล้วพบว่าข้อความไทยที่ส่งผ่าน stamp_text ออกมาเป็นตัวอักษรมั่ว (mojibake) ทันที ทางแก้: เรนเดอร์ข้อความไทย
เป็นรูปภาพเองก่อนด้วย Pillow+RAQM (ฟอนต์ Sarabun — แบบเดียวกับที่ edit_service รุ่นแรกเคยใช้ ปัจจุบันที่นี่
เป็นที่เดียวที่ยังใช้ RAQM; main.py เตือนใน log ตอน start ถ้า Pillow ไม่มี RAQM)
แล้วฝังรูปนั้นเป็น background ของ StaticStampStyle แทนการพึ่งเอนจินข้อความของ pyHanko เอง — ทดสอบแล้วว่า
เรนเดอร์ไทยถูกต้อง และลายเซ็นยังคง valid ตามปกติ (ดู pyhanko.sign.validation.validate_pdf_signature)

**เรื่องการรักษาไบต์ลายเซ็นให้ไม่เสียหาย + รองรับเซ็นซ้อนหลายคน (แก้ไขรอบนี้ — ผู้ใช้แจ้งว่า Digital
Sign ก็ไม่ต้องล็อกไฟล์เหมือนกัน เพราะอาจมีคนอื่นมาเซ็นต่อเป็นลำดับถัดไป)**: ลายเซ็นดิจิทัลคำนวณ hash
ครอบคลุมไบต์ของไฟล์ ณ ตอนเซ็นแบบเป๊ะๆ ถ้าเอกสารถูก "เขียนทับใหม่ทั้งหมด" อีกครั้งหลังจากนี้ (เช่น
fitz.Document.tobytes() ซึ่งทำ garbage-collection/rewrite โครงสร้างไฟล์ใหม่) ลายเซ็นจะ invalid ทันที
แม้เนื้อหาจะไม่มีอะไรเปลี่ยนเลยก็ตาม — แต่ทดสอบยืนยันแล้ว (ดู /tmp/experiment_multisign.py ตอนพัฒนา)
ว่าถ้าเอกสารถูกแก้ไขต่อแบบ "incremental" ล้วนๆ (doc.saveIncr() ของ fitz, หรือเซ็นซ้อนด้วย pyHanko อีกที)
ลายเซ็นเดิมจะยังคง valid อยู่เสมอ แม้จะมีการแก้ไขเนื้อหา (เช่น เพิ่ม annotation) คั่นกลางระหว่างสองลายเซ็น
ก็ตาม ทางแก้ที่ใช้ในแอปนี้ตอนนี้:
  1. session.doc ต้องเปิดจาก "ไฟล์จริงบนดิสก์" เสมอทุกจุด (ไม่ใช่ fitz.open(stream=...)) — ดูหมายเหตุ
     ยาวใน app/core/session.py — เพื่อให้ doc.saveIncr() ใช้งานได้ต่อไปเรื่อยๆ ไม่ว่าจะแก้ไข/เซ็นกี่รอบ
  2. ก่อนเซ็น: เรียก doc.saveIncr() (ไม่ใช่ doc.tobytes()) แล้วอ่านไบต์จากไฟล์จริงกลับมาให้ pyHanko ใช้
     เป็นฐาน — รักษา byte-range ของลายเซ็นที่อาจฝังอยู่ก่อนหน้านี้แล้วให้ยัง valid
  3. field_name ของแต่ละลายเซ็นต้องไม่ซ้ำกัน (ใช้ uuid ต่อท้าย) กันชนกันถ้ามีคนที่สองมาเซ็นต่อ
  4. เซ็นเสร็จแล้วเขียนไบต์ที่ pyHanko คืนมาทับ working_path บนดิสก์ตรงๆ แล้วเปิด session.doc ใหม่จาก
     ไฟล์จริงนั้น (ไม่ใช่จาก stream) เพื่อให้แก้ไขต่อ/เซ็นซ้อนต่อ/ดาวน์โหลดได้ตามปกติไม่ล็อกอีกต่อไป
  5. session.signed_pdf_bytes ยังเก็บไว้เป็น "flag ว่ามีลายเซ็นดิจิทัลฝังอยู่ในสาขา undo ปัจจุบัน" ให้
     pdf_service.add_password()/reorder_pages() เช็คก่อนบล็อก (ทั้งสองปฏิบัติการต้อง rebuild เอกสารใหม่
     ทั้งหมด ไม่ใช่ incremental จะทำให้ลายเซ็นเสียหาย — ดูหมายเหตุในไฟล์นั้น) แต่ไม่ใช่ทางลัด bypass
     การดาวน์โหลดอีกต่อไป (ดู pdf_service.get_download_path)
"""
from __future__ import annotations

import io
import logging
import uuid
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

from app.core.session import PDFSession
from app.models.schemas import Rect
from app.services import edit_service, fonts
from app.services.pdf_service import PDFError, require_unlocked
from app.services.pdf_service.core import has_digital_signatures

logger = logging.getLogger("signature_service")

# เรนเดอร์ preview/appearance ที่ความละเอียดสูงกว่าขนาดจริง (pt) กี่เท่า — คมชัดกว่าเวลาซูมดูใน PDF
# reader จริง (เช่น Acrobat ที่มักซูมดูลายเซ็นใกล้ๆ ก่อนอนุมัติ)
_STAMP_RENDER_SCALE = 4
_STAMP_MARGIN_PT = 6.0


def _get_stamp_font_path() -> str:
    """path ฟอนต์ที่ใช้เรนเดอร์ข้อความลายเซ็น — เรียกแบบ lazy (ไม่ cache ตอน import module) เผื่อ
    resolve_font_path fallback คืน path ว่างถ้าไฟล์ font หาย (ดูหมายเหตุใน fonts.py) ต้องเช็คซ้ำทุกครั้ง"""
    _, path = fonts.resolve_font_path("sarabun")
    if not path:
        raise PDFError("ไม่พบไฟล์ฟอนต์สำหรับเรนเดอร์ลายเซ็น (Sarabun) กรุณาติดต่อผู้ดูแลระบบ")
    return path


# ---------- Electronic Sign ----------

def apply_electronic_signature(
    session: PDFSession, page_number: int, rect: Rect, image_bytes: bytes
) -> None:
    """แปะรูปลายเซ็น (พิมพ์ข้อความ/อัปโหลดรูป/วาดลายมือ — frontend เรนเดอร์เป็น PNG มาให้แล้ว) ลงหน้า
    ตรงตำแหน่ง/ขนาด rect ที่ผู้ใช้ลากเลือก — เรียก edit_service.insert_image() ตรงๆ (ดูหมายเหตุหัวไฟล์)
    เพื่อให้รูปลายเซ็นที่แปะไปมี xref จริงในเอกสาร คลิกกลับมาย้าย/ปรับขนาดต่อได้ผ่าน "Tools > แก้ไข
    รูปภาพ" ตามปกติ (ผู้ใช้แจ้งขอ: ไม่ต้องล็อกเอกสารหลังกด "ตกลง" อีกต่อไป) ไม่ raise ถ้าเอกสารเคยเซ็น
    ไปแล้วรอบก่อน (แปะลายเซ็นซ้ำ/หลายจุดได้ตามปกติ)"""
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    if rect.x1 <= rect.x0 or rect.y1 <= rect.y0:
        raise PDFError("ตำแหน่ง/ขนาดลายเซ็นไม่ถูกต้อง")

    edit_service.insert_image(session, page_number, rect, image_bytes)

    session.is_signed = True
    # เอกสารที่มีลายเซ็นดิจิทัลอยู่แล้วยังเป็น "digital" (เดิมเปลี่ยนเป็น electronic — สถานะ/ข้อความเตือนผิด)
    if session.signed_pdf_bytes is None:
        session.signature_type = "electronic"
    # หมายเหตุ: "ไม่" เซ็ต signed_pdf_bytes = None ตรงนี้อีกต่อไป (บั๊กเดิม) — signed_pdf_bytes บอกว่า
    # "เอกสารมีลายเซ็นดิจิทัลฝังอยู่ไหม" ซึ่งเป็นคนละเรื่องกับ electronic sign ล้วนๆ ถ้า electronic sign
    # ถูกเรียกหลัง digital sign ไปแล้ว (ลำดับไหนก็ได้ตอนนี้ที่ไม่ล็อกแล้ว) ต้องไม่ไปลบ flag นี้ทิ้ง ไม่งั้น
    # pdf_service.add_password()/reorder_pages() จะเข้าใจผิดว่าไม่มีลายเซ็นดิจิทัลฝังอยู่แล้วปล่อยผ่าน


# ---------- Digital Sign (PAdES จริงด้วย p12/pfx) ----------

def load_signer(pfx_bytes: bytes, password: str):
    """เปิด p12/pfx + ตรวจใบรับรองก่อนเซ็น — คืน (signer, info)

    เดิมเซ็นได้ทุกใบ: ใบรับรองหมดอายุ/ยังไม่ถึงวันเริ่มใช้/ไม่อนุญาตให้ลงนาม เซ็นสำเร็จแต่ Acrobat ขึ้นว่าลายเซ็น
    ไม่ถูกต้อง และรหัสผ่านผิดรู้ตอนกดตกลงในกล่องตำแหน่ง (ต้องเลือกไฟล์/พิมพ์ใหม่ทั้งหมด) — ตอนนี้ตรวจตั้งแต่
    หน้าต่างเลือกใบรับรอง (/signature/check-certificate) และตรวจซ้ำตอนเซ็น · เติม chain ของผู้ออกให้ด้วย"""
    import datetime as dt

    from app.services import signing_pdf

    try:
        signer = signing_pdf.load_pkcs12_signer(pfx_bytes, password)
    except signing_pdf.SigningPdfError:
        raise PDFError("เปิดไฟล์ใบรับรองไม่สำเร็จ — รหัสผ่านไม่ถูกต้อง หรือไม่ใช่ไฟล์ .p12/.pfx ที่มีกุญแจส่วนตัว") from None
    cert = signer.signing_cert
    validity = cert["tbs_certificate"]["validity"]
    not_before, not_after = validity["not_before"].native, validity["not_after"].native
    now = dt.datetime.now(dt.timezone.utc)
    fmt = lambda d: d.astimezone(dt.timezone(dt.timedelta(hours=7))).strftime("%d/%m/%Y")
    if now > not_after:
        raise PDFError(f"ใบรับรองหมดอายุแล้ว (หมดอายุ {fmt(not_after)}) — ลายเซ็นจะไม่ถูกต้อง ใช้ใบรับรองใหม่")
    if now < not_before:
        raise PDFError(f"ใบรับรองยังไม่ถึงวันเริ่มใช้ ({fmt(not_before)})")
    key_usage = cert.key_usage_value.native if cert.key_usage_value else None
    if key_usage is not None and not ({"digital_signature", "non_repudiation"} & set(key_usage)):
        raise PDFError("ใบรับรองนี้ไม่ได้อนุญาตให้ใช้ลงนามเอกสาร (Key Usage) — ใช้ใบรับรองสำหรับลงลายมือชื่อดิจิทัล")
    subject, issuer = cert.subject.native, cert.issuer.native
    days_left = (not_after - now).days
    warnings = []
    if cert.self_signed != "no":
        warnings.append("ใบรับรองที่สร้างเอง (self-signed) — โปรแกรมอ่าน PDF จะแสดงว่ายังไม่ได้รับการรับรองความน่าเชื่อถือ")
    if days_left < 30:
        warnings.append(f"ใบรับรองจะหมดอายุในอีก {days_left} วัน")
    info = {
        "common_name": subject.get("common_name"),
        "organization": subject.get("organization_name"),
        "issuer": issuer.get("common_name"),
        "valid_to": fmt(not_after),
        "warnings": warnings,
    }
    return signer, info


def _render_signature_stamp_image(lines: list[str], box_width_pt: float, box_height_pt: float, image_bytes: Optional[bytes] = None) -> Image.Image:
    """เรนเดอร์ข้อความลายเซ็น (ชื่อผู้เซ็น/เหตุผล/เวลา) เป็นรูปภาพผ่าน Pillow+RAQM ด้วยฟอนต์ Sarabun
    (ดูหมายเหตุเรื่องฟอนต์ไทยที่หัวไฟล์ — เอนจินข้อความของ pyHanko เองแสดงภาษาไทยไม่ได้เลย)"""
    import io
    img_w = max(1, int(box_width_pt * _STAMP_RENDER_SCALE))
    img_h = max(1, int(box_height_pt * _STAMP_RENDER_SCALE))
    
    if image_bytes:
        try:
            user_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            user_img.thumbnail((img_w, img_h), Image.Resampling.LANCZOS)

            # ลบพื้นหลังขาว/ใกล้ขาว (threshold=240) เพื่อให้ลายเซ็นโปร่งใสและไม่บังข้อความใน PDF
            datas = user_img.getdata()
            cleaned = [
                (r, g, b, 0) if (r >= 240 and g >= 240 and b >= 240) else (r, g, b, a)
                for r, g, b, a in datas
            ]
            user_img.putdata(cleaned)

            # วางบนพื้นหลังโปร่งใส (RGBA) แทนพื้นขาว RGB
            out = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 0))
            offset = ((img_w - user_img.width) // 2, (img_h - user_img.height) // 2)
            out.paste(user_img, offset, user_img)
            return out
        except Exception as e:
            import logging
            logging.warning(f"Failed to load signature image: {e}")


    # พื้นหลังโปร่งใส — ตราลายเซ็นไม่บังเนื้อหาเดิมของหน้า (PdfImage แปลงช่อง alpha เป็น SMask ให้)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    margin_px = _STAMP_MARGIN_PT * _STAMP_RENDER_SCALE
    max_text_width = img_w - (margin_px * 2)
    # ระยะขอบบน/ล่าง: ไม่เกิน 12% ของความสูง (กล่องเตี้ยจะได้ไม่เหลือที่ให้ข้อความ) — ข้อความแต่ละบรรทัดอยู่กลางช่องของตัวเอง
    # และขนาดฟอนต์ไม่เกิน 62% ของช่อง เผื่อสระ/วรรณยุกต์บนและสระล่างของภาษาไทย ไม่ให้ชนเส้นกรอบ
    margin_v = min(margin_px, img_h * 0.12)

    n_lines = max(1, len(lines))
    line_height_px = (img_h - 2 * margin_v) / n_lines
    font_px = max(10, int(line_height_px * 0.62))
    font_path = _get_stamp_font_path()

    while font_px > 10:
        font = ImageFont.truetype(font_path, font_px, layout_engine=ImageFont.Layout.RAQM)
        too_wide = False
        for line in lines:
            bbox = font.getbbox(line)
            w = bbox[2] - bbox[0]
            if w > max_text_width:
                too_wide = True
                break
        if not too_wide:
            break
        font_px -= 1

    font = ImageFont.truetype(font_path, font_px, layout_engine=ImageFont.Layout.RAQM)

    for i, line in enumerate(lines):
        y_center = margin_v + (i + 0.5) * line_height_px
        draw.text((margin_px, y_center), line, font=font, fill=(0, 0, 0, 255), anchor="lm")

    border_px = max(1, int(0.5 * _STAMP_RENDER_SCALE)) # บางลงเทียบเท่าประมาณ 0.5 point (2px ในภาพ scale 4x)
    draw.rectangle([border_px//2, border_px//2, img_w - border_px//2, img_h - border_px//2], outline=(0, 0, 0, 255), width=border_px)
    return img


def apply_digital_signature(
    session: PDFSession,
    page_number: int,
    rect: Rect,
    pfx_bytes: bytes,
    password: str,
    reason: Optional[str] = None,
    location: Optional[str] = None,
    contact: Optional[str] = None,
    name: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
) -> str:
    """เซ็นเอกสารด้วยลายเซ็นดิจิทัลจริง (PAdES) จากไฟล์ p12/pfx — คืนชื่อผู้เซ็น (Common Name จาก
    certificate) ให้ frontend แสดงยืนยันความสำเร็จ raise PDFError พร้อมข้อความภาษาไทยที่เข้าใจง่ายถ้า
    รหัสผ่านผิด/ไฟล์เสีย/ไม่ใช่ p12 จริง (ไม่ใช่ traceback ดิบของ pyHanko ซึ่งอ่านยากสำหรับผู้ใช้ทั่วไป)

    ไม่ล็อกเอกสารหลังเซ็นอีกต่อไป (ผู้ใช้แจ้งขอ — อาจมีคนต่อไปเซ็นซ้อนเป็นลำดับถัดไป) เรียกเซ็นซ้อนได้
    เรื่อยๆ ไม่จำกัดจำนวนครั้ง/จำนวนคน แต่ละครั้งได้ signature field ใหม่คนละชื่อ (ดูหมายเหตุหัวไฟล์)"""
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    if rect.x1 <= rect.x0 or rect.y1 <= rect.y0:
        raise PDFError("ตำแหน่ง/ขนาดลายเซ็นไม่ถูกต้อง")
    if session.output_password:
        # ไฟล์ดาวน์โหลดถูกเข้ารหัสใหม่ทั้งไฟล์ → ลายเซ็นที่เพิ่งเซ็นใช้ไม่ได้ทันที (เดิมเซ็นได้ แล้วไฟล์ที่ได้ลายเซ็นเสีย)
        raise PDFError("เอกสารนี้ตั้งรหัสผ่านไว้ — ลบรหัสผ่านก่อน (เมนู ไฟล์ → ลบรหัสผ่าน) แล้วค่อยเซ็นดิจิทัล "
                       "เพราะการเข้ารหัสหลังเซ็นทำให้ลายเซ็นใช้ไม่ได้")

    # import แบบ lazy (โหลดช้ากว่า import ทั่วไปนิดหน่อย แต่กันไม่ให้ startup ทั้งแอปช้าลงถ้ามีปัญหา
    # เกี่ยวกับ pyHanko บนเครื่องที่ไม่เคยใช้ฟีเจอร์นี้เลย)
    from pyhanko import stamp
    from pyhanko.pdf_utils.images import PdfImage
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    signer, _info = load_signer(pfx_bytes, password)

    page = doc[page_number]
    # หน้าที่มี /Rotate (เช่น ไฟล์สแกนแนวนอน) หรือ CropBox ไม่เริ่มที่ 0 — เดิมคำนวณพิกัดจากความสูงหน้าบนจอ
    # ลายเซ็นไปอยู่ผิดที่ และตราลายเซ็นตะแคง · หมุนเนื้อหน้าจริงก่อน (เมื่อยังไม่มีลายเซ็นดิจิทัล) แล้วแปลงพิกัด
    # ด้วย transformation_matrix ของหน้า
    if page.rotation and session.signed_pdf_bytes is None and not has_digital_signatures(doc):
        from app.services.pdf_service.core import normalize_page_rotation

        if normalize_page_rotation(page):
            session.mark_dirty()
            page = doc[page_number]
    fr = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1).normalize() & page.rect
    if fr.is_empty or fr.width < 10 or fr.height < 10:
        raise PDFError("กรอบลายเซ็นเล็กเกินไป หรืออยู่นอกหน้ากระดาษ")
    rect = Rect(x0=fr.x0, y0=fr.y0, x1=fr.x1, y1=fr.y1)
    pr = fr * ~page.transformation_matrix  # พิกัดหน้าจอ (บนซ้าย) → พิกัด PDF (ล่างซ้าย, รวมการหมุน/CropBox)
    pdf_box = (pr.x0, pr.y0, pr.x1, pr.y1)

    signer_cn = _extract_common_name(signer) or "ไม่ทราบชื่อผู้เซ็น"
    stamp_lines = [f"ลงลายมือชื่อดิจิทัลโดย: {signer_cn}"]
    if reason:
        stamp_lines.append(f"เหตุผล: {reason}")
    stamp_lines.append("เวลา: " + _now_str())

    stamp_image = _render_signature_stamp_image(stamp_lines, rect.x1 - rect.x0, rect.y1 - rect.y0, image_bytes)

    try:
        # ใช้ session.flush_to_disk() (ไม่ใช่ doc.tobytes() หรือ doc.saveIncr() ตรงๆ) แล้วอ่านไบต์จาก
        # ไฟล์จริงกลับมาเป็นฐานให้ pyHanko — flush_to_disk() รักษา byte-range ของลายเซ็นดิจิทัลที่อาจ
        # ฝังอยู่ก่อนหน้านี้แล้วให้ยัง valid (ดูหมายเหตุหัวไฟล์เรื่องรองรับเซ็นซ้อนหลายคน) เหมือน
        # doc.saveIncr() ทุกประการ แต่เช็คก่อนว่ามีอะไรค้างจริงไหม (ไม่เรียก saveIncr() พร่ำเพรื่อ) กัน
        # บั๊กจริงของ MuPDF/PyMuPDF ที่พบระหว่างแก้ไขฟีเจอร์นี้: เรียก saveIncr() ติดกัน 2 ครั้งโดยไม่มี
        # การแก้ไขคั่นกลางเลยจะทำให้ไฟล์เสียหายทันที (ดูหมายเหตุ _doc_dirty ใน app/core/session.py)
        session.flush_to_disk()
        current_bytes = session.working_path.read_bytes()

        writer = _incremental_writer(doc, current_bytes, already_signed=session.signed_pdf_bytes is not None
                                     or has_digital_signatures(doc))
        # ชื่อ field ต้องไม่ซ้ำกันข้ามการเซ็นแต่ละครั้ง (uuid ต่อท้าย) กันชนกันถ้ามีคนที่สองมาเซ็นต่อ
        # บนเอกสารเดียวกัน (เดิมใช้ชื่อคงที่ "DigitalSignature1" เสมอ ซึ่งจะชนกันทันทีถ้าเซ็นซ้อน)
        field_name = f"DigitalSignature_{uuid.uuid4().hex[:8]}"
        fields.append_signature_field(
            writer,
            fields.SigFieldSpec(sig_field_name=field_name, on_page=page_number, box=pdf_box),
        )
        stamp_style = stamp.StaticStampStyle(background=PdfImage(stamp_image), background_opacity=1.0, border_width=0)
        meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            reason=reason or None,
            location=location or None,
            contact_info=contact or None,
            name=name or None,
        )
        pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=stamp_style)
        signed_out = pdf_signer.sign_pdf(writer)
        signed_bytes = signed_out.getvalue()
    except PDFError:
        raise
    except Exception as exc:
        logger.exception("apply_digital_signature: เซ็นเอกสารไม่สำเร็จ session=%s", session.session_id)
        raise PDFError(f"เซ็นเอกสารไม่สำเร็จ: {exc}") from exc

    # เขียนไบต์ที่เซ็นแล้วทับ working_path บนดิสก์ตรงๆ แล้วเปิด session.doc ใหม่จาก "ไฟล์จริง" นั้น
    # (ไม่ใช่ fitz.open(stream=...) แบบเดิม) เพื่อให้แก้ไขต่อ/เซ็นซ้อนต่อ/ดาวน์โหลดได้ตามปกติไม่ล็อกอีก
    # ต่อไป (doc.saveIncr() ครั้งถัดไปต้องการไฟล์จริงเสมอ — ดูหมายเหตุหัวไฟล์ app/core/session.py)
    try:
        doc.close()
    except Exception:
        pass
    try:
        session.working_path.write_bytes(signed_bytes)
        session.doc = fitz.open(session.working_path)
    except Exception as exc:
        raise PDFError(f"เซ็นสำเร็จแต่เปิดไฟล์ผลลัพธ์กลับไม่ได้: {exc}") from exc

    session.signed_pdf_bytes = signed_bytes
    session.is_signed = True
    session.signature_type = "digital"
    return signer_cn


def _incremental_writer(doc, current_bytes: bytes, already_signed: bool):
    """IncrementalPdfFileWriter ของไฟล์ปัจจุบัน — ไฟล์ที่โครงสร้าง xref ผิดมาตรฐานเล็กน้อย (เช่น "0000000000 65536 f"
    จากโปรแกรมสร้าง PDF บางตัว) pyHanko อ่านแบบเข้มงวดไม่ผ่าน เดิมเซ็นไม่ได้ ขึ้นข้อความภาษาอังกฤษ "Illegal generation"
    → ยังไม่มีลายเซ็น: เขียนไฟล์ใหม่ให้ถูกต้องก่อน (เนื้อหาเดิมครบ) · มีลายเซ็นแล้ว (ห้ามเขียนใหม่): อ่านแบบผ่อนปรน"""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.misc import PdfReadError

    try:
        return IncrementalPdfFileWriter(io.BytesIO(current_bytes))
    except PdfReadError:
        if already_signed:
            return IncrementalPdfFileWriter(io.BytesIO(current_bytes), strict=False)
        logger.info("ไฟล์มี xref ผิดมาตรฐาน — เขียนใหม่ก่อนเซ็นดิจิทัล")
        return IncrementalPdfFileWriter(io.BytesIO(doc.tobytes(garbage=1)))


def _extract_common_name(signer) -> Optional[str]:
    try:
        cert = signer.signing_cert
        cn = cert.subject.native.get("common_name")
        return str(cn) if cn else None
    except Exception:
        return None


def _now_str() -> str:
    """เวลาตามเขตเวลาของระบบ (APP_TIMEZONE) — datetime.now() ใน container เป็น UTC (ไม่มีฐานข้อมูลเขตเวลาของ OS)"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.core.config import settings

    return datetime.now(ZoneInfo(settings.APP_TIMEZONE)).strftime("%d/%m/%Y %H:%M:%S")
