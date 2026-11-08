"""สแกนเอกสารด้วยกล้องมือถือ — รับภาพทุกหน้า (ดัดภาพ/ขาวดำมาแล้วจากเครื่องผู้ใช้) แล้วสร้าง PDF + OCR เป็นงานเบื้องหลัง

POST /pdf/scan              multipart: filename, pages[] (PNG/JPEG ตามลำดับหน้า), ocr_pages[] (ไม่บังคับ: ภาพเทา ocr-NNN.*) → {"task_id"}
GET  /pdf/scan/status/{id}  → {"status": pending|processing|completed|failed, "progress", "error_message", "file"}

งานเก็บในตาราง conversion_tasks (ใช้ร่วมกับงานแปลงเป็น Word — file_record_id ว่างจนสร้างไฟล์เสร็จ)
ภาพต้นฉบับเก็บชั่วคราวระหว่างทำงานแล้วลบทิ้ง — ระบบเก็บเฉพาะ PDF ที่ได้
"""
from __future__ import annotations

import logging
import re
import shutil
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.api.pdf.files import check_storage_quota
from app.core.config import settings
from app.db.database import get_db
from app.models.domain import ConversionTask, FileRecord, User
from app.services import file_storage, pdf_service
from app.services.pdf_service import PDFError

logger = logging.getLogger("routes.pdf.scan")
router = APIRouter()

_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def clean_scan_filename(name: str) -> str:
    """ชื่อไฟล์จากเครื่องผู้ใช้ (เช่น Scan_20261025_152133) → ปลอดภัยสำหรับเก็บ ลงท้าย .pdf"""
    name = _BAD_CHARS.sub("_", (name or "").strip()).strip(". ")[:150]
    if name.lower().endswith(".pdf"):
        name = name[:-4].rstrip()
    return f"{name or 'Scan'}.pdf"


def _unique_filename(db: Session, user_id: int, filename: str) -> str:
    existing = {f for (f,) in db.query(FileRecord.filename).filter(FileRecord.user_id == user_id).all()}
    if filename not in existing:
        return filename
    base = filename[:-4]
    n = 2
    while f"{base} ({n}).pdf" in existing:
        n += 1
    return f"{base} ({n}).pdf"


def _scan_dir(task_id: str):
    return settings.WORKING_DIR / f"scan_{task_id}"


def process_scan_task(task_id: str, filename: str) -> None:
    from app.db.database import SessionLocal

    db = SessionLocal()
    folder = _scan_dir(task_id)
    try:
        task = db.query(ConversionTask).filter(ConversionTask.id == task_id).first()
        if not task:
            return
        task.status, task.progress = "processing", 5
        db.commit()
        images = [p.read_bytes() for p in sorted(folder.glob("*.img"))]
        ocr_images = [(folder / f"{i:03d}.ocr").read_bytes() if (folder / f"{i:03d}.ocr").exists() else None
                      for i in range(len(images))]

        def progress(done: int, total: int) -> None:
            task.progress = 5 + int(85 * done / total)
            db.commit()

        title = filename[:-4]
        pdf_bytes = pdf_service.build_scan_pdf(images, title=title, progress=progress, ocr_images=ocr_images)
        user = db.query(User).filter(User.id == task.user_id).first()
        check_storage_quota(db, user, len(pdf_bytes))

        storage_id = uuid.uuid4().hex
        file_storage.upload_path(storage_id).write_bytes(pdf_bytes)
        final_name = _unique_filename(db, user.id, filename)
        record = FileRecord(user_id=user.id, filename=final_name, original_filename=final_name,
                            storage_path=storage_id, file_size=len(pdf_bytes))
        db.add(record)
        db.flush()
        task.file_record_id = record.id
        task.status, task.progress = "completed", 100
        db.commit()
    except Exception as exc:  # noqa: BLE001 — รายงานให้ผู้ใช้เห็นในหน้าสแกน
        db.rollback()
        task = db.query(ConversionTask).filter(ConversionTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error_message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            db.commit()
        if not isinstance(exc, (PDFError, HTTPException)):
            logger.exception("scan task %s ล้มเหลว", task_id)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        db.close()


@router.post("/scan")
async def create_scan(
    background_tasks: BackgroundTasks,
    filename: str = Form(...),
    pages: list[UploadFile] = File(...),
    # ภาพเทาสำหรับอ่านข้อความ (ไม่บังคับ) เรียงตามหน้า — ไฟล์ชื่อ ocr-NNN.* ระบุหน้าที่ (เริ่ม 1) หน้าที่ไม่มีใช้ภาพหน้าเอง
    ocr_pages: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not pages:
        raise HTTPException(status_code=400, detail="ไม่มีภาพสแกน")
    if len(pages) > pdf_service.SCAN_MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"สแกนได้ไม่เกิน {pdf_service.SCAN_MAX_PAGES} หน้าต่อไฟล์")
    contents = []
    for page in pages:
        data = await page.read()
        try:
            pdf_service.check_scan_image(data)
        except PDFError as exc:
            raise HTTPException(status_code=400, detail=f"หน้า {len(contents) + 1}: {exc}")
        contents.append(data)
    ocr_contents: dict[int, bytes] = {}
    for up in ocr_pages or []:
        m = re.match(r"ocr-(\d+)", up.filename or "")
        if not m or not (1 <= int(m.group(1)) <= len(contents)):
            continue
        data = await up.read()
        try:
            pdf_service.check_scan_image(data)
        except PDFError:
            continue      # ภาพสำหรับอ่านข้อความเสริมเท่านั้น — เสียก็ใช้ภาพหน้าแทน
        ocr_contents[int(m.group(1)) - 1] = data
    check_storage_quota(db, current_user, sum(len(c) for c in contents))

    task_id = str(uuid.uuid4())
    folder = _scan_dir(task_id)
    folder.mkdir(parents=True, exist_ok=True)
    for i, data in enumerate(contents):
        (folder / f"{i:03d}.img").write_bytes(data)
    for i, data in ocr_contents.items():
        (folder / f"{i:03d}.ocr").write_bytes(data)
    db.add(ConversionTask(id=task_id, user_id=current_user.id, status="pending", progress=0))
    db.commit()
    background_tasks.add_task(process_scan_task, task_id, clean_scan_filename(filename))
    return {"task_id": task_id, "pages": len(contents)}


@router.get("/scan/status/{task_id}")
def scan_status(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    task = db.query(ConversionTask).filter(ConversionTask.id == task_id, ConversionTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="ไม่พบงานสแกน")
    file = None
    if task.status == "completed" and task.file_record_id:
        record = db.query(FileRecord).filter(FileRecord.id == task.file_record_id).first()
        if record:
            file = {"id": record.id, "filename": record.filename, "session_id": record.storage_path,
                    "file_size": record.file_size}
    return {"task_id": task.id, "status": task.status, "progress": task.progress,
            "error_message": task.error_message, "file": file}
