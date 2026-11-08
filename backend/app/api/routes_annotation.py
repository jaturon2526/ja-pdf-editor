from app.api.deps import get_owned_session
from app.core.session import PDFSession
from fastapi import Depends, APIRouter, HTTPException

from app.models.schemas import (
    AnnotationCreate,
    AnnotationDeleteRequest,
    AnnotationInfo,
    AnnotationUpdateRequest,
    WordInfo,
)
from app.services import annotation_service
from app.services.pdf_service import PDFError

router = APIRouter(prefix="/annotation", tags=["annotation"])




@router.post("/{session_id}", response_model=AnnotationInfo)
def create_annotation(session_id: str, payload: AnnotationCreate, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            result = annotation_service.add_annotation(session, payload)
            session.push_history()  # ดู app/core/session.py หมายเหตุ Undo/Redo
            return result
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{session_id}/page/{page_number}", response_model=list[AnnotationInfo])
def list_annotations(session_id: str, page_number: int, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            return annotation_service.list_annotations(session, page_number)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{session_id}/page/{page_number}/words", response_model=list[WordInfo])
def get_words(session_id: str, page_number: int, session: PDFSession = Depends(get_owned_session)):
    """คำทั้งหมดในหน้า พร้อมตำแหน่ง+line_key — ให้ frontend คำนวณตอนผู้ใช้ลากเลือกข้อความ
    (เครื่องมือไฮไลท์/โน้ต) ว่าครอบคำไหนบ้าง (ดู annotation_service.get_words)"""
    try:
        with session.lock:
            return annotation_service.get_words(session, page_number)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{session_id}", response_model=AnnotationInfo)
def update_annotation(session_id: str, payload: AnnotationUpdateRequest, session: PDFSession = Depends(get_owned_session)):
    """แก้ไข annotation ที่มีอยู่แล้ว — ไฮไลท์ (ย่อ/ขยาย+เปลี่ยนสี), กรอบสี่เหลี่ยม/กล่องข้อความ
    (ย่อ/ขยาย+แก้ข้อความ+เปลี่ยนสี), โน้ต (แก้ข้อความ+เปลี่ยนสี) ดู annotation_service.update_annotation
    — คืน AnnotationInfo ใหม่เสมอ (xref เปลี่ยน เพราะ implement ด้วยการลบของเดิมแล้วสร้างใหม่)"""
    try:
        with session.lock:
            result = annotation_service.update_annotation(session, payload)
            session.push_history()
            return result
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{session_id}")
def delete_annotation(session_id: str, payload: AnnotationDeleteRequest, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            ok = annotation_service.delete_annotation(session, payload.page_number, payload.xref)
            if ok:
                session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not ok:
        raise HTTPException(status_code=404, detail="ไม่พบ annotation ตาม xref ที่ระบุ")
    return {"status": "deleted"}
