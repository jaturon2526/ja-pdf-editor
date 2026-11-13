"""การทำงานกับเอกสารที่เปิดอยู่ — unlock, undo/redo, render, ดาวน์โหลด, รหัสผ่าน, bookmark, คุณสมบัติ"""
import base64
import uuid
from typing import Literal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.api.deps import get_current_active_user, get_owned_session
from app.core.config import settings
from app.core.session import PDFSession, session_manager
from app.models.domain import User
from app.models.schemas import (
    AddPasswordRequest,
    BookmarksResponse,
    DocumentPropertiesResponse,
    PasswordChangeResponse,
    PDFInfoResponse,
    RenderPageResponse,
    SetBookmarksRequest,
    UndoRedoResponse,
    UnlockRequest,
    UnlockResponse,
)
from app.services import pdf_service
from app.services.pdf_service import PDFError

router = APIRouter()


class ExtractRequest(BaseModel):
    page_range: str
    mode: str = "single"
    format: str = "pdf"   # pdf | png | jpg
    dpi: int = 150        # เฉพาะรูปภาพ: 100 / 150 / 300


@router.post("/{session_id}/unlock", response_model=UnlockResponse)
def unlock_pdf(session_id: str, payload: UnlockRequest, session: PDFSession = Depends(get_owned_session)):
    with session.lock:
        ok = pdf_service.unlock(session, payload.password)
        if not ok:
            return UnlockResponse(status="invalid_password")
        page_count = pdf_service.get_page_count(session)
        session.push_history()  # baseline แรกของ undo/redo stack (ไฟล์นี้เพิ่งปลดล็อกเสร็จ)
    return UnlockResponse(status="ok", page_count=page_count)


@router.post("/{session_id}/undo", response_model=UndoRedoResponse)
def undo(session_id: str, session: PDFSession = Depends(get_owned_session)):
    """เลิกทำ (Undo) — ย้อนเอกสารทั้งฉบับกลับไปหนึ่งขั้นก่อนหน้า ครอบคลุมทั้งการแก้ไข annotation
    และการแก้ไขข้อความ/รูปภาพ (ดู app/core/session.py หมายเหตุ Undo/Redo) เอกสารเปลี่ยนไปทั้งฉบับ —
    ฝั่ง frontend ต้องรีเฟรชรูปหน้าปัจจุบัน + รายการ annotation/ย่อหน้า/รูปภาพใหม่ทั้งหมดเสมอเมื่อ
    status เป็น "ok" """
    with session.lock:
        ok = session.undo()
        status = "ok" if ok else "nothing_to_undo"
        can_undo, can_redo = session.can_undo(), session.can_redo()
        is_signed, signature_type = session.is_signed, session.signature_type
    return UndoRedoResponse(
        status=status,
        can_undo=can_undo,
        can_redo=can_redo,
        is_signed=is_signed,
        signature_type=signature_type,
    )


@router.post("/{session_id}/redo", response_model=UndoRedoResponse)
def redo(session_id: str, session: PDFSession = Depends(get_owned_session)):
    """ทำซ้ำ (Redo) — เดินหน้าเอกสารทั้งฉบับไปหนึ่งขั้นถัดไป (ย้อนกลับการ Undo ล่าสุด) ดูหมายเหตุที่ undo() ด้านบน"""
    with session.lock:
        ok = session.redo()
        status = "ok" if ok else "nothing_to_redo"
        can_undo, can_redo = session.can_undo(), session.can_redo()
        is_signed, signature_type = session.is_signed, session.signature_type
    return UndoRedoResponse(
        status=status,
        can_undo=can_undo,
        can_redo=can_redo,
        is_signed=is_signed,
        signature_type=signature_type,
    )


@router.get("/{session_id}/info", response_model=PDFInfoResponse)
def get_info(session_id: str, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            page_count = pdf_service.get_page_count(session)
            page_sizes = pdf_service.get_page_sizes(session)
            is_password_protected = bool(pdf_service.get_encryption_state(session))
            is_signed, signature_type = session.is_signed, session.signature_type
    except PDFError as exc:
        raise HTTPException(status_code=423, detail=str(exc))  # 423 Locked
    return PDFInfoResponse(
        session_id=session.session_id,
        filename=session.original_filename,
        page_count=page_count,
        is_unlocked=session.is_unlocked,
        page_sizes=page_sizes,
        is_password_protected=is_password_protected,
        is_signed=is_signed,
        signature_type=signature_type,
    )


@router.get("/{session_id}/page/{page_number}", response_model=RenderPageResponse)
def render_page(session_id: str, page_number: int, zoom: float = 1.5, fmt: Literal["jpeg", "png"] = "jpeg",
                session: PDFSession = Depends(get_owned_session)):
    try:
        # ล็อกกัน request render อื่น (เช่น thumbnail กับหน้าหลักที่ frontend ยิงพร้อมกัน) เข้าถึง
        # fitz.Document ตัวเดียวกันพร้อมกันจากคนละ thread (ดู session.lock ใน app/core/session.py)
        with session.lock:
            data, width, height = pdf_service.render_page_image(session, page_number, zoom, fmt)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RenderPageResponse(page_number=page_number, width=width, height=height,
                              image_base64=base64.b64encode(data).decode("ascii"),
                              image_mime="image/png" if fmt == "png" else "image/jpeg")


@router.get("/{session_id}/download")
def download_pdf(session_id: str, inline: bool = False, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            path = pdf_service.get_download_path(session)
            # ถ้าผู้ใช้ตั้งรหัสผ่านไว้ (เมนู File > เข้ารหัส PDF) get_download_path จะคืนไฟล์ temp ใหม่
            # ที่เข้ารหัสแล้วแยกต่างหาก (ไม่ใช่ working_path เดิม) — ต้องลบทิ้งหลังส่งเสร็จ เหมือนกับ
            # /export-pages ด้านบน (ดู pdf_service.get_download_path)
            is_temp_copy = path != session.working_path  # ไฟล์ส่งออก (บีบอัด/เข้ารหัส) ที่สร้างใหม่
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    background = BackgroundTask(lambda: path.unlink(missing_ok=True)) if is_temp_copy else None
    content_disposition_type = "inline" if inline else "attachment"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=session.original_filename,
        content_disposition_type=content_disposition_type,
        background=background,
    )


@router.get("/{session_id}/print")
def print_pdf(session_id: str, layout: str = "as_shown", session: PDFSession = Depends(get_owned_session)):
    """PDF สำหรับพิมพ์ "ตามที่เห็นบนจอ" — หน้าที่หมุนไม่กลับหัวตอนพิมพ์ (ดู pdf_service.build_print_pdf)"""
    try:
        with session.lock:
            data = pdf_service.build_print_pdf(session, layout)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@router.post("/{session_id}/add-password", response_model=PasswordChangeResponse)
def add_password(session_id: str, payload: AddPasswordRequest, session: PDFSession = Depends(get_owned_session)):
    """เข้ารหัส PDF (เมนู File > เข้ารหัส PDF... — ผู้ใช้แจ้งขอ กรณีไฟล์ไม่มีรหัสผ่านมาก่อน) ดู
    pdf_service.add_password — ไม่ได้เข้ารหัสไฟล์ที่กำลังแก้ไขในหน่วยความจำทันที แค่จำรหัสผ่านไว้ใช้
    ตอนสร้างไฟล์ดาวน์โหลดครั้งต่อไปเท่านั้น เรียกซ้ำเพื่อ "เปลี่ยน" รหัสผ่านที่ตั้งไว้ได้เสมอ"""
    try:
        with session.lock:
            pdf_service.add_password(session, payload.password, payload.encryption)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PasswordChangeResponse(status="ok", is_password_protected=True)


@router.post("/{session_id}/remove-password", response_model=PasswordChangeResponse)
def remove_password(session_id: str, session: PDFSession = Depends(get_owned_session)):
    """ลบรหัสผ่าน (เมนู File > ลบรหัสผ่าน — ผู้ใช้แจ้งขอ กรณีไฟล์เปิดด้วยรหัสผ่าน) ดู
    pdf_service.remove_password — ไฟล์ที่จะได้ตอนดาวน์โหลดครั้งต่อไปจะไม่มีรหัสผ่านป้องกันอีกต่อไป"""
    try:
        with session.lock:
            pdf_service.remove_password(session)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PasswordChangeResponse(status="ok", is_password_protected=False)


@router.get("/{session_id}/bookmarks", response_model=BookmarksResponse)
def get_bookmarks(session_id: str, session: PDFSession = Depends(get_owned_session)):
    """อ่าน bookmark ปัจจุบันของเอกสาร (PDF outline/TOC จริง — ดู pdf_service.get_bookmarks) เรียกตอน
    เปิดเอกสาร (โชว์ bookmark ที่ติดมากับไฟล์อยู่แล้วถ้ามี เช่นไฟล์ที่เคยดาวน์โหลดจากแอปนี้เอง) และ
    หลัง undo/redo (เอกสารเปลี่ยนไปทั้งฉบับ bookmark ก็ต้องรีเฟรชตาม)"""
    try:
        with session.lock:
            bookmarks = pdf_service.get_bookmarks(session)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return BookmarksResponse(bookmarks=bookmarks)


@router.put("/{session_id}/bookmarks", response_model=BookmarksResponse)
def set_bookmarks(session_id: str, payload: SetBookmarksRequest, session: PDFSession = Depends(get_owned_session)):
    """เขียน bookmark ทั้งชุดใหม่ทับของเดิม (full replace — ผู้ใช้แจ้งบั๊ก bookmark หายหลังกด Save แล้ว
    Download แล้วเปิดไฟล์ใหม่ เพราะของเดิมเก็บเป็น React state ฝั่ง frontend ล้วนๆ ไม่เคยลงไปอยู่ในไฟล์
    จริง ดู pdf_service.set_bookmarks) เขียนเอกสารที่เปิดอยู่จริงทันที จึง push_history() ให้ undo/redo
    ย้อนกลับได้เหมือนการแก้ไขอื่นๆ ทุกชนิด"""
    try:
        with session.lock:
            bookmarks = pdf_service.set_bookmarks(
                session,
                [b.model_dump() for b in payload.bookmarks],
            )
            session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return BookmarksResponse(bookmarks=bookmarks)


@router.get("/{session_id}/export-pages")
def export_pages(session_id: str, pages: str, session: PDFSession = Depends(get_owned_session)):
    """ส่งออกเฉพาะหน้าที่เลือกเป็นไฟล์ PDF ใหม่แยกต่างหาก (ผู้ใช้แจ้งขอฟีเจอร์นี้จากแผงหน้าเอกสารด้านซ้าย:
    เลือกได้หลายหน้า คลิกขวา ส่งออกเป็นไฟล์ใหม่) — pages เป็น query string ตัวเลขหน้า (0-based ตรงกับ
    เลขหน้าที่ frontend ใช้ภายใน) คั่นด้วยจุลภาค เช่น "0,2,5" ไม่แก้ไขเอกสารต้นฉบับ/working ที่เปิดอยู่เลย
    (ดู pdf_service.export_pages) เขียนผลลัพธ์ลงไฟล์ temp ใน WORKING_DIR ชั่วคราวก่อนส่งกลับด้วย
    FileResponse แบบเดียวกับ /download (Starlette เข้ารหัสชื่อไฟล์ภาษาไทย/ที่ไม่ใช่ ASCII ให้ถูกต้อง
    อัตโนมัติผ่าน RFC 5987 อยู่แล้ว ไม่ต้องทำเอง) ลบไฟล์ temp ทิ้งหลังส่งเสร็จด้วย BackgroundTask — ถ้า
    เผลอหลุดจริงๆ (เช่น client ตัดการเชื่อมต่อกลางทาง) cleanup_orphan_files() ใน session.py จะกวาดไฟล์
    เก่าเกิน 24 ชม. ใน WORKING_DIR ทิ้งอยู่ดี (เป็น safety net อีกชั้น — ดูหมายเหตุใน session.py)
    """
    try:
        page_numbers = [int(tok) for tok in pages.split(",") if tok.strip() != ""]
    except ValueError:
        raise HTTPException(status_code=400, detail="พารามิเตอร์ pages ไม่ถูกต้อง (ต้องเป็นเลขหน้าคั่นด้วยจุลภาค)")
    try:
        with session.lock:
            pdf_bytes = pdf_service.export_pages(session, page_numbers)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    settings.ensure_dirs()
    temp_path = settings.WORKING_DIR / f"export_{session_id}_{uuid.uuid4().hex}.pdf"
    temp_path.write_bytes(pdf_bytes)
    base_name = Path(session.original_filename or "document.pdf").stem
    download_name = f"{base_name}_pages.pdf"
    return FileResponse(
        temp_path,
        media_type="application/pdf",
        filename=download_name,
        background=BackgroundTask(lambda: temp_path.unlink(missing_ok=True)),
    )


@router.post("/{session_id}/extract")
def extract_pages(session_id: str, payload: ExtractRequest, current_user: User = Depends(get_current_active_user), session: PDFSession = Depends(get_owned_session)):
    """ดึงหน้า PDF ออกมาเป็นไฟล์ใหม่ แยกไฟล์ (ZIP) หรือส่งออกเป็นรูปภาพ PNG/JPG"""
    try:
        with session.lock:
            file_bytes, filename, mime_type = pdf_service.extract_pages(
                session, payload.page_range, payload.mode, payload.format, payload.dpi)
            
        # ชื่อไฟล์ภาษาไทยต้องเข้ารหัสแบบ RFC 5987 — เดิมใส่ตรงๆ ใน header (latin-1) ไฟล์ชื่อไทยแยกหน้าไม่ได้ (500)
        from urllib.parse import quote

        ascii_name = filename if filename.isascii() and filename.isprintable() and '"' not in filename else "pages" + Path(filename).suffix
        return Response(
            content=file_bytes,
            media_type=mime_type,
            headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"},
        )
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{session_id}/properties", response_model=DocumentPropertiesResponse)
def get_document_properties(session_id: str, session: PDFSession = Depends(get_owned_session)):
    """คุณสมบัติเอกสาร (Document Properties) แบบเดียวกับ Acrobat Reader (ผู้ใช้แจ้งขอ — เมนู File และ
    ปุ่มบน toolbar) ดู pdf_service.get_document_properties สำหรับรายละเอียดว่าแต่ละฟิลด์มาจากไหน/ทำไม
    บางฟิลด์อาจเป็น None ได้"""
    try:
        with session.lock:
            data = pdf_service.get_document_properties(session)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return DocumentPropertiesResponse(**data)


@router.delete("/{session_id}")
def close_session(session_id: str, session: PDFSession = Depends(get_owned_session)):
    session_manager.close(session_id)
    return {"status": "closed"}
