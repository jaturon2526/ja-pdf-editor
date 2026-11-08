from fastapi import APIRouter, UploadFile, File, HTTPException, Response
from app.core.heavy import ServerBusyError
from app.services.convert_service import convert_pdf_to_docx
import logging
from urllib.parse import quote

router = APIRouter(prefix="/convert", tags=["convert"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

from fastapi import Depends
from app.api.deps import get_current_active_user
from app.models.domain import User
from app.db.database import get_db
from sqlalchemy.orm import Session

def docx_name(pdf_name: str | None) -> str:
    """ชื่อไฟล์ Word จากชื่อ PDF — เดิม replace(".pdf", ".docx") ไฟล์ .PDF ตัวใหญ่ได้ชื่อลงท้าย .PDF"""
    import re

    stem = re.sub(r"\.pdf$", "", (pdf_name or "document.pdf").strip(), flags=re.IGNORECASE) or "document"
    return f"{stem}.docx"


@router.post("/pdf-to-word")
async def pdf_to_word(file: UploadFile = File(...), current_user: User = Depends(get_current_active_user)):
    """แปลงแบบรอผล (API) — ต้องเข้าสู่ระบบ: เดิมใครก็เรียกได้ไม่จำกัด และแปลงบน event loop ทำให้ทั้งเซิร์ฟเวอร์หยุดตอบ
    ระหว่างแปลงไฟล์ใหญ่ · หน้าเว็บใช้ /pdf-to-word/async"""
    from fastapi.concurrency import run_in_threadpool

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="ไฟล์ต้องเป็น PDF เท่านั้น")

    pdf_bytes = await file.read(MAX_FILE_SIZE + 1)

    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"ขนาดไฟล์เกิน {MAX_FILE_SIZE // (1024*1024)}MB")
        
    try:
        docx_bytes, status = await run_in_threadpool(convert_pdf_to_docx, pdf_bytes, current_user)

        filename_encoded = quote(docx_name(file.filename))
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
            "Access-Control-Expose-Headers": "Content-Disposition, X-Conversion-Status",
            "X-Conversion-Status": status
        }
        
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers
        )
    except ServerBusyError:
        raise
    except Exception as e:
        logging.error(f"Error converting PDF to Word: {e}")
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการแปลงไฟล์: {str(e)}")

from typing import Literal

from pydantic import BaseModel
import uuid
import os
from fastapi import BackgroundTasks
from app.models.domain import ConversionTask, FileRecord
from app.services.convert_service import process_conversion_task

class ConvertAsyncRequest(BaseModel):
    # ระบุอย่างใดอย่างหนึ่ง: ไฟล์ในเอกสารของฉัน หรือเอกสารที่เปิดอยู่ใน Editor (ใช้ฉบับที่บันทึกล่าสุด)
    file_record_id: int | None = None
    session_id: str | None = None
    # editable = แก้ไขข้อความได้ไหลตามย่อหน้า (ค่าเดิม), layout = รักษาหน้าตาเหมือนต้นฉบับ (ดู layout_docx.py)
    # scan = ไฟล์สแกน อ่านข้อความด้วย OCR (ไฟล์สแกนที่ส่งมาด้วยโหมดอื่นจะเปลี่ยนเป็น scan อัตโนมัติ)
    mode: Literal["editable", "layout", "scan"] = "editable"
    # ไฟล์สแกน: ให้ AI แก้คำไทยที่ OCR อ่านผิด (ใช้โควต้า AI) — ปิดเป็นค่าเริ่มต้น ผู้ใช้เลือกเอง
    use_ai: bool = False


class ConvertInspectRequest(BaseModel):
    file_record_id: int | None = None
    session_id: str | None = None


def _owned_record(db: Session, user: User, file_record_id: int | None, session_id: str | None) -> FileRecord:
    if file_record_id is not None:
        rec = db.query(FileRecord).filter(FileRecord.id == file_record_id).first()
    elif session_id:
        rec = db.query(FileRecord).filter(FileRecord.storage_path == session_id, FileRecord.user_id == user.id).first()
    else:
        raise HTTPException(status_code=422, detail="ต้องระบุ file_record_id หรือ session_id")
    if not rec or rec.user_id != user.id:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ในระบบ")
    return rec


@router.post("/pdf-to-word/inspect")
def pdf_to_word_inspect(req: ConvertInspectRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """ไฟล์นี้เป็นไฟล์สแกนไหม — หน้าต่างเลือกรูปแบบการแปลงใช้แสดงตัวเลือกที่เหมาะ"""
    from app.services import scan_docx
    from app.services.file_storage import resolve_stored_pdf

    rec = _owned_record(db, current_user, req.file_record_id, req.session_id)
    path = resolve_stored_pdf(rec)
    if path is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ต้นฉบับบนเซิร์ฟเวอร์")
    data = path.read_bytes()
    try:
        import fitz

        with fitz.open(stream=data, filetype="pdf") as doc:
            pages = doc.page_count
    except ServerBusyError:
        raise
    except Exception:
        pages = 0
    return {"scanned": scan_docx.is_scanned_pdf(data), "pages": pages, "max_pages": scan_docx.MAX_PAGES}


@router.post("/pdf-to-word/async")
def pdf_to_word_async(req: ConvertAsyncRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if req.file_record_id is not None:
        file_record = db.query(FileRecord).filter(FileRecord.id == req.file_record_id).first()
    elif req.session_id:
        # session_id ของ Editor = storage_path ของไฟล์ (ดู api/pdf/files.py save_to_server)
        file_record = db.query(FileRecord).filter(
            FileRecord.storage_path == req.session_id, FileRecord.user_id == current_user.id).first()
    else:
        raise HTTPException(status_code=422, detail="ต้องระบุ file_record_id หรือ session_id")
    if not file_record:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ในระบบ")
        
    if file_record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ในระบบ")
        
    task_id = str(uuid.uuid4())
    task = ConversionTask(
        id=task_id,
        user_id=current_user.id,
        file_record_id=file_record.id,
        status="pending",
        progress=0
    )
    db.add(task)
    db.commit()
    
    background_tasks.add_task(process_conversion_task, task_id, req.mode, req.use_ai)
    return {"task_id": task_id}

@router.get("/pdf-to-word/status/{task_id}")
def pdf_to_word_status(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    task = db.query(ConversionTask).filter(ConversionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="ไม่พบงานแปลงไฟล์")
        
    if task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="ไม่พบงานแปลงไฟล์")
        
    file_record = db.query(FileRecord).filter(FileRecord.id == task.file_record_id).first()
    original_name = file_record.filename if file_record else "document.pdf"
    
    return {
        "task_id": task.id,
        "status": task.status,
        "progress": task.progress,
        "error_message": task.error_message,
        "filename": original_name
    }

from fastapi.responses import FileResponse

@router.get("/pdf-to-word/download/{task_id}")
def pdf_to_word_download(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    task = db.query(ConversionTask).filter(ConversionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="ไม่พบงานแปลงไฟล์")
        
    if task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="ไม่พบงานแปลงไฟล์")
        
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="ไฟล์ยังแปลงไม่เสร็จ")
    if not task.result_file_path or not os.path.exists(task.result_file_path):
        raise HTTPException(status_code=410, detail="ไฟล์ Word ที่แปลงไว้หมดอายุแล้ว (เก็บไว้ 24 ชั่วโมง) — แปลงใหม่อีกครั้ง")
        
    file_record = db.query(FileRecord).filter(FileRecord.id == task.file_record_id).first()
    original_name = file_record.filename if file_record else "document.pdf"
    
    filename_encoded = quote(docx_name(original_name))
    return FileResponse(
        path=task.result_file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
            "X-Conversion-Status": task.error_message or "ai" # Hack to send status back
        }
    )
