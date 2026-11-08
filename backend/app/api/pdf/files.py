"""ไฟล์ของผู้ใช้ (Dashboard) และการสร้าง/บันทึก session — /pdf/files, /pdf/upload, /pdf/{id}/open ฯลฯ"""
import logging
import re
import os
import shutil
import uuid
from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.heavy import ServerBusyError
from app.api.deps import ensure_session_owner, get_current_active_user, get_owned_session
from app.core.config import settings
from app.core.session import PDFSession, session_manager
from app.db.database import get_db
from app.models.domain import ConversionTask, FileRecord, PlanConfig, User
from app.models.schemas import DocumentPropertiesResponse, PageNumberRequest, UploadResponse, WatermarkRequest
from app.services import edit_service, file_storage, pdf_service
from app.services.pdf_service import PDFError
from app.services.pdf_service.core import has_digital_signatures
from app.services.convert_service import convert_office_to_pdf_bytes

logger = logging.getLogger("routes.pdf.files")
router = APIRouter()


class SaveAsCopyRequest(BaseModel):
    filename: str = Field(max_length=300)
    # None = ไม่เปลี่ยนเวอร์ชัน (เหมือนเดิม) — ระบุแล้วไฟล์ใหม่ตรงมาตรฐาน PDF เวอร์ชันนั้น (ดู pdf_service.version)
    pdf_version: Optional[Literal["1.4", "1.5", "1.6", "1.7", "2.0", "pdfa-1b", "pdfa-2b", "pdfa-3b"]] = None


class RenameFileRequest(BaseModel):
    filename: str = Field(max_length=300)


def _storage_limit_bytes(db: Session, user: User) -> int:
    plan_config = db.query(PlanConfig).filter(PlanConfig.plan_type == user.plan_type).first()
    max_mb = (plan_config.max_storage_mb if plan_config else None) or settings.DEFAULT_STORAGE_MB
    return max_mb * 1024 * 1024


def check_storage_quota(db: Session, user: User, new_file_size: int = 0, replacing_file_size: int = 0):
    files = db.query(FileRecord).filter(FileRecord.user_id == user.id).all()
    used_bytes = sum((f.file_size or 0) for f in files)
    projected_bytes = used_bytes - replacing_file_size + new_file_size
    if projected_bytes > _storage_limit_bytes(db, user):
        raise HTTPException(status_code=403, detail="พื้นที่เก็บข้อมูลของคุณเต็มแล้ว กรุณาอัปเกรดแพ็กเกจหรือลบไฟล์ที่ไม่ใช้งาน")


def _page_count_of(path: Path) -> int:
    try:
        with fitz.open(path) as doc:
            return doc.page_count
    except ServerBusyError:
        raise
    except Exception:
        return 1


def _iso(dt):
    return dt.isoformat() if dt else None


@router.get("/files")
def get_my_files(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    files = (
        db.query(FileRecord)
        .filter(FileRecord.user_id == current_user.id)
        .order_by(FileRecord.updated_at.desc(), FileRecord.created_at.desc())
        .all()
    )
    used_bytes = sum((f.file_size or 0) for f in files)
    return {
        "files": [
            {
                "id": f.id,
                "filename": f.filename,
                "session_id": f.storage_path,
                "created_at": _iso(f.created_at),
                "updated_at": _iso(getattr(f, "updated_at", None)) or _iso(f.created_at),
                "file_size": f.file_size or 0,
                # มีเวอร์ชันก่อนบันทึกครั้งล่าสุด → "เทียบกับเวอร์ชันก่อนหน้า" ได้
                "has_previous_version": file_storage.resolve_previous_pdf(f) is not None,
            }
            for f in files
        ],
        "quota": {"used": used_bytes, "limit": _storage_limit_bytes(db, current_user)},
    }


@router.post("/{session_id}/open")
def open_existing_file(session_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    file_record = db.query(FileRecord).filter(FileRecord.storage_path == session_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ หรือคุณไม่มีสิทธิ์เข้าถึง")

    session = session_manager.get(session_id)
    if session:
        ensure_session_owner(session, current_user, db)
        status = "password_required" if pdf_service.is_locked(session) else "ok"
        return {"session_id": session_id, "filename": file_record.filename, "status": status}

    pdf_path = file_storage.resolve_stored_pdf(file_record)  # เวอร์ชันที่บันทึกล่าสุด
    if pdf_path is None:
        raise HTTPException(status_code=404, detail="ไฟล์เอกสารถูกลบออกจากระบบแล้ว (หมดอายุ)")

    try:
        content = pdf_path.read_bytes()
        new_session, needs_password = pdf_service.create_session_from_upload(
            content, file_record.filename, user_id=current_user.id
        )
        old_storage = file_record.storage_path
        file_record.storage_path = new_session.session_id
        db.commit()
        file_storage.move_previous_version(old_storage, new_session.session_id)
        # สำเนาชุดเดิมไม่มีใครใช้แล้ว (เนื้อหาล่าสุดถูกคัดลอกเป็นชุดใหม่) — เดิมค้างบนดิสก์ทุกครั้งที่เปิดไฟล์
        file_storage.remove_stored_copies(old_storage, file_record.filename, file_record.original_filename)
        return {
            "session_id": new_session.session_id,
            "filename": file_record.filename,
            "status": "password_required" if needs_password else "ok",
        }
    except ServerBusyError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการโหลดไฟล์: {exc}")


OFFICE_EXTS = (".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".rtf", ".odt", ".ods", ".odp")
IMAGE_EXTS = (".png", ".jpg", ".jpeg")


async def _to_pdf(content: bytes, filename: str, user: User) -> tuple[bytes, str]:
    """ไฟล์ที่อัปโหลด → (PDF, ชื่อไฟล์ .pdf) — Office แปลงด้วย LibreOffice, รูปภาพทำ OCR ให้ค้นหาข้อความได้"""
    lower = filename.lower()
    pdf_name = os.path.splitext(filename)[0] + ".pdf"
    if lower.endswith(OFFICE_EXTS):
        try:
            return await convert_office_to_pdf_bytes(content, filename, user_id=user.id), pdf_name
        except HTTPException:
            raise
        except ServerBusyError:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"แปลงไฟล์ Office เป็น PDF ล้มเหลว: {e}")
    if lower.endswith(IMAGE_EXTS):
        try:
            # ชั้นข้อความ OCR แบบเดียวกับเมนู "อ่านข้อความในรูปภาพ" (แม่นกว่า PDF ของ tesseract เองกับภาษาไทย)
            return await run_in_threadpool(pdf_service.image_to_searchable_pdf, content), pdf_name
        except ServerBusyError:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"แปลงรูปภาพเป็น PDF ล้มเหลว: {e}")
    return content, filename


async def _store_upload(content: bytes, filename: str, db: Session, user: User) -> UploadResponse:
    """อัปโหลด (PDF / รูปภาพ / Office) → แปลงเป็น PDF → บันทึกเป็นไฟล์ PDF ในเอกสารของฉัน + เปิด session
    ใช้ร่วมกันทั้งปุ่มอัปโหลดใน Dashboard และเมนูสร้าง PDF จากไฟล์ Office ใน Editor"""
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="ไฟล์ใหญ่เกินขนาดที่กำหนด")
    check_storage_quota(db, user, len(content))
    pdf_bytes, final_filename = await _to_pdf(content, filename, user)
    # ชื่อไฟล์จากเครื่องผู้ใช้: ตัด path (Windows ส่ง "C:\\fakepath\\…" ได้) อักขระที่ใช้ไม่ได้ และความยาว
    # (เดิมเก็บตามที่ส่งมา — ชื่อแบบนี้ดาวน์โหลดแล้วได้ชื่อแปลก/สร้างโฟลเดอร์ซ้อน)
    base = re.split(r"[\\/]", final_filename or "")[-1]
    try:
        final_filename = clean_pdf_stem(base) + ".pdf"
    except HTTPException:
        final_filename = "document.pdf"
    if pdf_bytes is not content:
        check_storage_quota(db, user, len(pdf_bytes))   # ขนาดที่เก็บจริงคือ PDF ที่แปลงแล้ว
    return _store_pdf(pdf_bytes, final_filename, db, user)


def _store_pdf(pdf_bytes: bytes, final_filename: str, db: Session, user: User) -> UploadResponse:
    """PDF ที่พร้อมแล้ว → เปิด session + บันทึกเป็นไฟล์ในเอกสารของฉัน (ตรวจโควต้าก่อนเรียก)"""
    try:
        session, needs_password = pdf_service.create_session_from_upload(pdf_bytes, final_filename, user_id=user.id)
    except ServerBusyError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"เปิดไฟล์ PDF ไม่สำเร็จ: {exc}")

    db.add(FileRecord(
        user_id=user.id,
        filename=final_filename,
        original_filename=final_filename,  # ชื่อต้นฉบับบน disk (ไม่เปลี่ยนแม้จะ rename)
        storage_path=session.session_id,
        file_size=len(pdf_bytes),
    ))
    db.commit()

    if needs_password:
        return UploadResponse(session_id=session.session_id, filename=session.original_filename, status="password_required")
    with session.lock:
        page_count = pdf_service.get_page_count(session)
        session.push_history()  # baseline แรกของ undo/redo stack (ดู app/core/session.py)
    return UploadResponse(
        session_id=session.session_id,
        filename=session.original_filename,
        status="ok",
        page_count=page_count,
    )


@router.post("/convert-office", response_model=UploadResponse)
async def convert_office(file: UploadFile = File(...), db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_active_user)):
    """เมนูสร้าง PDF จากไฟล์ Office (Editor) — แปลงแล้วบันทึกเป็น PDF ในเอกสารของฉัน (วิธีเดียวกับ /upload)"""
    if not file.filename.lower().endswith(OFFICE_EXTS):
        raise HTTPException(status_code=400, detail="รูปแบบไฟล์ไม่รองรับ รองรับเฉพาะไฟล์ Office")
    return await _store_upload(await file.read(), file.filename, db, current_user)


def _merged_filename(db: Session, user_id: int, first_name: str, count: int) -> str:
    """ชื่อไฟล์ที่รวมแล้ว: "<ชื่อไฟล์แรก> (รวม N ไฟล์).pdf" — ซ้ำกับไฟล์ที่มีอยู่ เติม (2), (3) ..."""
    stem = (Path(first_name).stem or "Merged")[:120]
    return _unique_filename(db, user_id, f"{stem} (รวม {count} ไฟล์)")


_BAD_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')
FILENAME_STEM_MAX = 150


def clean_pdf_stem(name: str) -> str:
    """ชื่อไฟล์ที่ผู้ใช้พิมพ์ → stem ที่ปลอดภัย: ตัดอักขระที่ใช้ไม่ได้ในชื่อไฟล์ (/ \\ : * ? " < > | และอักขระควบคุม
    — เดิมเก็บตามที่พิมพ์ ดาวน์โหลดแล้วได้ชื่อแปลก/โฟลเดอร์ซ้อน) ตัด .pdf ท้าย จำกัดความยาว · ว่าง → 400"""
    stem = _BAD_NAME_CHARS.sub(" ", name or "")
    stem = re.sub(r"\s+", " ", stem).strip().strip(".")
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4].rstrip(" .")
    stem = stem[:FILENAME_STEM_MAX].strip()
    if not stem:
        raise HTTPException(status_code=400, detail="กรุณาตั้งชื่อไฟล์")
    return stem


def _unique_filename(db: Session, user_id: int, base: str) -> str:
    """"<base>.pdf" ที่ไม่ซ้ำกับไฟล์ของผู้ใช้ — ซ้ำ เติม (2), (3) ..."""
    existing = {f for (f,) in db.query(FileRecord.filename).filter(FileRecord.user_id == user_id).all()}
    name, n = f"{base}.pdf", 2
    while name in existing:
        name, n = f"{base} ({n}).pdf", n + 1
    return name


@router.post("/merge", response_model=UploadResponse)
async def merge_pdf_files(
    files: list[UploadFile] = File(default=[]),
    file_ids: str = Form(""),
    order: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """รวม PDF หลายไฟล์ → บันทึกเป็นไฟล์ใหม่ในเอกสารของฉัน แล้วเปิด session
    files    : ไฟล์จากเครื่องผู้ใช้
    file_ids : id ของไฟล์ในเอกสารของฉัน คั่นด้วยจุลภาค ("12,15")
    order    : ลำดับการรวม เช่น "u0,f12,u1" (u = ไฟล์อัปโหลดลำดับที่, f = id ไฟล์) — ว่าง = ไฟล์อัปโหลดก่อน ตามด้วยไฟล์ในเอกสารของฉัน"""
    uploads: list[tuple[str, bytes]] = []
    total = 0
    for f in files:
        if not (f.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"ไฟล์ {f.filename} ไม่ใช่ PDF")
        data = await f.read()
        if len(data) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"ไฟล์ {f.filename} ใหญ่เกินขนาดที่กำหนด")
        total += len(data)
        uploads.append((f.filename, data))
    stored: dict[int, tuple[str, bytes]] = {}
    try:
        ids = [int(x) for x in file_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="file_ids ไม่ถูกต้อง")
    for fid in ids:
        if fid in stored:
            continue
        record = db.query(FileRecord).filter(FileRecord.id == fid, FileRecord.user_id == current_user.id).first()
        path = file_storage.resolve_stored_pdf(record) if record else None
        if not path:
            raise HTTPException(status_code=404, detail="ไม่พบไฟล์ที่เลือกในเอกสารของฉัน")
        data = path.read_bytes()
        total += len(data)
        stored[fid] = (record.filename, data)
    if order.strip():
        seq = []
        for tok in order.split(","):
            tok = tok.strip()
            try:
                if tok.startswith("u"):
                    seq.append(uploads[int(tok[1:])])
                elif tok.startswith("f"):
                    seq.append(stored[int(tok[1:])])
                else:
                    raise ValueError
            except (ValueError, IndexError, KeyError):
                raise HTTPException(status_code=400, detail="ลำดับไฟล์ (order) ไม่ถูกต้อง")
    else:
        seq = uploads + [stored[i] for i in ids if i in stored]
    if len(seq) < 2:
        raise HTTPException(status_code=400, detail="ต้องมีไฟล์อย่างน้อย 2 ไฟล์สำหรับรวม")
    if len(seq) > pdf_service.MERGE_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"รวมได้ครั้งละไม่เกิน {pdf_service.MERGE_MAX_FILES} ไฟล์")
    if total > settings.MAX_MERGE_TOTAL:
        raise HTTPException(status_code=413, detail=f"ไฟล์รวมกันใหญ่เกิน {settings.MAX_MERGE_TOTAL // (1024 * 1024)} MB")
    filename = _merged_filename(db, current_user.id, seq[0][0], len(seq))
    try:
        merged, _pages = await run_in_threadpool(pdf_service.merge_pdf_bytes, [d for _, d in seq], [n for n, _ in seq],
                                                 filename[:-4])
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ServerBusyError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("รวมไฟล์ไม่สำเร็จ")
        raise HTTPException(status_code=400, detail=f"รวมไฟล์ไม่สำเร็จ: {exc}")
    check_storage_quota(db, current_user, len(merged))
    return _store_pdf(merged, filename, db, current_user)


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """อัปโหลดจาก Dashboard: PDF, รูปภาพ (OCR ให้ค้นหาได้) หรือไฟล์ Office (แปลงเป็น PDF) — เก็บเป็น PDF เสมอ"""
    if not file.filename.lower().endswith((".pdf",) + IMAGE_EXTS + OFFICE_EXTS):
        raise HTTPException(status_code=400,
                            detail="รองรับเฉพาะไฟล์ PDF, รูปภาพ (.png, .jpg) หรือไฟล์ Office (Word, Excel, PowerPoint)")
    return await _store_upload(await file.read(), file.filename, db, current_user)


@router.post("/{session_id}/save-as-copy")
def save_as_copy(
    session_id: str,
    payload: SaveAsCopyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    session: PDFSession = Depends(get_owned_session),
):
    file_record = db.query(FileRecord).filter(FileRecord.storage_path == session_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ต้นฉบับ")
    try:
        with session.lock:
            report = None
            if payload.pdf_version and payload.pdf_version.startswith("pdfa-"):
                path, report = pdf_service.export_pdfa(session, payload.pdf_version)
            elif payload.pdf_version:
                path, report = pdf_service.export_pdf_version(session, payload.pdf_version)
            else:
                path = pdf_service.get_download_path(session)
            new_size = path.stat().st_size
            try:
                check_storage_quota(db, current_user, new_size, 0)
            except HTTPException:
                if path != session.working_path:
                    path.unlink(missing_ok=True)
                raise

            new_session_id = uuid.uuid4().hex
            # ชื่อซ้ำกับไฟล์ที่มีอยู่ เติม (2), (3) — เดิมได้สองไฟล์ชื่อเดียวกันในเอกสารของฉัน แยกไม่ออก
            new_filename = _unique_filename(db, current_user.id, clean_pdf_stem(payload.filename))
            shutil.copy2(path, file_storage.upload_path(new_session_id))
            if path != session.working_path:
                path.unlink(missing_ok=True)

            new_record = FileRecord(
                user_id=current_user.id,
                filename=new_filename,
                storage_path=new_session_id,
                file_size=new_size,
            )
            db.add(new_record)
            db.commit()
            return {"status": "ok", "new_id": new_record.id, "new_session_id": new_session_id, "version": report}
    except HTTPException:
        raise
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ServerBusyError:
        raise
    except Exception as e:
        logger.exception("save-as-copy ล้มเหลว session=%s", session_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/save")
def save_to_server(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    session: PDFSession = Depends(get_owned_session),
):
    file_record = db.query(FileRecord).filter(FileRecord.storage_path == session_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ หรือคุณไม่มีสิทธิ์เข้าถึง")
    try:
        with session.lock:
            # get_download_path จะ flush การแก้ไขล่าสุด และใส่รหัสผ่านถ้าตั้งไว้
            path = pdf_service.get_download_path(session)
            check_storage_quota(db, current_user, path.stat().st_size, file_record.file_size or 0)

            target = file_storage.saved_path(session_id)
            file_storage.keep_previous_version(file_record)  # "เทียบกับเวอร์ชันก่อนหน้า"
            shutil.copy2(path, target)
            file_record.file_size = target.stat().st_size
            db.commit()

            if path != session.working_path:  # ไฟล์ temp ที่เข้ารหัสแล้ว
                path.unlink(missing_ok=True)
            return {"status": "ok", "file_size": file_record.file_size}
    except HTTPException:
        raise
    except ServerBusyError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/files/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ หรือคุณไม่มีสิทธิ์ลบไฟล์นี้")

    session_id = file_record.storage_path
    for p in file_storage.all_existing_paths(file_record):
        try:
            p.unlink(missing_ok=True)
        except ServerBusyError:
            raise
        except Exception as e:
            logger.warning("ลบไฟล์ %s ไม่สำเร็จ: %s", p, e)

    session_manager.close(session_id)

    # ลบ Conversion Tasks ที่อ้างถึงไฟล์นี้ก่อน (กัน Foreign Key constraint)
    for task in db.query(ConversionTask).filter(ConversionTask.file_record_id == file_id).all():
        if task.result_file_path and os.path.exists(task.result_file_path):
            try:
                os.remove(task.result_file_path)
            except ServerBusyError:
                raise
            except Exception as e:
                logger.warning("ลบไฟล์ DOCX %s ไม่สำเร็จ: %s", task.result_file_path, e)
        db.delete(task)

    db.delete(file_record)
    db.commit()
    return {"msg": "ลบไฟล์สำเร็จ"}


@router.get("/files/{file_id}/signature-status")
def file_signature_status(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """ไฟล์นี้มีลายเซ็นดิจิทัลแล้วหรือยัง — Dashboard ใช้เตือนก่อนใส่ลายน้ำ/เซ็นเซอร์ (แก้แล้วลายเซ็นจะไม่ถูกต้อง)

    ตรวจแค่ "มีลายเซ็นฝังอยู่" (ไม่ validate) จึงเร็ว · ไฟล์ที่มีรหัสผ่านอ่านไม่ได้ → signed=None (ไม่ทราบ)"""
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
    path = file_storage.resolve_stored_pdf(file_record)
    if path is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์บนเซิร์ฟเวอร์")
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader

        with open(path, "rb") as fh:
            reader = PdfFileReader(fh, strict=False)
            if reader.encrypted:
                return {"signed": None, "count": 0, "pdfa": None}
            count = len(reader.embedded_signatures)
    except ServerBusyError:
        raise
    except Exception as exc:  # ไฟล์เสีย/อ่านไม่ได้ — ไม่ขวางการใช้งาน
        logger.warning("ตรวจลายเซ็นไฟล์ %s ไม่สำเร็จ: %s", file_id, exc)
        return {"signed": None, "count": 0, "pdfa": None}
    # pdfa: ไฟล์ประกาศว่าเป็น PDF/A (เช่น "PDF/A-2b") — เครื่องมือด่วนเข้ารหัสใช้เตือน (PDF/A ห้ามเข้ารหัส)
    return {"signed": count > 0, "count": count, "pdfa": pdf_service.pdfa_claim_of(path)}


class QuickActionRequest(BaseModel):
    """ใส่ลายน้ำ / เซ็นเซอร์ด้วยคำค้นหา จาก Dashboard โดยไม่ต้องเปิดไฟล์ใน Editor"""
    action: Literal["watermark", "redact_search", "encrypt", "pdpa", "compress", "page_numbers"]
    watermark: Optional[WatermarkRequest] = None
    page_numbers: Optional[PageNumberRequest] = None  # action=page_numbers
    keyword: Optional[str] = Field(default=None, max_length=500)
    is_regex: bool = False
    match_case: bool = False
    password: Optional[str] = None  # รหัสผ่านปัจจุบันของไฟล์ (ถ้ามี)
    new_password: Optional[str] = Field(default=None, max_length=128)  # action=encrypt
    encryption: Literal["aes256", "aes128"] = "aes256"  # action=encrypt (ดู pdf_service.encrypt_pdf_file)
    pii_ids: list[str] = Field(default_factory=list, max_length=5000)  # action=pdpa (id จาก /pii-scan)
    clean_metadata: bool = False  # action=pdpa
    compress_profile: Literal["screen", "ebook", "printer"] = "screen"  # action=compress


_QUICK_SUFFIX = {"page_numbers": "เลขหน้า", "watermark": "ลายน้ำ", "redact_search": "เซ็นเซอร์", "encrypt": "เข้ารหัส", "pdpa": "PDPA", "compress": "ลดขนาด"}


def _owned_record(db: Session, user: User, file_id: int) -> FileRecord:
    record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == user.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
    return record


def _open_temp_session(record: FileRecord, user: User, password: Optional[str]):
    """เปิดไฟล์ที่บันทึกไว้ใน session ชั่วคราวแยกต่างหาก (ไม่ใช่ session ที่ผู้ใช้อาจเปิดค้างใน Editor)
    ไฟล์มีรหัสผ่าน: ไม่ส่ง/ผิด → 423 · ผู้เรียกต้องปิดด้วย _close_temp_session เสมอ"""
    source = file_storage.resolve_stored_pdf(record)
    if source is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์บนเซิร์ฟเวอร์")
    session, needs_password = pdf_service.create_session_from_upload(source.read_bytes(), record.filename, user_id=user.id)
    if needs_password:
        ok = bool(password) and pdf_service.unlock(session, password)
        if not ok:
            _close_temp_session(session, keep_file=False)
            raise HTTPException(status_code=423, detail="รหัสผ่านไม่ถูกต้อง" if password else "ไฟล์นี้มีรหัสผ่าน กรุณาใส่รหัสผ่าน")
        session.output_password = password  # ไฟล์ที่ได้ยังมีรหัสผ่านเดิม
    return session


def _close_temp_session(session, keep_file: bool) -> None:
    session_manager.close(session.session_id)  # ลบ working copy
    if not keep_file:
        file_storage.upload_path(session.session_id).unlink(missing_ok=True)


@router.get("/files/{file_id}/download")
def download_stored_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """ดาวน์โหลดไฟล์เวอร์ชันที่บันทึกไว้ (เมนู ☰ บน Dashboard) โดยไม่ต้องเปิด session"""
    record = _owned_record(db, current_user, file_id)
    path = file_storage.resolve_stored_pdf(record)
    if path is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์บนเซิร์ฟเวอร์")
    return FileResponse(path, media_type="application/pdf", filename=record.filename)


class FilePropertiesRequest(BaseModel):
    password: Optional[str] = None


@router.post("/files/{file_id}/properties", response_model=DocumentPropertiesResponse)
def stored_file_properties(
    file_id: int,
    payload: FilePropertiesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """คุณสมบัติเอกสารของไฟล์ที่บันทึกไว้ (เมนู ☰ บน Dashboard) — POST เพื่อไม่ให้รหัสผ่านไปอยู่ใน URL"""
    record = _owned_record(db, current_user, file_id)
    session = _open_temp_session(record, current_user, payload.password)
    try:
        with session.lock:
            data = pdf_service.get_document_properties(session)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        _close_temp_session(session, keep_file=False)
    return DocumentPropertiesResponse(**data)


@router.post("/files/{file_id}/pii-scan")
def stored_file_pii_scan(
    file_id: int,
    payload: FilePropertiesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """ตรวจหาข้อมูลส่วนบุคคลในไฟล์ที่บันทึกไว้ (เครื่องมือด่วนบน Dashboard) — ไม่แก้ไฟล์
    แล้วส่ง id ที่เลือกไปที่ quick-action action=pdpa"""
    record = _owned_record(db, current_user, file_id)
    session = _open_temp_session(record, current_user, payload.password)
    try:
        with session.lock:
            return pdf_service.scan_pii(session)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        _close_temp_session(session, keep_file=False)


@router.post("/files/{file_id}/quick-action")
def quick_action(
    file_id: int,
    payload: QuickActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """ทำงานกับ "สำเนา" ของไฟล์ใน session ชั่วคราวแยกต่างหาก แล้วบันทึกเป็นไฟล์ใหม่ "ชื่อ (ลายน้ำ).pdf"

    ไม่ใช้ session ของไฟล์เดิม — ถ้าผู้ใช้เปิดไฟล์นั้นค้างไว้ใน Editor (มีการแก้ที่ยังไม่ Save) จะไม่ถูกปนเข้ามา
    และไฟล์ต้นฉบับไม่ถูกแตะเลย · ไฟล์ที่มีรหัสผ่าน: ต้องส่ง password มา (ผิด/ไม่ส่ง → 423) ไฟล์ใหม่ใช้รหัสเดิม
    · เซ็นเซอร์แล้วไม่พบคำ → ไม่สร้างไฟล์ คืน status=not_found · encrypt: ไฟล์ใหม่ใช้ new_password (ไฟล์ที่ลงนามแล้ว → 400)
    · compress: เล็กลงไม่ถึง 3% → ไม่สร้างไฟล์ คืน status=no_change · คืน before/after (ไบต์) · ไฟล์ที่ลงนามแล้ว → 400"""
    if payload.action == "watermark" and (payload.watermark is None or not payload.watermark.text.strip()):
        raise HTTPException(status_code=400, detail="กรุณากรอกข้อความลายน้ำ")
    if payload.action == "page_numbers" and payload.page_numbers is None:
        raise HTTPException(status_code=400, detail="กรุณาตั้งค่าเลขหน้า")
    if payload.action == "redact_search" and not (payload.keyword or "").strip():
        raise HTTPException(status_code=400, detail="กรุณากรอกคำที่ต้องการเซ็นเซอร์")
    if payload.action == "encrypt" and not (payload.new_password or "").strip():
        raise HTTPException(status_code=400, detail="กรุณากรอกรหัสผ่านใหม่")
    if payload.action == "pdpa" and not payload.pii_ids and not payload.clean_metadata:
        raise HTTPException(status_code=400, detail="กรุณาเลือกรายการที่ต้องการปกปิด")

    record = _owned_record(db, current_user, file_id)
    session = _open_temp_session(record, current_user, payload.password)
    new_id = session.session_id
    created = False
    try:
        with session.lock:
            count = None
            report = None
            sizes = None
            if payload.action == "compress":
                stored = file_storage.resolve_stored_pdf(record)
                sizes = pdf_service.compress_pdf(session, payload.compress_profile,
                                                 reference_size=stored.stat().st_size if stored else None)
                if sizes is None:
                    return {"status": "no_change"}
            elif payload.action == "watermark":
                wm = payload.watermark
                edit_service.apply_watermark(session, text=wm.text, opacity=wm.opacity, angle=wm.angle,
                                             color=wm.color, font_size=wm.font_size)
            elif payload.action == "page_numbers":
                try:
                    count = edit_service.apply_page_numbers(session, payload.page_numbers.to_options())
                except PDFError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from None
            elif payload.action == "redact_search":
                try:
                    count = pdf_service.redact_by_search(session, payload.keyword.strip(), payload.match_case,
                                                         payload.is_regex)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from None
                if count == -1:
                    raise HTTPException(status_code=400, detail="เซ็นเซอร์ไม่สำเร็จ (ตรวจรูปแบบ regex อีกครั้ง)")
                if count == 0:
                    return {"status": "not_found", "count": 0, "image_pages": pdf_service.pages_with_images(session)}
            elif payload.action == "pdpa":
                try:
                    result = pdf_service.redact_pii(session, payload.pii_ids, payload.clean_metadata)
                except pdf_service.PIIStaleError:
                    raise HTTPException(status_code=409, detail="ไฟล์มีการเปลี่ยนแปลงหลังสแกน กรุณาสแกนใหม่อีกครั้ง")
                count, report = result["redacted"], result["report"]
            else:  # encrypt — เขียนไฟล์ใหม่ทั้งไฟล์ ลายเซ็นดิจิทัลที่มีอยู่จะใช้ไม่ได้ จึงไม่อนุญาต
                if has_digital_signatures(session.doc):
                    raise HTTPException(status_code=400, detail="เอกสารที่ลงนามแล้วเข้ารหัสไม่ได้ เพราะลายเซ็นจะใช้ไม่ได้")
                pdf_service.check_password_for_mode(payload.new_password, payload.encryption)
                session.output_password = payload.new_password
                session.output_encryption = payload.encryption
            path = pdf_service.get_download_path(session)
            data = path.read_bytes()
            if path != session.working_path:
                path.unlink(missing_ok=True)

        check_storage_quota(db, current_user, len(data), 0)
        file_storage.upload_path(new_id).write_bytes(data)
        base = record.filename[:-4] if record.filename.lower().endswith(".pdf") else record.filename
        new_name = _unique_filename(db, current_user.id, f"{base[:150]} ({_QUICK_SUFFIX[payload.action]})")
        new_record = FileRecord(user_id=current_user.id, filename=new_name,
                                storage_path=new_id, file_size=len(data))
        db.add(new_record)
        db.commit()
        created = True
        if sizes is not None:
            sizes = {"before": sizes["before"], "after": len(data)}
        return {"status": "ok", "count": count, "report": report, "sizes": sizes,
                "file": {"id": new_record.id, "filename": new_record.filename, "session_id": new_id}}
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        _close_temp_session(session, keep_file=created)


@router.put("/files/{file_id}/rename")
def rename_file(file_id: int, payload: RenameFileRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
    stem = clean_pdf_stem(payload.filename)
    if f"{stem}.pdf" != file_record.filename:
        file_record.filename = _unique_filename(db, current_user.id, stem)
    db.commit()
    return {"msg": "เปลี่ยนชื่อไฟล์สำเร็จ", "filename": file_record.filename}
