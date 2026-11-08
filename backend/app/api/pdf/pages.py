"""จัดการหน้าเอกสาร — ลบ/หมุน/เรียงหน้า, บีบอัด, flatten, OCR พื้นที่ที่เลือก"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_active_user, get_owned_session
from app.core.session import PDFSession
from app.models.domain import User
from app.models.schemas import (
    CompressPdfRequest,
    DeletePagesRequest,
    Rect,
    ReorderPagesRequest,
    ReorderPagesResponse,
    RotatePagesRequest,
)
from app.services import pdf_service
from app.services.pdf_service import PDFError

router = APIRouter()


class OcrRequest(BaseModel):
    page_number: int
    rect: Rect


class OcrResponse(BaseModel):
    text: str


@router.delete("/{session_id}/pages")
def delete_pages(session_id: str, payload: DeletePagesRequest, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            changed = pdf_service.delete_pages(session, payload.page_numbers)
            if changed:
                session.push_history()
            return {"status": "ok" if changed else "no_change"}
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/pages/rotate")
def rotate_pages(session_id: str, payload: RotatePagesRequest, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            changed = pdf_service.rotate_pages(session, payload.page_numbers, payload.angle)
            if changed:
                session.push_history()
            return {"status": "ok" if changed else "no_change"}
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/compress")
def compress_pdf(session_id: str, payload: CompressPdfRequest, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            sizes = pdf_service.compress_pdf(session, payload.profile)
            if sizes is None:
                return {"status": "no_change"}
            session.push_history()
            return {"status": "ok", **sizes}
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/flatten")
def flatten_pdf(session_id: str, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            changed = pdf_service.flatten_pdf(session)
            if changed:
                session.push_history()
            return {"status": "ok"}
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/reorder-pages", response_model=ReorderPagesResponse)
def reorder_pages(session_id: str, payload: ReorderPagesRequest, session: PDFSession = Depends(get_owned_session)):
    """ย้ายตำแหน่งหน้าจริงในเอกสาร (ผู้ใช้แจ้งขอฟีเจอร์นี้จากแผงหน้าเอกสารด้านซ้าย: กดเมาส์ค้างที่
    thumbnail แล้วลากไปวาง — ส่ง target_page มา, หรือคลิกขวาเลือก "เลื่อนหน้าขึ้น/ลง" — ส่ง direction มา
    แทน) ต่างจาก /export-pages ด้านบน (สร้างไฟล์ใหม่แยกต่างหาก ไม่แตะเอกสารเดิม) ตรงที่ endpoint นี้แก้ไข
    เอกสารที่เปิดอยู่จริง จึง push_history() ให้ undo/redo ย้อนกลับได้เหมือนการแก้ไขอื่นๆ ทุกชนิด (ดู
    pdf_service.reorder_pages) เอกสารเปลี่ยนลำดับไปทั้งฉบับ — ฝั่ง frontend ต้องรีเฟรช thumbnail ทุกหน้า
    ใหม่เหมือนหลัง undo/redo"""
    try:
        with session.lock:
            changed = pdf_service.reorder_pages(
                session,
                payload.page_numbers,
                target_page=payload.target_page,
                direction=payload.direction,
            )
            page_count = pdf_service.get_page_count(session)
            if changed:
                session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ReorderPagesResponse(status="ok" if changed else "no_change", page_count=page_count)


@router.post("/{session_id}/extract_text_ocr", response_model=OcrResponse)
def extract_text_ocr_api(session_id: str, payload: OcrRequest, current_user: User = Depends(get_current_active_user), session: PDFSession = Depends(get_owned_session)):
    """ใช้ Tesseract OCR ดึงข้อความจากพื้นที่ที่เลือก"""
    try:
        with session.lock:
            text = pdf_service.extract_text_ocr(session, payload.page_number, payload.rect, user=current_user)
        return OcrResponse(text=text)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
