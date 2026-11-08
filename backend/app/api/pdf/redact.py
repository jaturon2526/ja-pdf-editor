"""Redaction (ปิดทับข้อความ/พื้นที่แบบถาวร) — /pdf/{session_id}/redact*"""
import logging

import fitz
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.heavy import ServerBusyError
from app.api.deps import get_owned_session
from app.core.session import PDFSession
from app.services import pdf_service

logger = logging.getLogger("routes.pdf.redact")
router = APIRouter()


def _locked(session: PDFSession, fn, *args):
    """รัน fn ภายใต้ session.lock ใน threadpool — PyMuPDF ไม่ thread-safe และงาน redact ใช้ CPU หนัก
    จึงไม่ควรรันบน event loop ตรงๆ (เดิม endpoint กลุ่มนี้รันบน event loop และไม่ได้ล็อก)"""
    with session.lock:
        return fn(*args)


def _redact_rect_all_pages(session: PDFSession, rects_data: list) -> None:
    doc = pdf_service.require_unlocked(session)
    for page in doc:
        for rect_data in rects_data:
            fitz_rect = fitz.Rect(rect_data["x0"], rect_data["y0"], rect_data["x1"], rect_data["y1"])
            page.add_redact_annot(fitz_rect, fill=(0, 0, 0))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    session.mark_dirty()
    session.push_history()


@router.post("/{session_id}/redact-all-pages")
async def redact_all_pages(session_id: str, request: Request, session: PDFSession = Depends(get_owned_session)):
    """Redact สี่เหลี่ยมเดียวกันในทุกหน้า"""
    data = await request.json()
    rects_data = data.get("rects")
    if not rects_data or not isinstance(rects_data, list):
        raise HTTPException(status_code=400, detail="Missing rects array")
    try:
        await run_in_threadpool(_locked, session, _redact_rect_all_pages, session, rects_data)
    except pdf_service.PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ServerBusyError:
        raise
    except Exception as exc:
        logger.exception("redact-all-pages ล้มเหลว session=%s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


@router.post("/{session_id}/redact-search")
async def redact_pdf_search(session_id: str, request: Request, session: PDFSession = Depends(get_owned_session)):
    """ค้นหาคำ/regex แล้ว redact ทุกตำแหน่งที่พบ"""
    data = await request.json()
    keyword = data.get("keyword")
    if not keyword:
        raise HTTPException(status_code=400, detail="Missing keyword")
    try:
        count = await run_in_threadpool(
            _locked, session, pdf_service.redact_by_search, session, keyword,
            data.get("match_case", False), data.get("is_regex", False),
        )
    except ValueError as exc:  # regex ผิด / คำค้นยาวเกิน
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if count == -1:
        raise HTTPException(status_code=500, detail="Error during redaction")
    result = {"status": "ok", "redacted_count": count}
    if count == 0:  # ไม่เจอ — บอกหน้าที่มีรูปภาพ (ข้อความในรูปค้นด้วยคำไม่ได้)
        result["image_pages"] = await run_in_threadpool(pdf_service.pages_with_images, session)
    return result


@router.post("/{session_id}/redact_batch")
async def redact_pdf_batch(session_id: str, request: Request, session: PDFSession = Depends(get_owned_session)):
    data = await request.json()
    page_number = data.get("pageNumber")
    rects = data.get("rects")
    if page_number is None or not rects:
        raise HTTPException(status_code=400, detail="Missing pageNumber or rects")
    try:
        await run_in_threadpool(_locked, session, pdf_service.redact_areas_batch, session, page_number, rects)
    except ServerBusyError:
        raise
    except Exception as exc:
        logger.exception("redact_batch ล้มเหลว session=%s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


@router.post("/{session_id}/redact")
async def redact_pdf(session_id: str, request: Request, session: PDFSession = Depends(get_owned_session)):
    """Redact สี่เหลี่ยมเดียวบนหน้าที่ระบุ (ปิดทับถาวร)"""
    data = await request.json()
    page_number = data.get("pageNumber")
    rect_data = data.get("rect")
    if page_number is None or not rect_data:
        raise HTTPException(status_code=400, detail="Missing pageNumber or rect")
    try:
        await run_in_threadpool(_locked, session, pdf_service.redact_area, session, page_number, rect_data)
    except ServerBusyError:
        raise
    except Exception as exc:
        logger.exception("redact ล้มเหลว session=%s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


# ---------------------------------------------------------------- PDPA


class PIIRedactRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=5000)
    clean_metadata: bool = False


@router.post("/{session_id}/pii/scan")
async def pii_scan(session_id: str, session: PDFSession = Depends(get_owned_session)):
    """ตรวจหาข้อมูลส่วนบุคคลทั้งเอกสาร (ทำบนเซิร์ฟเวอร์ ไม่ส่งออกภายนอก) — ยังไม่แก้ไฟล์"""
    try:
        return await run_in_threadpool(_locked, session, pdf_service.scan_pii, session)
    except pdf_service.PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/pii/redact")
async def pii_redact(session_id: str, payload: PIIRedactRequest, session: PDFSession = Depends(get_owned_session)):
    """ปิดทับถาวรเฉพาะรายการที่เลือกจากผล scan (undo ได้ใน Editor)"""
    try:
        return await run_in_threadpool(_locked, session, pdf_service.redact_pii, session, payload.ids, payload.clean_metadata)
    except pdf_service.PIIStaleError:
        raise HTTPException(status_code=409, detail="เอกสารมีการเปลี่ยนแปลงหลังสแกน กรุณาสแกนใหม่อีกครั้ง")
    except pdf_service.PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class OcrLayerRequest(BaseModel):
    pages: list[int] | None = None  # เลขหน้าเริ่ม 0 — ไม่ส่ง = ทุกหน้าที่มีรูปภาพ


@router.post("/{session_id}/ocr-text-layer")
async def ocr_text_layer(session_id: str, payload: OcrLayerRequest | None = None,
                         session: PDFSession = Depends(get_owned_session)):
    """อ่านข้อความในรูปภาพ (OCR) แล้ววางเป็นข้อความล่องหน — ให้ค้นหา/เซ็นเซอร์ข้อความในรูปได้ (ดู pdf_service.ocr)"""
    pages = payload.pages if payload else None
    try:
        return await run_in_threadpool(_locked, session, pdf_service.add_ocr_text_layer, session, pages)
    except pdf_service.PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
