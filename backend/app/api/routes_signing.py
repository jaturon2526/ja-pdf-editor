"""API ส่งเอกสารให้ลงนามตามลำดับ + แจ้งเตือนในระบบ (ดู app/services/signing_service.py)"""
from __future__ import annotations

import datetime as dt
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_active_user
from app.db.database import get_db
from app.models.domain import Notification, SigningEvent, User
from app.services import signing_pdf, signing_service
from app.services.signing_service import ClientInfo, SigningError, StepInput

router = APIRouter(prefix="/signing", tags=["signing"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])

_MAX_UPLOAD = 5 * 1024 * 1024  # รูปลายเซ็น/ไฟล์ p12


def _client(request: Request) -> ClientInfo:
    return ClientInfo(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


def _http(exc: SigningError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


def _require_verified(user: User) -> None:
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="กรุณายืนยันอีเมลก่อนใช้งานการลงนาม")


class StepPayload(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    sign_type: Literal["electronic", "digital", "either"] = "either"
    page: int = Field(ge=0)
    x0: float
    y0: float
    x1: float
    y1: float
    parallel: bool = False  # ลงนามพร้อมกับคนก่อนหน้า
    require_passkey: bool = False  # ผู้ลงนามต้องยืนยันตัวตนด้วย passkey ก่อนลงนาม


class CreatePayload(BaseModel):
    file_id: int
    title: Optional[str] = Field(default=None, max_length=255)
    message: Optional[str] = Field(default=None, max_length=2000)
    steps: list[StepPayload]
    due_at: Optional[dt.datetime] = None  # วันครบกำหนด (ไม่บังคับ) — ISO 8601 ควรมี timezone


class RejectPayload(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@router.get("/users/lookup")
def lookup_user(email: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """หาผู้ลงนามด้วยอีเมล (ตรงทั้งหมดเท่านั้น — ไม่เปิดให้ค้นหาบางส่วนเพื่อไม่ให้ไล่ดูรายชื่อผู้ใช้ได้)"""
    user = signing_service.find_signer(db, email)
    if user is None:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้อีเมลนี้ในระบบ (หรือยังไม่ได้ยืนยันอีเมล)")
    return {"id": user.id, "email": user.email, "name": user.display_name or user.email}


def _owned_file_path(db: Session, user: User, file_id: int):
    from app.models.domain import FileRecord
    from app.services import file_storage

    record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == user.id).first()
    path = file_storage.resolve_stored_pdf(record) if record else None
    if path is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ หรือคุณไม่มีสิทธิ์ใช้ไฟล์นี้")
    return record, path


@router.get("/files/{file_id}/info")
def source_file_info(file_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """ข้อมูลไฟล์ต้นฉบับสำหรับหน้าสร้างคำขอ (ขนาดแต่ละหน้า) — เฉพาะไฟล์ของตัวเอง"""
    import fitz

    record, path = _owned_file_path(db, current_user, file_id)
    try:
        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise HTTPException(status_code=400, detail="ไฟล์มีรหัสผ่าน — กรุณาปลดรหัสผ่านก่อนส่งให้ลงนาม")
            sizes = [[p.rect.width, p.rect.height] for p in doc]
            rotated = any(p.rotation for p in doc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"เปิดไฟล์ PDF ไม่สำเร็จ: {exc}")
    return {"id": record.id, "filename": record.filename, "page_sizes": sizes, "has_rotated_pages": rotated}


@router.get("/files/{file_id}/pages/{page}")
def source_file_page(file_id: int, page: int, zoom: float = 1.0, current_user: User = Depends(get_current_active_user),
                     db: Session = Depends(get_db)):
    import fitz

    _, path = _owned_file_path(db, current_user, file_id)
    zoom = max(0.25, min(zoom, 3.0))
    with fitz.open(path) as doc:
        if doc.needs_pass or not (0 <= page < doc.page_count):
            raise HTTPException(status_code=404, detail="ไม่มีหน้านี้")
        png = doc[page].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@router.post("/requests")
def create_request(payload: CreatePayload, request: Request, current_user: User = Depends(get_current_active_user),
                   db: Session = Depends(get_db)):
    _require_verified(current_user)
    steps = [StepInput(**s.model_dump()) for s in payload.steps]
    try:
        sr = signing_service.create_request(db, current_user, payload.file_id, payload.title, payload.message,
                                            steps, _client(request), due_at=payload.due_at)
    except SigningError as exc:
        raise _http(exc)
    return signing_service.serialize(sr, current_user)


@router.get("/requests")
def list_requests(box: Literal["to_sign", "sent", "all"] = "all", current_user: User = Depends(get_current_active_user),
                  db: Session = Depends(get_db)):
    return [signing_service.serialize(r, current_user) for r in signing_service.list_requests(db, current_user, box)]


@router.get("/requests/{request_id}")
def get_request(request_id: int, request: Request, current_user: User = Depends(get_current_active_user),
                db: Session = Depends(get_db)):
    try:
        sr = signing_service.get_request_for(db, request_id, current_user)
        signing_service.record_view(db, sr, current_user, _client(request))
        events = db.query(SigningEvent).filter(SigningEvent.request_id == sr.id).order_by(SigningEvent.id).all()
        data = signing_service.serialize(sr, current_user, events)
        data["page_sizes"] = signing_service.page_sizes(sr)
    except SigningError as exc:
        raise _http(exc)
    return data


@router.get("/requests/{request_id}/pages/{page}")
def page_image(request_id: int, page: int, zoom: float = 1.0, current_user: User = Depends(get_current_active_user),
               db: Session = Depends(get_db)):
    try:
        sr = signing_service.get_request_for(db, request_id, current_user)
        png = signing_service.render_page(sr, page, zoom)
    except SigningError as exc:
        raise _http(exc)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@router.get("/requests/{request_id}/document")
def document(request_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    try:
        sr = signing_service.get_request_for(db, request_id, current_user)
        data = signing_service.read_current(sr)
    except SigningError as exc:
        raise _http(exc)
    filename = sr.title if sr.title.lower().endswith(".pdf") else f"{sr.title}.pdf"
    from urllib.parse import quote

    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                             "Cache-Control": "private, no-store"})


@router.get("/requests/{request_id}/evidence")
def evidence(request_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """หนังสือรับรองการลงนาม (PDF แยก) — ผู้ส่งและผู้ลงนามในคำขอดาวน์โหลดได้"""
    try:
        sr = signing_service.get_request_for(db, request_id, current_user)
        data = signing_service.evidence_pdf(db, sr)
    except SigningError as exc:
        raise _http(exc)
    base = sr.title[:-4] if sr.title.lower().endswith(".pdf") else sr.title
    from urllib.parse import quote

    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(base + ' (หลักฐานการลงนาม).pdf')}",
                             "Cache-Control": "private, no-store"})


@router.get("/requests/{request_id}/verify")
def verify(request_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """ตรวจลายเซ็นทุกฟิลด์ในเวอร์ชันล่าสุด (ไม่ตรวจ trust chain)"""
    try:
        sr = signing_service.get_request_for(db, request_id, current_user)
        data = signing_service.read_current(sr)
    except SigningError as exc:
        raise _http(exc)
    return {"signatures": signing_pdf.signature_report(data)}


@router.post("/requests/{request_id}/passkey/options")
def sign_passkey_options(request_id: int, current_user: User = Depends(get_current_active_user),
                         db: Session = Depends(get_db)):
    """challenge สำหรับยืนยันตัวตนด้วย passkey ก่อนลงนาม — ส่งผลกลับมากับ /sign (passkey_flow_id + passkey_credential)"""
    _require_verified(current_user)
    try:
        return signing_service.passkey_options(db, request_id, current_user)
    except SigningError as exc:
        raise _http(exc)


@router.post("/requests/{request_id}/sign")
async def sign(
    request_id: int,
    request: Request,
    sign_type: Literal["electronic", "digital"] = Form(...),
    reason: Optional[str] = Form(None),
    pfx_password: Optional[str] = Form(None),
    signature_image: Optional[UploadFile] = File(None),
    pfx_file: Optional[UploadFile] = File(None),
    passkey_flow_id: Optional[str] = Form(None),
    passkey_credential: Optional[str] = Form(None),  # JSON จาก navigator.credentials.get()
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _require_verified(current_user)

    async def _read(upload: Optional[UploadFile]) -> Optional[bytes]:
        if upload is None:
            return None
        data = await upload.read(_MAX_UPLOAD + 1)
        if len(data) > _MAX_UPLOAD:
            raise HTTPException(status_code=413, detail="ไฟล์ใหญ่เกินไป (สูงสุด 5 MB)")
        return data or None

    credential = None
    if passkey_credential:
        try:
            credential = json.loads(passkey_credential)
        except ValueError:
            raise HTTPException(status_code=400, detail="ข้อมูล passkey ไม่ถูกต้อง")
        if not isinstance(credential, dict):
            raise HTTPException(status_code=400, detail="ข้อมูล passkey ไม่ถูกต้อง")
    png = await _read(signature_image)
    pfx = await _read(pfx_file)
    client = _client(request)
    try:
        return await run_in_threadpool(
            signing_service.sign, db, request_id, current_user, sign_type, client,
            signature_png=png, pfx_bytes=pfx, pfx_password=pfx_password, reason=(reason or "").strip()[:200] or None,
            passkey_flow_id=passkey_flow_id, passkey_credential=credential,
        )
    except SigningError as exc:
        raise _http(exc)


@router.post("/requests/{request_id}/reject")
def reject(request_id: int, payload: RejectPayload, request: Request,
           current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    try:
        signing_service.reject(db, request_id, current_user, payload.reason, _client(request))
    except SigningError as exc:
        raise _http(exc)
    return {"status": "rejected"}


@router.post("/requests/{request_id}/cancel")
def cancel(request_id: int, request: Request, current_user: User = Depends(get_current_active_user),
           db: Session = Depends(get_db)):
    try:
        signing_service.cancel(db, request_id, current_user, _client(request))
    except SigningError as exc:
        raise _http(exc)
    return {"status": "cancelled"}


@router.post("/requests/{request_id}/remind")
def remind(request_id: int, request: Request, current_user: User = Depends(get_current_active_user),
           db: Session = Depends(get_db)):
    try:
        signing_service.remind(db, request_id, current_user, _client(request))
    except SigningError as exc:
        raise _http(exc)
    return {"status": "reminded"}


class PreferencesPayload(BaseModel):
    email_notifications: bool


@router.get("/preferences")
def get_preferences(current_user: User = Depends(get_current_active_user)):
    return {"email_notifications": bool(current_user.signing_email_notifications)}


@router.put("/preferences")
def put_preferences(payload: PreferencesPayload, current_user: User = Depends(get_current_active_user),
                    db: Session = Depends(get_db)):
    enabled = signing_service.set_email_preference(db, current_user, payload.email_notifications)
    return {"email_notifications": enabled}


# ---------------------------------------------------------------------------
# แจ้งเตือนในระบบ
# ---------------------------------------------------------------------------

class ReadPayload(BaseModel):
    ids: Optional[list[int]] = None  # None = อ่านทั้งหมด


@notifications_router.get("")
def list_notifications(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    base = db.query(Notification).filter(Notification.user_id == current_user.id)
    items = base.order_by(Notification.id.desc()).limit(50).all()
    unread = base.filter(Notification.read_at.is_(None)).count()
    return {
        "unread": unread,
        "items": [
            {"id": n.id, "kind": n.kind, "title": n.title, "request_id": n.request_id,
             "read": n.read_at is not None, "created_at": signing_service._iso(n.created_at)}
            for n in items
        ],
    }


@notifications_router.post("/read")
def mark_read(payload: ReadPayload, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    query = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.read_at.is_(None))
    if payload.ids is not None:
        query = query.filter(Notification.id.in_(payload.ids))
    query.update({Notification.read_at: dt.datetime.now(dt.timezone.utc)}, synchronize_session=False)
    db.commit()
    return {"status": "ok"}
