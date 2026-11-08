"""pdf_service.core — เปิด/ปลดล็อก/render เอกสาร, สร้าง session, รหัสผ่าน, ไฟล์สำหรับดาวน์โหลด, รวมไฟล์"""
from __future__ import annotations

from typing import Optional
from app.core.config import settings
import base64
import uuid
from pathlib import Path
import fitz
import pikepdf
from app.core.session import PDFSession, session_manager

import logging

logger = logging.getLogger("pdf_service")


class PDFError(Exception):
    """ข้อผิดพลาดที่เกี่ยวกับการประมวลผล PDF ซึ่งควรถูกแปลงเป็น HTTP error ที่ route"""


def _flush_mupdf_warnings(context: str) -> None:
    """ดึงข้อความ warning/error ภายในของ MuPDF (ที่ปกติจะพ่นตรงไปที่ stderr แบบไม่มี context)
    มา log ผ่าน logging ของแอปแทน พร้อมระบุว่าเกิดตอนทำอะไร (context) จะได้ debug ง่ายขึ้น
    ต้องเรียกคู่กับ fitz.TOOLS.mupdf_display_errors(False) ใน main.py (ปิดการพ่น stderr ดิบ)
    """
    msg = fitz.TOOLS.mupdf_warnings(reset=True)
    if msg:
        logger.warning("MuPDF warning ระหว่าง %s: %s", context, msg.replace("\n", " | "))


def create_session_from_upload(file_bytes: bytes, filename: str, user_id: Optional[int] = None) -> tuple[PDFSession, bool]:
    """บันทึกไฟล์ที่ upload มา สร้าง session และลองเปิดไฟล์ทันที
    คืนค่า (session, needs_password)
    """
    settings.ensure_dirs()

    import uuid
    session_id = uuid.uuid4().hex
    safe_name = Path(filename).name  # สำหรับใช้ใน session (original_filename)

    # แก้ไข [Errno 36] File name too long โดยการใช้ session_id.pdf เพียวๆ เป็นชื่อไฟล์บนดิสก์
    # เพื่อหลีกเลี่ยงชื่อไฟล์ภาษาไทยที่ยาวเกินลิมิต 255 bytes ของระบบปฏิบัติการ
    disk_filename = f"{session_id}.pdf"
    
    original_path = settings.UPLOAD_DIR / disk_filename
    original_path.write_bytes(file_bytes)

    working_path = settings.WORKING_DIR / disk_filename
    import shutil
    shutil.copyfile(original_path, working_path)

    session = session_manager.create_session(
        original_path=original_path,
        working_path=working_path,
        original_filename=safe_name,
        user_id=user_id,
        session_id=session_id
    )
    
    needs_password = _try_open(session)
    return session, needs_password


def _try_open(session: PDFSession) -> bool:
    """เปิดไฟล์จาก working_path เก็บ fitz.Document ไว้ใน session
    คืนค่า True ถ้าไฟล์ต้องใช้รหัสผ่านและยังไม่ได้ authenticate
    """
    doc = fitz.open(session.working_path)
    session.doc = doc
    _flush_mupdf_warnings(f"เปิดไฟล์ครั้งแรก session={session.session_id}")
    if doc.needs_pass:
        session.is_unlocked = False
        return True
    session.is_unlocked = True
    _mark_existing_signatures(session)
    normalize_document_rotation(session)
    return False


def has_digital_signatures(doc) -> bool:
    """เอกสารมีลายเซ็นดิจิทัลฝังอยู่แล้ว (AcroForm SigFlags บิต SignaturesExist)"""
    try:
        flags = doc.get_sigflags()
    except Exception:
        return False
    return flags > 0 and bool(flags & 1)


def _mark_existing_signatures(session: PDFSession) -> None:
    """ไฟล์ที่เปิดมามีลายเซ็นดิจิทัลอยู่แล้ว (เช่น เอกสารที่ลงนามครบจากฟีเจอร์ลงนามตามลำดับ) — ตั้ง flag เดียวกับ
    ตอนเซ็นในแอป เพื่อกันการเข้ารหัส/สลับหน้า/บีบอัดตอนดาวน์โหลด ซึ่งจะทำให้ลายเซ็นเสีย"""
    if session.doc is not None and has_digital_signatures(session.doc):
        session.signed_pdf_bytes = session.signed_pdf_bytes or b"existing"
        session.is_signed = True
        session.signature_type = session.signature_type or "digital"


# ---------- หน้าที่หมุน (/Rotate) → หมุนเข้าเนื้อหน้าจริง ----------
# ทั้งแอปทำงานด้วยพิกัด "ตามที่เห็นบนจอ" (ภาพหน้าที่เรนเดอร์แล้วหมุนแล้ว) แต่ annotation/ข้อความ/รูปใน PDF ใช้พิกัดของ
# หน้าก่อนหมุน — หน้าที่มี /Rotate จึงวางไฮไลต์/กล่องข้อความ/กรอบผิดที่ (บนจอเห็นถูก แต่ไฟล์จริงไปอยู่อีกมุม) และเลือกคำ
# แก้ข้อความ ฯลฯ ไม่ตรง ทางแก้: ทำให้ทุกหน้า /Rotate = 0 เสมอ โดยหมุนเนื้อหน้า (content stream) แทน หน้าตาเหมือนเดิมทุก
# ประการ และพิกัดใน PDF = พิกัดบนจอ (ทำตอนเปิดไฟล์ และทุกครั้งที่ผู้ใช้กดหมุนหน้า — ยกเว้นไฟล์ที่มีลายเซ็นดิจิทัล)
# ไม่ใช้ fitz.Page.remove_rotation() เพราะรุ่นที่ใช้ย้ายลิงก์ผิดตำแหน่ง (get_links คืนพิกัดที่หมุนแล้วแต่ถูกคูณซ้ำ)
# และยืด appearance ของ annotation/ช่องฟอร์มแทนที่จะหมุน
_MARKUP_ANNOTS = {fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE, fitz.PDF_ANNOT_STRIKE_OUT, fitz.PDF_ANNOT_SQUIGGLY}
_ROTATE_CW = {90: fitz.Matrix(0, -1, 1, 0, 0, 0), 180: fitz.Matrix(-1, 0, 0, -1, 0, 0), 270: fitz.Matrix(0, 1, -1, 0, 0, 0)}


def _xref_matrix(doc, xref: int) -> fitz.Matrix:
    kind, value = doc.xref_get_key(xref, "Matrix")
    if kind != "array":
        return fitz.Matrix(1, 0, 0, 1, 0, 0)
    try:
        return fitz.Matrix(*[float(x) for x in value.strip("[]").split()])
    except (TypeError, ValueError):
        return fitz.Matrix(1, 0, 0, 1, 0, 0)


def normalize_page_rotation(page) -> bool:
    """หน้า /Rotate 90/180/270 → /Rotate 0 โดยหมุนเนื้อหน้า ลิงก์ annotation และช่องฟอร์มตาม (หน้าตาเหมือนเดิม) คืน True ถ้าแก้"""
    rot = page.rotation
    if rot not in _ROTATE_CW:
        return False
    doc = page.parent
    to_visible = page.rotation_matrix
    links = [{k: v for k, v in link.items() if k not in ("xref", "id", "zoom")} for link in page.get_links()]
    plan = []
    for annot in page.annots():
        verts = annot.vertices if annot.type[0] in _MARKUP_ANNOTS else None
        plan.append((annot.xref, annot.type[0], fitz.Rect(annot.rect) * to_visible,
                     [fitz.Point(v) * to_visible for v in verts] if verts else None))
    for widget in page.widgets():
        plan.append((widget.xref, fitz.PDF_ANNOT_WIDGET, fitz.Rect(widget.rect) * to_visible, None))

    # เนื้อหน้า: เติม cm ไว้หน้า content stream (ตามวิธีของ PyMuPDF remove_rotation) แล้วสลับกว้าง/สูงของ mediabox
    mb = page.mediabox
    if rot == 90:
        shift = fitz.Matrix(1, 0, 0, 1, mb.y1 - mb.x1 - mb.x0 - mb.y0, 0)
    elif rot == 270:
        shift = fitz.Matrix(1, 0, 0, 1, 0, mb.x1 - mb.y1 - mb.y0 - mb.x0)
    else:
        shift = fitz.Matrix(1, 0, 0, 1, -2 * mb.x0, -2 * mb.y0)
    mat = shift * page.derotation_matrix
    page.clean_contents()
    contents = page.get_contents()
    if contents:
        xref = contents[0]
        doc.update_stream(xref, ("q " + " ".join(f"{v:g}" for v in mat) + " cm\n").encode() + doc.xref_stream(xref) + b"\nQ")
    if rot in (90, 270):
        page.set_mediabox(fitz.Rect(mb.y0, mb.x0, mb.y1, mb.x1))
    page.set_rotation(0)

    # ลิงก์: get_links คืนพิกัดตามที่เห็นอยู่แล้ว = พิกัดใหม่
    for link in page.get_links():
        page.delete_link(link)
    for link in links:
        try:
            page.insert_link(link)
        except Exception:  # ลิงก์ชนิดที่ใส่คืนไม่ได้ ข้ามไป
            logger.warning("หมุนหน้า: ใส่ลิงก์คืนไม่สำเร็จ %s", link.get("uri") or link.get("page"))

    to_pdf = ~page.transformation_matrix
    turn = _ROTATE_CW[rot]
    for xref, atype, rect, verts in plan:
        if atype in _MARKUP_ANNOTS and verts:
            # ไฮไลต์/ขีดเส้นใต้: สร้างใหม่จาก quad ที่หมุนแล้ว (QuadPoints ใช้ทั้งวาดและเลือกข้อความ)
            old = next((a for a in page.annots() if a.xref == xref), None)
            if old is None:
                continue
            add = {fitz.PDF_ANNOT_HIGHLIGHT: page.add_highlight_annot, fitz.PDF_ANNOT_UNDERLINE: page.add_underline_annot,
                   fitz.PDF_ANNOT_STRIKE_OUT: page.add_strikeout_annot, fitz.PDF_ANNOT_SQUIGGLY: page.add_squiggly_annot}[atype]
            info, colors, opacity = old.info, old.colors, old.opacity
            new = add([fitz.Quad(verts[i:i + 4]) for i in range(0, len(verts) - 3, 4)])
            if colors.get("stroke"):
                new.set_colors(stroke=colors["stroke"])
            if opacity is not None and 0 <= opacity < 1:
                new.set_opacity(opacity)
            new.set_info(info)
            new.update()
            page.delete_annot(old)
            continue
        # อื่น ๆ: ย้าย /Rect และหมุน appearance stream ด้วย /Matrix — รูปลักษณ์เดิมทุกจุด ไม่ถูกยืด
        r = rect * to_pdf
        doc.xref_set_key(xref, "Rect", "[" + " ".join(f"{v:g}" for v in (r.x0, r.y0, r.x1, r.y1)) + "]")
        kind, value = doc.xref_get_key(xref, "AP/N")
        if kind == "xref":
            ap = int(value.split()[0])
            doc.xref_set_key(ap, "Matrix", "[" + " ".join(f"{v:g}" for v in _xref_matrix(doc, ap) * turn) + "]")
        if atype == fitz.PDF_ANNOT_WIDGET:   # ให้ appearance ที่สร้างใหม่ตอนแก้ค่าฟอร์มยังหมุนตามหน้า
            kind, value = doc.xref_get_key(xref, "MK/R")
            old_r = int(float(value)) if kind in ("int", "real") else 0
            doc.xref_set_key(xref, "MK/R", str((old_r + 360 - rot) % 360))
    return True


def normalize_document_rotation(session: PDFSession) -> int:
    """ทำทุกหน้าของเอกสารใน session ให้ /Rotate = 0 (ดู normalize_page_rotation) — ข้ามไฟล์ที่มีลายเซ็นดิจิทัล
    (แก้เนื้อหน้าแล้วลายเซ็นใช้ไม่ได้) คืนจำนวนหน้าที่แก้"""
    doc = session.doc
    if doc is None or session.signed_pdf_bytes is not None or has_digital_signatures(doc):
        return 0
    changed = 0
    for page in doc:
        try:
            changed += normalize_page_rotation(page)
        except Exception:  # หน้าแปลก ๆ ปล่อย /Rotate ไว้ดีกว่าเปิดไฟล์ไม่ได้
            logger.warning("หมุนหน้า %s เข้าเนื้อหน้าไม่สำเร็จ session=%s", page.number, session.session_id, exc_info=True)
    if changed:
        session.mark_dirty()
    return changed


def unlock(session: PDFSession, password: str) -> bool:
    """ลอง authenticate ด้วยรหัสผ่านที่ผู้ใช้กรอก คืน True ถ้าสำเร็จ

    ประวัติการแก้บั๊ก:
    รอบแรกสงสัยว่าเป็นบั๊ก MuPDF เรื่อง compressed object streams (ObjStm) ที่ถูกแตะก่อน
    authenticate แล้วแคช ciphertext ค้างไว้ — เลยลองแก้ด้วยการปิด document แล้วเปิดใหม่หลัง
    authenticate สำเร็จ แต่พบว่าไฟล์จริงที่มีปัญหาใช้ xref ธรรมดา (ไม่มี ObjStm เลย) และแก้แล้ว
    อาการยัง "MuPDF error: library error: zlib error: incorrect header check" อยู่ทุกครั้งที่ render
    แบบ deterministic (ไม่ใช่ race — render ซ้ำหน้าเดิมกี่ครั้งก็ error เหมือนเดิมทุกครั้ง แม้จะ
    ล็อกกัน concurrent access แล้วก็ตาม) แปลว่าปัญหาจริงคือ MuPDF (เวอร์ชันที่ pin ไว้ใน
    requirements.txt) ถอดรหัส RC4 (/Filter /Standard /V 2 /R 3) ของไฟล์นี้ผิดพลาดตอน decode
    content stream โดยเฉพาะ (มักเกิดกับไฟล์จากซอฟต์แวร์สร้าง PDF บางเจ้าที่ implement
    security handler ไม่ตรง spec เป๊ะ 100% แต่ viewer ทั่วไป/library อื่นยัง parse ได้)

    ทางแก้ที่ใช้จริง: เลี่ยงการให้ MuPDF ทำหน้าที่ถอดรหัส RC4 เอง — ใช้ pikepdf (สร้างบน qpdf ซึ่ง
    ขึ้นชื่อเรื่อง robust กับไฟล์ PDF ที่เขียนไม่ตรง spec) ตรวจรหัสผ่านแล้ว "ถอดรหัสจริง" ทับ
    working_path ให้กลายเป็น PDF ธรรมดาที่ไม่เข้ารหัสเลย จากนั้นค่อยเปิดไฟล์ (ที่ไม่เข้ารหัสแล้ว)
    ด้วย fitz ตามปกติ — fitz จึงไม่ต้องยุ่งกับการถอดรหัส RC4 ของไฟล์นี้อีกต่อไป
    (original_path ต้นฉบับที่เข้ารหัสยังอยู่ครบ ไม่ถูกแตะ ตามหลักการเดิมของระบบ)
    """
    try:
        with pikepdf.open(session.working_path, password=password, allow_overwriting_input=True) as pdf:
            pdf.save(session.working_path)
    except pikepdf.PasswordError:
        return False
    except pikepdf.PdfError as exc:
        raise PDFError(f"ถอดรหัส PDF ไม่สำเร็จ: {exc}") from exc

    if session.doc is not None:
        try:
            session.doc.close()
        except Exception:
            pass

    # เปิดไฟล์ที่ pikepdf ถอดรหัสแล้ว (ไม่มี /Encrypt อีกต่อไป) ด้วย fitz ตามปกติ
    session.doc = fitz.open(session.working_path)
    _flush_mupdf_warnings(f"เปิดไฟล์หลังถอดรหัสด้วย pikepdf session={session.session_id}")

    session.is_unlocked = True
    _mark_existing_signatures(session)
    normalize_document_rotation(session)
    return True


def is_locked(session: PDFSession) -> bool:
    """True ถ้า session นี้เป็นไฟล์ที่มีรหัสผ่านและยังไม่ได้ปลดล็อก (ใช้ให้ Dashboard รู้ว่าต้องถามรหัสก่อนเข้า Editor)"""
    doc = session.doc
    return doc is not None and bool(doc.needs_pass) and not session.is_unlocked


def require_unlocked(session: PDFSession) -> fitz.Document:
    """ helper: ใช้ต้นทาง route อื่นๆ เพื่อยืนยันว่าไฟล์พร้อมใช้งานแล้ว (ปลดล็อกแล้วถ้ามีรหัส)"""
    if session.doc is None:
        raise PDFError("Session ไม่พบเอกสารที่เปิดอยู่")
    if session.doc.needs_pass and not session.is_unlocked:
        raise PDFError("ไฟล์นี้ยังไม่ได้ปลดล็อกด้วยรหัสผ่าน")
    return session.doc


def get_encryption_state(session: PDFSession) -> bool | None:
    """เอกสาร (เวอร์ชันที่จะได้ตอนดาวน์โหลด) มีรหัสผ่านป้องกันอยู่ตอนนี้ไหม — True/False/None (ตรวจไม่ได้)

    ถ้าผู้ใช้เคยกด "ลบรหัสผ่าน"/"เข้ารหัส PDF" ในเซสชันนี้แล้ว (session.encryption_touched) ให้ยึดตาม
    การตั้งค่าล่าสุดนั้นเสมอ (session.output_password) — ไม่ต้องเช็คไฟล์ต้นฉบับอีก เพราะผู้ใช้ตั้งใจ
    เปลี่ยนสถานะไปแล้ว มิฉะนั้น (ยังไม่เคยแตะต้องเรื่องรหัสผ่านเลย) เช็คจากไฟล์ต้นฉบับ (original_path)
    เหมือน Document Properties เดิม (ตรวจว่าไฟล์ที่ผู้ใช้ upload มาจริงเข้ารหัสไว้หรือเปล่า ไม่ใช่ดูสถานะ
    ปลดล็อกของ session ปัจจุบัน ซึ่งจะเป็น "ปลดล็อกแล้ว" เสมอหลัง unlock สำเร็จ)
    """
    if session.encryption_touched:
        return session.output_password is not None
    try:
        probe = fitz.open(session.original_path)
        result = bool(probe.needs_pass)
        probe.close()
        return result
    except Exception:
        return None


ENCRYPTION_MODES = ("aes256", "aes128")
ENCRYPTION_LABELS = {"aes256": "AES-256", "aes128": "AES-128 (เข้ากันได้กับโปรแกรมรุ่นเก่า)"}
_R4_MAX_PASSWORD = 32  # มาตรฐาน AES-128/RC4 ใช้รหัสผ่านแค่ 32 ไบต์แรก


def check_password_for_mode(password: str, mode: str) -> None:
    """รหัสผ่านใช้กับวิธีเข้ารหัสนี้ได้ไหม — AES-128 (PDF 1.6/1.7 แบบเดิม) รับเฉพาะอักษรละติน
    (ตัวอังกฤษ ตัวเลข สัญลักษณ์) และใช้แค่ 32 ตัวแรก · AES-256 รับทุกภาษา (รวมภาษาไทย)"""
    if mode not in ENCRYPTION_MODES:
        raise PDFError("วิธีเข้ารหัสไม่ถูกต้อง")
    if not password or not password.strip():
        raise PDFError("กรุณากรอกรหัสผ่าน")
    if len(password) > 128:
        raise PDFError("รหัสผ่านยาวเกิน 128 ตัวอักษร")
    if mode == "aes128":
        try:
            password.encode("latin-1")
        except UnicodeEncodeError:
            raise PDFError("โหมดเข้ากันได้กับโปรแกรมรุ่นเก่า (AES-128) ใช้รหัสผ่านภาษาไทยไม่ได้ — ใช้ตัวอังกฤษ/ตัวเลข/สัญลักษณ์ "
                           "หรือเลือก AES-256 (แนะนำ) ซึ่งรองรับรหัสผ่านภาษาไทย") from None
        if len(password) > _R4_MAX_PASSWORD:
            raise PDFError(f"โหมด AES-128 ใช้รหัสผ่านได้ไม่เกิน {_R4_MAX_PASSWORD} ตัวอักษร — ตั้งให้สั้นลง หรือเลือก AES-256")


def pdfa_claim(pdf: "pikepdf.Pdf") -> Optional[str]:
    """ไฟล์ประกาศว่าเป็น PDF/A ไหม (XMP pdfaid) → เช่น "PDF/A-2b" หรือ None"""
    try:
        meta = pdf.open_metadata()
        part = str(meta.get("pdfaid:part", "") or "").strip()
        conf = str(meta.get("pdfaid:conformance", "") or "").strip().lower()
    except Exception:
        return None
    return f"PDF/A-{part}{conf}" if part else None


def pdfa_claim_of(path) -> Optional[str]:
    try:
        with pikepdf.open(path) as pdf:
            return pdfa_claim(pdf)
    except Exception:  # ไฟล์มีรหัสผ่าน/เสีย — ไม่ทราบ
        return None


def encrypt_pdf_file(src, out, password: str, mode: str = "aes256") -> None:
    """เข้ารหัสไฟล์ PDF (ผลลัพธ์เป็น PDF 1.7 เสมอ)

    - aes256 (ค่าเริ่มต้น แนะนำ): AES-256 แบบ R6 พร้อม Adobe Extension Level 8 — ตามมาตรฐาน PDF 1.7 ที่ Acrobat X
      (ปี 2010) ขึ้นไป, Chrome, Edge, Firefox, Preview ของ Mac/iPhone และแอปมือถือปัจจุบันเปิดได้ · ต้านการเดารหัสได้ดีกว่ามาก
      (เดิมใช้ PyMuPDF เขียน R6 แต่หัวไฟล์ 1.7 ไม่มี Extension — ผิดมาตรฐาน โปรแกรมตรวจไฟล์บางตัวเตือน)
    - aes128: AES-128 แบบ R4 (PDF 1.6+) สำหรับโปรแกรมรุ่นเก่ามาก (Acrobat 7–9) — รหัสผ่านต้องเป็นอักษรละติน
    ไฟล์ที่ประกาศว่าเป็น PDF/A: เอาคำประกาศออก เพราะ PDF/A ห้ามเข้ารหัส (ไม่ให้ไฟล์อ้างมาตรฐานที่ไม่ตรงความจริง)"""
    check_password_for_mode(password, mode)
    with pikepdf.open(src) as pdf:
        if pdfa_claim(pdf):
            with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
                for key in ("pdfaid:part", "pdfaid:conformance", "pdfaid:amd"):
                    if key in meta:
                        del meta[key]
        enc = (pikepdf.Encryption(owner=password, user=password, R=6, aes=True) if mode == "aes256"
               else pikepdf.Encryption(owner=password, user=password, R=4, aes=True))
        pdf.save(out, encryption=enc, min_version="1.7", object_stream_mode=pikepdf.ObjectStreamMode.generate)


def add_password(session: PDFSession, password: str, mode: str = "aes256") -> None:
    """เข้ารหัส PDF (เมนู File > เข้ารหัส PDF... — ผู้ใช้แจ้งขอ กรณีไฟล์ไม่มีรหัสผ่านมาก่อน) — ไม่ได้
    เข้ารหัสไฟล์ที่กำลังแก้ไขอยู่ในหน่วยความจำทันที (session.doc ยังคงไม่เข้ารหัสเสมอ แก้ไข/render
    ต่อได้ตามปกติไม่ต้องปลดล็อกซ้ำ) แค่ "จำรหัสผ่านที่จะใช้" ไว้ก่อน แล้วค่อยเข้ารหัสจริงตอนสร้างไฟล์
    สำหรับดาวน์โหลดเท่านั้น (ดู get_download_path) — ถ้าเคยตั้งรหัสผ่านไว้ก่อนหน้านี้แล้วในเซสชันเดียวกัน
    เรียกซ้ำเพื่อ "เปลี่ยน" รหัสผ่านใหม่ได้เลย (ทับค่าเดิม)

    ข้อยกเว้นทางเทคนิคที่ยังบล็อกอยู่ (ผู้ใช้แจ้งให้เอาเงื่อนไข "ล็อกเอกสารหลังเซ็น" ออกทั้งหมดแล้ว แต่ข้อนี้
    เป็นข้อจำกัดทางเทคนิคจริง ไม่ใช่การล็อกตามใจ — อีกจุดหนึ่งที่กันแบบเดียวกันคือ reorder_pages() ด้านล่าง
    เพราะ doc.select() ก็ rebuild เอกสารใหม่ทั้งหมดเช่นกัน): ถ้าเอกสารมีลายเซ็นดิจิทัล (PAdES) ฝังอยู่แล้ว
    (session.signed_pdf_bytes ไม่ใช่ None) ห้ามตั้งรหัสผ่านเข้ารหัสต่อ เพราะการเข้ารหัส PDF ต้องเขียน
    เนื้อไฟล์ใหม่ทั้งหมด (fitz doc.save(..., encryption=...)) ไม่ใช่การแก้ไขแบบ incremental เหมือนการ
    แก้ไขเนื้อหาอื่นๆ (annotation/ข้อความ/รูปภาพ/เซ็นซ้อน) ที่ยังคง byte-range ของลายเซ็นเดิมไว้ได้ —
    เข้ารหัสทับจะทำให้ลายเซ็นดิจิทัลที่ฝังไว้ก่อนหน้านี้ใช้งานไม่ได้ทันทีโดยผู้ใช้อาจไม่รู้ตัว"""
    if session.signed_pdf_bytes is not None:
        raise PDFError(
            "เอกสารนี้มีลายเซ็นดิจิทัล (PAdES) ฝังอยู่แล้ว ไม่สามารถเข้ารหัส PDF ต่อได้ เพราะจะทำให้"
            "ลายเซ็นดิจิทัลที่ฝังไว้ใช้งานไม่ได้อีกต่อไป (การเข้ารหัสต้องเขียนเนื้อไฟล์ใหม่ทั้งหมด "
            "ต่างจากการแก้ไขเนื้อหาอื่นๆ ที่ทำแบบ incremental ได้) กรุณา Undo ย้อนกลับไปก่อนจุดที่เซ็นถ้าต้องการเข้ารหัส"
        )
    require_unlocked(session)
    check_password_for_mode(password, mode)
    session.output_password = password
    session.output_encryption = mode
    session.encryption_touched = True


def remove_password(session: PDFSession) -> None:
    """ลบรหัสผ่าน (เมนู File > ลบรหัสผ่าน — ผู้ใช้แจ้งขอ กรณีไฟล์เปิดด้วยรหัสผ่าน) — ทำให้ไฟล์ที่จะได้
    ตอนดาวน์โหลดครั้งต่อไปไม่มีรหัสผ่านป้องกันอีกต่อไป ไม่ว่าไฟล์ต้นฉบับที่ upload มาจะเข้ารหัสไว้หรือ
    ไม่ก็ตาม (ดู get_encryption_state — ตั้งแต่เรียกฟังก์ชันนี้แล้ว จะยึดตามนี้เสมอ ไม่เช็คไฟล์ต้นฉบับอีก)
    ไม่ต้องกันเอกสารที่เซ็นดิจิทัลไว้แล้วเหมือน add_password — "ไม่เข้ารหัสเลย" ไม่มีทางทำให้ลายเซ็นเดิม
    เสียหาย (ไม่มีการเขียนไฟล์ใหม่แบบไม่ incremental เกิดขึ้น)"""
    require_unlocked(session)
    session.output_password = None
    session.encryption_touched = True


def get_page_count(session: PDFSession) -> int:
    doc = require_unlocked(session)
    return doc.page_count


def get_page_sizes(session: PDFSession) -> list[tuple[float, float]]:
    doc = require_unlocked(session)
    return [(page.rect.width, page.rect.height) for page in doc]


MAX_RENDER_ZOOM = 8.0
MAX_RENDER_PIXELS = 40_000_000  # ~160 MB RGBA — หน้าใหญ่มาก (เช่นแบบแปลน A0) ลดซูมลงเองแทนการกินหน่วยความจำ


def _safe_render_zoom(page, zoom: float) -> float:
    """ซูมที่ใช้เรนเดอร์จริง: ไม่ติดลบ/ไม่ใหญ่เกิน และจำนวนพิกเซลไม่เกิน MAX_RENDER_PIXELS"""
    try:
        zoom = float(zoom)
    except (TypeError, ValueError):
        zoom = 1.5
    if not zoom or zoom != zoom:  # 0 / NaN
        zoom = 1.5
    zoom = min(MAX_RENDER_ZOOM, max(0.05, zoom))
    area = max(1.0, page.rect.width * page.rect.height)
    if area * zoom * zoom > MAX_RENDER_PIXELS:
        zoom = (MAX_RENDER_PIXELS / area) ** 0.5
    return zoom


def render_page(session: PDFSession, page_number: int, zoom: float = 1.5) -> tuple[bytes, float, float]:
    """render หน้าที่ระบุเป็น PNG bytes พร้อมขนาด (width, height) ของหน้าต้นฉบับ (point)"""
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง (มีทั้งหมด {doc.page_count} หน้า)")

    page = doc[page_number]
    zoom = _safe_render_zoom(page, zoom)
    matrix = fitz.Matrix(zoom, zoom)
    # กล่องข้อความ/กรอบของแอปที่สร้างก่อนมี appearance ของตัวเอง → สร้างให้ (ครั้งเดียว) แล้ว render ตามจริง
    # เดิมทุกครั้งที่ render ลบ AP ของ FreeText ทุกตัวทิ้ง (รวมของโปรแกรมอื่น) — แค่เปิดดูหน้า ข้อความในไฟล์ก็หาย
    if session.signed_pdf_bytes is None and not has_digital_signatures(doc):
        from app.services import annotation_service
        if annotation_service.ensure_text_appearances(doc, [page_number], user_id=session.user_id):
            session.mark_dirty()
        page = doc[page_number]  # หน้าชั่วคราวตอนสร้าง appearance ทำให้ object หน้าเดิมใช้ไม่ได้
    pixmap = page.get_pixmap(matrix=matrix)

    png_bytes = pixmap.tobytes("png")
    _flush_mupdf_warnings(f"render หน้า {page_number} session={session.session_id}")
    return png_bytes, page.rect.width, page.rect.height


JPEG_QUALITY = 85


def render_page_image(session: PDFSession, page_number: int, zoom: float = 1.5, fmt: str = "jpeg") -> tuple[bytes, float, float]:
    """ภาพหน้าสำหรับแสดงบนจอ — JPEG (ค่าเริ่มต้น) เข้ารหัสเร็วกว่า PNG ราว 10 เท่า ขนาดไฟล์ใกล้เคียง/เล็กกว่า
    (คอขวด CPU ของ load test คือการเข้ารหัส PNG ไม่ใช่การเรนเดอร์) · 4:4:4 ไม่ลดสี ตัวหนังสือสีคม · cache ตามรุ่นเอกสาร"""
    from app.services import render_cache

    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง (มีทั้งหมด {doc.page_count} หน้า)")
    eff_zoom = _safe_render_zoom(doc[page_number], zoom)
    key = render_cache.key_for(session, page_number, eff_zoom, fmt)
    rect = doc[page_number].rect
    cached = render_cache.get(key)
    if cached is not None:
        return cached, rect.width, rect.height
    if fmt == "png":
        data, w, h = render_page(session, page_number, zoom)
    else:
        import io

        from PIL import Image

        doc = require_unlocked(session)
        page = doc[page_number]
        if session.signed_pdf_bytes is None and not has_digital_signatures(doc):
            from app.services import annotation_service
            if annotation_service.ensure_text_appearances(doc, [page_number], user_id=session.user_id):
                session.mark_dirty()
            page = doc[page_number]
        pix = page.get_pixmap(matrix=fitz.Matrix(eff_zoom, eff_zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=JPEG_QUALITY, subsampling=0)
        data, w, h = buf.getvalue(), page.rect.width, page.rect.height
        _flush_mupdf_warnings(f"render หน้า {page_number} session={session.session_id}")
    render_cache.put(render_cache.key_for(session, page_number, eff_zoom, fmt), data)
    return data, w, h


def render_page_base64(session: PDFSession, page_number: int, zoom: float = 1.5) -> tuple[str, float, float]:
    png_bytes, w, h = render_page(session, page_number, zoom)
    return base64.b64encode(png_bytes).decode("ascii"), w, h


def save_working_copy(session: PDFSession) -> Path:
    """เซฟการแก้ไขทั้งหมดที่ทำผ่าน fitz ลงไฟล์ working_path (incremental save)

    ใช้ session.flush_to_disk() (ไม่เรียก doc.saveIncr() ตรงๆ) — flush_to_disk() เช็คก่อนเสมอว่ามีการ
    แก้ไขค้างจริงไหม (session mark_dirty ไว้หรือยัง) ถ้าไม่มี (เช่น กดดาวน์โหลดซ้ำติดกันโดยไม่ได้แก้ไข
    อะไรเพิ่ม หรือ push_history() ของการแก้ไขล่าสุดเพิ่งเซฟไปแล้ว) จะข้าม ไม่เรียก saveIncr() ซ้ำ — ป้องกัน
    บั๊กจริงของ MuPDF/PyMuPDF ที่พบระหว่างแก้ไขฟีเจอร์นี้: เรียก doc.saveIncr() ติดกัน 2 ครั้งโดยไม่มีการ
    แก้ไขคั่นกลางเลย จะทำให้ไฟล์เสียหายทันที (เปิดกลับมาได้ 0 หน้า) ดูหมายเหตุ _doc_dirty ใน
    app/core/session.py"""
    require_unlocked(session)
    session.flush_to_disk()
    return session.working_path


def get_download_path(session: PDFSession) -> Path:
    """คืน path ไฟล์เวอร์ชันล่าสุด (พร้อมให้ผู้ใช้ดาวน์โหลด) — เซฟให้ก่อนเสมอ

    ถ้าผู้ใช้กด "เข้ารหัส PDF" ไว้ในเซสชันนี้ (session.output_password มีค่า — ดู add_password) จะสร้าง
    ไฟล์เข้ารหัสแยกต่างหากเป็นไฟล์ temp ใหม่ทุกครั้งที่เรียก (สะท้อนการแก้ไขล่าสุดเสมอ) โดยไม่แตะ
    working_path เดิม (ยังคงไม่เข้ารหัสไว้ใช้แก้ไขต่อในเซสชันได้ตามปกติ ไม่ต้องปลดล็อกซ้ำ) — ผู้เรียก
    (route /download) มีหน้าที่ลบไฟล์ temp นี้ทิ้งหลังส่งเสร็จ โดยเช็คว่า path ที่ได้กลับมา "ไม่ใช่"
    working_path เดิม (ถ้าไม่มีรหัสผ่านที่ต้องเข้ารหัส จะได้ working_path ตรงๆ กลับไปเหมือนเดิม
    ไม่ต้องลบทิ้งหลังส่ง)

    เรื่อง Digital Signature (ผู้ใช้แจ้งขอไม่ต้องล็อกเอกสารหลังเซ็นอีกต่อไป แก้ไข/เซ็นซ้อนต่อได้เรื่อยๆ):
    ก่อนหน้านี้ฟังก์ชันนี้มีทางลัดพิเศษคืน session.signed_pdf_bytes ตรงๆ โดยข้าม save_working_copy()
    ไปเลย (กันไม่ให้ fitz re-serialize ทับ byte-range ที่ลายเซ็นครอบคลุมอยู่) — ตอนนี้ไม่จำเป็นอีกต่อไป
    เพราะ session.doc เปิดจาก "ไฟล์จริง" (session.working_path) เสมอทุกจุดแล้ว (ดู
    signature_service.apply_digital_signature และ session.py _restore_from_history) และ
    save_working_copy() ใช้ doc.saveIncr() (incremental) ซึ่งทดสอบยืนยันแล้วว่ารักษาลายเซ็นดิจิทัลที่
    เคยฝังไว้ก่อนหน้าให้ยัง valid อยู่เสมอ ไม่ว่าจะมีการแก้ไขเนื้อหาเพิ่มหรือเซ็นซ้อนอีกกี่รอบก็ตาม —
    ส่วนกรณีเข้ารหัส PDF (encryption=... ด้านล่าง ซึ่ง "ไม่ใช่" incremental) ถูกกันไว้แล้วตั้งแต่ต้นทาง
    ที่ add_password() (ปฏิเสธถ้าเอกสารมีลายเซ็นดิจิทัลฝังอยู่) จึงไม่มีทางมาถึง branch เข้ารหัสด้านล่าง
    พร้อมกับเอกสารที่เซ็นดิจิทัลไว้แล้วได้เลย"""
    signed = session.signed_pdf_bytes is not None or has_digital_signatures(session.doc)
    if not signed and session.doc is not None and not (session.doc.needs_pass and not session.is_unlocked):
        # กล่องข้อความ/กรอบรุ่นก่อน v1.26.12 (ยังไม่มี appearance) — สร้างให้ ไม่งั้นโปรแกรมอื่นไม่เห็นข้อความไทย
        from app.services import annotation_service
        if annotation_service.ensure_text_appearances(session.doc, user_id=session.user_id):
            session.mark_dirty()
    save_working_copy(session)
    # ไฟล์ทำงานถูกบันทึกแบบ incremental (saveIncr) ทุกครั้งที่แก้ — ของเก่าทุกเวอร์ชันยังค้างอยู่ในไฟล์ ไฟล์จึงโต
    # ขึ้นเรื่อยๆ (ผู้ใช้เจอ 170 KB → 9 MB หลังแก้ไม่กี่ครั้ง) ไฟล์ที่ส่งออกจึงเขียนใหม่แบบตัดของเก่าทิ้ง
    # ยกเว้นเอกสารที่มีลายเซ็นดิจิทัล: เขียนใหม่ทั้งไฟล์จะทำให้ลายเซ็น invalid (ต้องคงแบบ incremental)
    if (session.signed_pdf_bytes is not None or has_digital_signatures(session.doc)) and not session.output_password:
        return session.working_path
    settings.ensure_dirs()
    prefix = "encrypted" if session.output_password else "export"
    temp_path = settings.WORKING_DIR / f"{prefix}_{session.session_id}_{uuid.uuid4().hex}.pdf"
    doc = fitz.open(session.working_path)
    try:
        doc.save(temp_path, garbage=3, deflate=True)
    finally:
        doc.close()
    if session.output_password:
        plain = temp_path.with_suffix(".plain.pdf")
        temp_path.replace(plain)
        try:
            encrypt_pdf_file(plain, temp_path, session.output_password, session.output_encryption or "aes256")
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            plain.unlink(missing_ok=True)
    return temp_path


MERGE_MAX_FILES = 30


def merge_pdf_bytes(file_contents: list[bytes], filenames: list[str], title: str) -> tuple[bytes, int]:
    """รวม PDF ตามลำดับ → (ไฟล์ที่รวมแล้ว, จำนวนหน้า)
    - บุ๊กมาร์กระดับบนสุด = ชื่อไฟล์ต้นทางแต่ละไฟล์ (ชี้หน้าแรกของไฟล์นั้น) และบุ๊กมาร์กเดิมของไฟล์ซ้อนอยู่ข้างใต้
    - ไฟล์ที่มีรหัสผ่าน / เปิดไม่ได้ → PDFError บอกชื่อไฟล์"""
    if len(file_contents) < 2:
        raise PDFError("ต้องมีไฟล์อย่างน้อย 2 ไฟล์สำหรับรวม")
    if len(file_contents) > MERGE_MAX_FILES:
        raise PDFError(f"รวมได้ครั้งละไม่เกิน {MERGE_MAX_FILES} ไฟล์")
    merged = fitz.open()
    toc: list[list] = []
    try:
        for content, name in zip(file_contents, filenames):
            try:
                doc = fitz.open("pdf", content)
            except Exception:
                raise PDFError(f"เปิดไฟล์ {name} ไม่ได้ — ไฟล์เสียหรือไม่ใช่ PDF") from None
            try:
                if doc.needs_pass:
                    raise PDFError(f"ไฟล์ {name} มีรหัสผ่าน — เปิดไฟล์แล้วนำรหัสผ่านออกก่อน (เมนู ไฟล์ → รหัสผ่าน) แล้วรวมใหม่")
                if doc.page_count == 0:
                    raise PDFError(f"ไฟล์ {name} ไม่มีหน้า")
                start = merged.page_count
                sub = doc.get_toc(simple=False)
                merged.insert_pdf(doc)
            finally:
                doc.close()
            toc.append([1, Path(name).stem or name, start + 1])
            for entry in sub:
                level, label, page = entry[0], entry[1], entry[2]
                if page >= 1:
                    toc.append([level + 1, label, start + page])
        try:
            merged.set_toc(toc)
        except Exception:  # noqa: BLE001 — บุ๊กมาร์กเดิมผิดรูป: ใช้เฉพาะชื่อไฟล์
            merged.set_toc([t for t in toc if t[0] == 1])
        merged.set_metadata({"title": title, "producer": "JA PDF Editor", "creator": "JA PDF Editor",
                             "creationDate": fitz.get_pdf_now(), "modDate": fitz.get_pdf_now()})
        pages = merged.page_count
        return merged.tobytes(garbage=3, deflate=True), pages
    finally:
        merged.close()
