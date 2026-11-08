"""เปรียบเทียบเอกสาร PDF — สร้างงานเทียบ (เบื้องหลัง) · ดูสถานะ/ผล · ภาพหน้าของแต่ละฝั่ง · รายงาน PDF

แต่ละฝั่ง (A = เดิม, B = ใหม่) มาจาก 1 ใน:
- ไฟล์ในบัญชี: {side}_file_id (+ {side}_version = "current" | "previous" = เวอร์ชันก่อนบันทึกครั้งล่าสุด)
- เอกสารที่เปิดใน Editor: {side}_session_id (รวมการแก้ไขที่ยังไม่บันทึก) · + {side}_version = "saved" ไฟล์ที่บันทึกไว้
  หรือ "previous" เวอร์ชันก่อนหน้าของไฟล์นั้น
- อัปโหลดไฟล์: {side}_upload
ไฟล์ทั้งสองถูกคัดลอกไว้ใน WORKING_DIR/compare_<id>/ (เก็บ 24 ชม. — ดู cleanup_old_tasks) ผลเก็บเป็น result.json
"""
from __future__ import annotations

import io
import json
import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import quote

import fitz
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from app.api.deps import ensure_session_owner, get_current_active_user
from app.core.config import settings
from app.core.heavy import ServerBusyError, heavy_slot
from app.core.session import session_manager
from app.db.database import get_db
from app.models.domain import ConversionTask, FileRecord, User
from app.services import file_storage
from app.services.compare_service import CompareError, Options, compare_documents
from app.services.compare_service.report import build_report

logger = logging.getLogger("compare")
router = APIRouter(prefix="/compare", tags=["compare"])

MAX_UPLOAD = 60 * 1024 * 1024
KEEP_HOURS = 24


def task_dir(task_id: str) -> Path:
    return settings.WORKING_DIR / f"compare_{task_id}"


async def _load_side(side: str, file_id: Optional[int], version: str, session_id: Optional[str],
                     upload: Optional[UploadFile], db: Session, user: User) -> tuple[bytes, str]:
    label = "ไฟล์เดิม" if side == "a" else "ไฟล์ใหม่"
    given = sum(x is not None for x in (file_id, session_id, upload))
    if given != 1:
        raise HTTPException(status_code=400, detail=f"เลือก{label}ให้ครบ (ไฟล์ในบัญชี เอกสารที่เปิดอยู่ หรืออัปโหลด อย่างใดอย่างหนึ่ง)")
    if upload is not None:
        data = await upload.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(status_code=413, detail=f"{label}ใหญ่เกิน {MAX_UPLOAD // (1024 * 1024)}MB")
        return data, upload.filename or f"{label}.pdf"
    if session_id is not None and version in ("saved", "previous"):
        # ไฟล์ที่บันทึกไว้ / เวอร์ชันก่อนหน้า ของเอกสารที่เปิดใน Editor
        record = db.query(FileRecord).filter(FileRecord.storage_path == session_id, FileRecord.user_id == user.id).first()
        if record is None:
            raise HTTPException(status_code=404, detail="เอกสารนี้ยังไม่ได้บันทึกไว้ในเอกสารของฉัน")
        file_id, session_id = record.id, None
    if session_id is not None:
        session = session_manager.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="เอกสารที่เปิดอยู่หมดอายุแล้ว — เปิดไฟล์ใหม่อีกครั้ง")
        ensure_session_owner(session, user, db)
        with session.lock:
            if session.doc is None or session.doc.needs_pass:
                raise HTTPException(status_code=400, detail="ปลดล็อกเอกสารก่อนเปรียบเทียบ")
            data = session.doc.tobytes(garbage=0)
        record = db.query(FileRecord).filter(FileRecord.storage_path == session_id, FileRecord.user_id == user.id).first()
        name = (record.filename if record else session.filename) or "เอกสาร.pdf"
        return data, f"{name} (กำลังแก้ไข)"
    record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == user.id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ หรือคุณไม่มีสิทธิ์เข้าถึง")
    if version == "previous":
        path = file_storage.resolve_previous_pdf(record)
        if path is None:
            raise HTTPException(status_code=404, detail="ไฟล์นี้ยังไม่มีเวอร์ชันก่อนหน้า (มีหลังกดบันทึกทับอย่างน้อย 1 ครั้ง)")
        return path.read_bytes(), f"{record.filename} (เวอร์ชันก่อนหน้า)"
    path = file_storage.resolve_stored_pdf(record)
    if path is None:
        raise HTTPException(status_code=404, detail="ไฟล์เอกสารถูกลบออกจากระบบแล้ว")
    return path.read_bytes(), record.filename


def _open_checked(data: bytes, label: str) -> fitz.Document:
    try:
        doc = fitz.open("pdf", data)
    except Exception:
        raise HTTPException(status_code=400, detail=f"{label}ไม่ใช่ไฟล์ PDF ที่เปิดได้")
    if doc.needs_pass:
        raise HTTPException(status_code=400, detail=f"{label}มีรหัสผ่าน — ปลดล็อก (บันทึกแบบไม่มีรหัส) ก่อนเปรียบเทียบ")
    if doc.page_count == 0:
        raise HTTPException(status_code=400, detail=f"{label}ไม่มีหน้า")
    return doc


def process_compare_task(task_id: str) -> None:
    from app.db.database import SessionLocal

    folder = task_dir(task_id)
    db = SessionLocal()
    try:
        task = db.query(ConversionTask).filter(ConversionTask.id == task_id).first()
        if not task:
            return
        meta = json.loads((folder / "meta.json").read_text())
        task.status, task.progress = "processing", 1
        db.commit()
        last = [0.0]

        def progress(pct: int, message: str) -> None:
            now = time.monotonic()
            if pct < 100 and now - last[0] < 0.7:
                return
            last[0] = now
            task.progress = max(1, min(99, pct))
            (folder / "stage.txt").write_text(message)
            db.commit()

        opts = Options(**meta["options"])
        # ทั้งงานนับเป็นงานหนัก 1 ช่อง (เรนเดอร์/ตัดคำ/difflib กิน CPU) — OCR ข้างในใช้ช่องเดียวกัน
        with heavy_slot("compare"), fitz.open(folder / "a.pdf") as doc_a, fitz.open(folder / "b.pdf") as doc_b:
            result = compare_documents(doc_a, doc_b, opts, progress)
        (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False))
        task.result_file_path = str(folder / "result.json")
        task.status, task.progress = "completed", 100
        db.commit()
    except Exception as exc:  # noqa: BLE001 — แสดงในหน้าเปรียบเทียบ
        db.rollback()
        task = db.query(ConversionTask).filter(ConversionTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error_message = str(exc) if isinstance(exc, (CompareError, ServerBusyError)) else "เปรียบเทียบไม่สำเร็จ — ลองใหม่อีกครั้ง"
            db.commit()
        if not isinstance(exc, (CompareError, ServerBusyError)):
            logger.exception("compare task %s ล้มเหลว", task_id)
    finally:
        db.close()


@router.post("")
async def create_compare(
    background_tasks: BackgroundTasks,
    a_file_id: Optional[int] = Form(None), a_version: Literal["current", "previous", "saved"] = Form("current"),
    a_session_id: Optional[str] = Form(None), a_upload: Optional[UploadFile] = File(None),
    b_file_id: Optional[int] = Form(None), b_version: Literal["current", "previous", "saved"] = Form("current"),
    b_session_id: Optional[str] = Form(None), b_upload: Optional[UploadFile] = File(None),
    text: bool = Form(True), visual: bool = Form(True), ocr: bool = Form(True),
    ignore_case: bool = Form(False), ignore_punctuation: bool = Form(False),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    data_a, name_a = await _load_side("a", a_file_id, a_version, a_session_id, a_upload, db, current_user)
    data_b, name_b = await _load_side("b", b_file_id, b_version, b_session_id, b_upload, db, current_user)
    doc_a, doc_b = _open_checked(data_a, "ไฟล์เดิม"), _open_checked(data_b, "ไฟล์ใหม่")
    pages = (doc_a.page_count, doc_b.page_count)
    doc_a.close()
    doc_b.close()
    from app.services.compare_service.engine import MAX_PAGES

    if max(pages) > MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"เปรียบเทียบได้ไม่เกิน {MAX_PAGES} หน้าต่อไฟล์")

    task_id = str(uuid.uuid4())
    folder = task_dir(task_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "a.pdf").write_bytes(data_a)
    (folder / "b.pdf").write_bytes(data_b)
    meta = {"user_id": current_user.id, "name_a": name_a, "name_b": name_b,
            "options": {"text": text, "visual": visual, "ocr": ocr, "ignore_case": ignore_case,
                        "ignore_punctuation": ignore_punctuation}}
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    db.add(ConversionTask(id=task_id, user_id=current_user.id, status="pending", progress=0))
    db.commit()
    background_tasks.add_task(process_compare_task, task_id)
    return {"task_id": task_id, "name_a": name_a, "name_b": name_b, "pages_a": pages[0], "pages_b": pages[1]}


def _owned_task(task_id: str, db: Session, user: User) -> tuple[ConversionTask, Path, dict]:
    task = db.query(ConversionTask).filter(ConversionTask.id == task_id, ConversionTask.user_id == user.id).first()
    folder = task_dir(task_id)
    if task is None or not (folder / "meta.json").exists():
        raise HTTPException(status_code=404, detail="ไม่พบผลเปรียบเทียบ (เก็บไว้ 24 ชั่วโมง) — เปรียบเทียบใหม่อีกครั้ง")
    return task, folder, json.loads((folder / "meta.json").read_text())


@router.get("/{task_id}")
def compare_status(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    task, folder, meta = _owned_task(task_id, db, current_user)
    body = {"task_id": task_id, "status": task.status, "progress": task.progress, "error_message": task.error_message,
            "name_a": meta["name_a"], "name_b": meta["name_b"], "options": meta["options"],
            "stage": (folder / "stage.txt").read_text() if (folder / "stage.txt").exists() else None}
    if task.status == "completed" and (folder / "result.json").exists():
        body["result"] = json.loads((folder / "result.json").read_text())
    return body


@router.get("/{task_id}/page/{side}/{page_number}")
def compare_page(task_id: str, side: Literal["a", "b"], page_number: int, zoom: float = 1.5,
                 db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """ภาพหน้าของฝั่ง A/B (JPEG) — cache ในเบราว์เซอร์ได้ เพราะไฟล์ของงานเทียบไม่เปลี่ยน"""
    _, folder, _ = _owned_task(task_id, db, current_user)
    zoom = max(0.25, min(zoom, 4.0))
    cache = folder / f"{side}-{page_number}-{zoom:.2f}.jpg"
    if not cache.exists():
        with fitz.open(folder / f"{side}.pdf") as doc:
            if not 0 <= page_number < doc.page_count:
                raise HTTPException(status_code=404, detail="ไม่พบหน้านี้")
            pix = doc[page_number].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85, subsampling=0)
            cache.write_bytes(buf.getvalue())
    return Response(cache.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{task_id}/report")
def compare_report(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    task, folder, meta = _owned_task(task_id, db, current_user)
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="ยังเปรียบเทียบไม่เสร็จ")
    out = folder / "report.pdf"
    if not out.exists():
        result = json.loads((folder / "result.json").read_text())
        with heavy_slot("compare-report"), fitz.open(folder / "a.pdf") as a, fitz.open(folder / "b.pdf") as b:
            out.write_bytes(build_report(a, b, result, meta["name_a"], meta["name_b"]))
    stem_a = Path(meta["name_a"]).stem[:40]
    stem_b = Path(meta["name_b"]).stem[:40]
    name = f"เปรียบเทียบ {stem_a} กับ {stem_b}.pdf"
    return Response(out.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
                             "Access-Control-Expose-Headers": "Content-Disposition"})


@router.delete("/{task_id}")
def delete_compare(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    task, folder, _ = _owned_task(task_id, db, current_user)
    shutil.rmtree(folder, ignore_errors=True)
    db.delete(task)
    db.commit()
    return {"status": "ok"}


def cleanup_old_tasks(max_age_hours: float = KEEP_HOURS) -> int:
    """ลบโฟลเดอร์งานเทียบที่เก่ากว่ากำหนด (เรียกจากงานเก็บกวาดเบื้องหลังใน main.py)"""
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for folder in settings.WORKING_DIR.glob("compare_*"):
        try:
            if folder.is_dir() and folder.stat().st_mtime < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
