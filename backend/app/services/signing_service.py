"""ส่งเอกสารให้ลงนามตามลำดับ — ขั้นตอนงาน (workflow) ฝั่งฐานข้อมูล

ผู้ส่ง (owner) เลือกไฟล์ของตัวเอง + ผู้ลงนาม 1..N (ต้องเป็นผู้ใช้ในระบบที่ยืนยันอีเมลแล้ว) + ตำแหน่งกล่องลายเซ็น
→ ระบบทำสำเนาเอกสาร สร้างฟิลด์ลายเซ็นของทุกคนไว้ล่วงหน้า (signing_pdf.prepare_signature_fields) แล้วส่งให้คนที่ 1
→ แต่ละคนลงนามได้เฉพาะเมื่อถึงคิว (ตรวจฝั่ง server + ล็อกแถวคำขอกันกดพร้อมกัน) → ครบทุกคนแล้วสร้างไฟล์
"(ลงนามครบแล้ว)" ในรายการไฟล์ของผู้ส่ง ทุกเหตุการณ์บันทึกใน signing_events พร้อม SHA-256 ของไฟล์ก่อน/หลัง

ไฟล์ทุกเวอร์ชันเก็บที่ UPLOAD_DIR/_signing/{request_id}/v{n}.pdf (v0 = หลังสร้างฟิลด์) ไม่ถูกบีบอัด/เขียนใหม่ทั้งไฟล์
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import FileRecord, Notification, SigningEvent, SigningRequest, SigningStep, User
from app.services import file_storage, passkey_service, signing_emails, signing_pdf

MAX_SIGNERS = 20
SIGN_TYPES = ("electronic", "digital", "either")


class SigningError(Exception):
    """ข้อความภาษาไทยที่แสดงให้ผู้ใช้ได้ — status คือ HTTP status ที่ควรตอบ"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class StepInput:
    email: str
    sign_type: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    parallel: bool = False  # ลงนามพร้อมกับคนก่อนหน้า (อยู่ขั้นเดียวกัน)
    require_passkey: bool = False  # ผู้ลงนามต้องยืนยันตัวตนด้วย passkey ก่อนลงนาม


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class ClientInfo:
    ip: Optional[str] = None
    user_agent: Optional[str] = None


# ---------------------------------------------------------------------------
# ไฟล์
# ---------------------------------------------------------------------------

def request_dir(request_id: int) -> Path:
    return settings.UPLOAD_DIR / "_signing" / str(request_id)


def version_path(request: SigningRequest, version: Optional[int] = None) -> Path:
    return request_dir(request.id) / f"v{request.version if version is None else version}.pdf"


def read_current(request: SigningRequest) -> bytes:
    path = version_path(request)
    if not path.is_file():
        raise SigningError("ไม่พบไฟล์เอกสารของคำขอนี้บนเซิร์ฟเวอร์", 404)
    return path.read_bytes()


def _write_version(request: SigningRequest, data: bytes) -> None:
    request.version += 1
    path = version_path(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# บันทึกเหตุการณ์ + แจ้งเตือน
# ---------------------------------------------------------------------------

def _event(db: Session, request: SigningRequest, actor: Optional[User], action: str, client: ClientInfo,
           detail: Optional[str] = None, before: Optional[bytes] = None, after: Optional[bytes] = None) -> None:
    db.add(SigningEvent(
        request_id=request.id,
        actor_user_id=actor.id if actor else None,
        action=action,
        detail=detail,
        ip=(client.ip or "")[:64] or None,
        user_agent=(client.user_agent or "")[:255] or None,
        sha256_before=signing_pdf.sha256(before) if before is not None else None,
        sha256_after=signing_pdf.sha256(after) if after is not None else None,
    ))


def _notify(db: Session, user_id: int, kind: str, title: str, request: SigningRequest,
            actor: Optional[User] = None, lines: Optional[list[str]] = None) -> None:
    """แจ้งเตือนในระบบ + เข้าคิวอีเมล (ส่งจริงหลัง commit — ดู _commit)"""
    db.add(Notification(user_id=user_id, kind=kind, title=title[:255], request_id=request.id))
    signing_emails.queue(db, signing_emails.OutgoingEmail(
        user_id=user_id, kind=kind, request_id=request.id, title=title,
        actor_id=actor.id if actor else None, lines=list(lines or [])))


def _invite(db: Session, email: str, request: SigningRequest, actor: Optional[User], your_turn: bool,
            lines: Optional[list[str]] = None) -> None:
    """อีเมลเชิญคนที่ยังไม่มีบัญชี (ไม่มีแจ้งเตือนในระบบเพราะยังไม่มีผู้ใช้)"""
    who = _display(actor) if actor else "ผู้ส่ง"
    status = "ตอนนี้ถึงคิวคุณลงนามแล้ว" if your_turn else "ระบบจะแจ้งอีกครั้งเมื่อถึงคิวของคุณ"
    signing_emails.queue(db, signing_emails.OutgoingEmail(
        user_id=None, to_email=email, kind="sign_invite", request_id=request.id,
        title=f"{who} เชิญคุณลงนามเอกสาร \"{request.title}\"", actor_id=actor.id if actor else None,
        lines=[status, f"สมัครสมาชิกด้วยอีเมล {email} แล้วยืนยันอีเมล เอกสารจะอยู่ในเมนู \"การลงนาม\"", *(lines or [])]))


def _notify_turn(db: Session, request: SigningRequest, step: SigningStep, actor: Optional[User],
                 lines: Optional[list[str]] = None) -> None:
    if step.signer_user_id is not None:
        owner = request.owner
        _notify(db, step.signer_user_id, "sign_turn", f"ถึงคิวคุณลงนาม \"{request.title}\" (ส่งโดย {_display(owner)})",
                request, actor=actor, lines=lines)
    elif step.invite_email:
        _invite(db, step.invite_email, request, actor, your_turn=True, lines=lines)


def _commit(db: Session) -> None:
    """commit แล้วค่อยส่งอีเมลที่เข้าคิวไว้ (ธุรกรรมล้ม = ไม่มีอีเมลหลุดออกไป)"""
    try:
        db.commit()
    except Exception:
        signing_emails.discard(db)
        raise
    signing_emails.flush(db)


def _display(user: Optional[User]) -> str:
    if user is None:
        return "-"
    return user.display_name or user.email


def _step_name(step: SigningStep) -> str:
    if step.signer is not None:
        return _display(step.signer)
    return step.signer_label or step.invite_email or "-"


def _field_spec(step: SigningStep) -> signing_pdf.FieldSpec:
    return signing_pdf.FieldSpec(step.field_name, step.page, step.x0, step.y0, step.x1, step.y1)


# ---------------------------------------------------------------------------
# สร้างคำขอ
# ---------------------------------------------------------------------------

def find_signer(db: Session, email: str) -> Optional[User]:
    email = (email or "").strip().lower()
    if not email:
        return None
    # เทียบตรงทั้งหมด (ไม่ใช้ ilike — % และ _ ในอีเมลจะกลายเป็น wildcard ให้ไล่หาผู้ใช้ได้)
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is None or not user.is_active or not user.is_verified:
        return None
    return user


def _validate_steps(db: Session, steps: list[StepInput],
                    page_sizes: list[tuple[float, float]]) -> list[tuple[Optional[User], str]]:
    """คืน [(ผู้ใช้ หรือ None = เชิญทางอีเมล, อีเมลตัวเล็ก)] ตามลำดับ"""
    if not steps:
        raise SigningError("ต้องมีผู้ลงนามอย่างน้อย 1 คน")
    if len(steps) > MAX_SIGNERS:
        raise SigningError(f"ผู้ลงนามได้ไม่เกิน {MAX_SIGNERS} คน")
    users, seen = [], set()
    for i, step in enumerate(steps, start=1):
        email = (step.email or "").strip().lower()
        if not _EMAIL_RE.match(email) or len(email) > 255:
            raise SigningError(f"อีเมลผู้ลงนามคนที่ {i} ไม่ถูกต้อง")
        user = find_signer(db, email)
        if email in seen:
            raise SigningError(f"{step.email} อยู่ในรายชื่อผู้ลงนามซ้ำ")
        seen.add(email)
        if step.sign_type not in SIGN_TYPES:
            raise SigningError("ประเภทลายเซ็นไม่ถูกต้อง")
        if not (0 <= step.page < len(page_sizes)):
            raise SigningError(f"ตำแหน่งลายเซ็นของผู้ลงนามคนที่ {i} อยู่นอกหน้าเอกสาร")
        w, h = page_sizes[step.page]
        if not (0 <= step.x0 < step.x1 <= w + 0.5 and 0 <= step.y0 < step.y1 <= h + 0.5):
            raise SigningError(f"กล่องลายเซ็นของผู้ลงนามคนที่ {i} อยู่นอกหน้าเอกสาร")
        if step.x1 - step.x0 < 30 or step.y1 - step.y0 < 15:
            raise SigningError(f"กล่องลายเซ็นของผู้ลงนามคนที่ {i} เล็กเกินไป")
        users.append((user, email))
    return users


def create_request(db: Session, owner: User, file_id: int, title: str, message: Optional[str],
                   steps: list[StepInput], client: ClientInfo,
                   due_at: Optional[dt.datetime] = None) -> SigningRequest:
    if due_at is not None:
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=dt.timezone.utc)
        if due_at <= dt.datetime.now(dt.timezone.utc):
            raise SigningError("วันครบกำหนดต้องเป็นเวลาในอนาคต")
    record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == owner.id).first()
    if record is None:
        raise SigningError("ไม่พบไฟล์ หรือคุณไม่มีสิทธิ์ใช้ไฟล์นี้", 404)
    path = file_storage.resolve_stored_pdf(record)
    if path is None:
        raise SigningError("ไม่พบไฟล์ต้นฉบับบนเซิร์ฟเวอร์", 404)
    source = path.read_bytes()
    try:
        with fitz.open("pdf", source) as doc:
            if doc.needs_pass:
                raise SigningError("ไฟล์มีรหัสผ่าน — กรุณาปลดรหัสผ่านก่อนส่งให้ลงนาม")
            # พิกัดกล่องเป็นพิกัดบนหน้าที่แสดงจริง (หมุนแล้ว) — signing_pdf แปลงเป็นพิกัด PDF เอง
            page_sizes = [(p.rect.width, p.rect.height) for p in doc]
    except SigningError:
        raise
    except Exception as exc:
        raise SigningError(f"เปิดไฟล์ PDF ไม่สำเร็จ: {exc}") from exc

    users = _validate_steps(db, steps, page_sizes)

    request = SigningRequest(owner_id=owner.id, source_file_id=record.id,
                             title=(title or record.filename).strip()[:255] or record.filename,
                             message=(message or "").strip() or None, status="in_progress",
                             current_order=1, version=0, due_at=due_at)
    db.add(request)
    db.flush()  # ได้ request.id สำหรับตั้งชื่อฟิลด์/โฟลเดอร์

    stage = 0
    for order, (step_in, (user, email)) in enumerate(zip(steps, users), start=1):
        if order == 1 or not step_in.parallel:
            stage += 1
        db.add(SigningStep(
            request_id=request.id, order=order, stage=stage, sign_type=step_in.sign_type,
            signer_user_id=user.id if user else None, invite_email=None if user else email,
            field_name=f"SR{request.id}_S{order}", page=step_in.page,
            x0=step_in.x0, y0=step_in.y0, x1=step_in.x1, y1=step_in.y1,
            status="pending" if stage == 1 else "waiting", require_passkey=bool(step_in.require_passkey),
        ))
    db.flush()
    db.refresh(request)

    try:
        prepared = signing_pdf.prepare_signature_fields(source, [_field_spec(s) for s in request.steps])
    except signing_pdf.SigningPdfError as exc:
        db.rollback()
        raise SigningError(str(exc)) from exc
    request.version = -1
    _write_version(request, prepared)  # v0

    invited = [s.invite_email for s in request.steps if s.invite_email]
    detail = f"ส่งให้ลงนาม {len(users)} คน" + (f" (เชิญทางอีเมล: {', '.join(invited)})" if invited else "")
    _event(db, request, owner, "created", client, detail=detail, before=source, after=prepared)
    for step in request.steps:
        if step.stage == 1:
            _notify_turn(db, request, step, owner)
        elif step.invite_email:
            _invite(db, step.invite_email, request, owner, your_turn=False)
    _turn_started(request)
    _commit(db)
    db.refresh(request)
    return request


# ---------------------------------------------------------------------------
# สิทธิ์ + ดึงข้อมูล
# ---------------------------------------------------------------------------

def get_request_for(db: Session, request_id: int, user: User, lock: bool = False) -> SigningRequest:
    """ผู้ส่งหรือผู้ลงนามในคำขอเท่านั้น — คนอื่นได้ 404 (ไม่บอกว่ามีคำขอนี้อยู่)"""
    query = db.query(SigningRequest).filter(SigningRequest.id == request_id)
    if lock:
        query = query.with_for_update()
    request = query.first()
    if request is None:
        raise SigningError("ไม่พบคำขอลงนาม", 404)
    if request.owner_id != user.id and all(s.signer_user_id != user.id for s in request.steps):
        raise SigningError("ไม่พบคำขอลงนาม", 404)
    return request


def list_requests(db: Session, user: User, box: str) -> list[SigningRequest]:
    query = db.query(SigningRequest)
    if box == "sent":
        query = query.filter(SigningRequest.owner_id == user.id)
    elif box == "to_sign":
        query = query.join(SigningStep).filter(SigningStep.signer_user_id == user.id,
                                               SigningStep.status == "pending",
                                               SigningRequest.status == "in_progress")
    else:  # all: ที่เกี่ยวข้องทั้งหมด
        query = query.outerjoin(SigningStep).filter(or_(SigningRequest.owner_id == user.id,
                                                        SigningStep.signer_user_id == user.id))
    return query.distinct().order_by(SigningRequest.updated_at.desc(), SigningRequest.id.desc()).limit(200).all()


def pending_steps(request: SigningRequest) -> list[SigningStep]:
    """ผู้ลงนามในขั้นปัจจุบันที่ยังไม่ได้ลงนาม (ขั้นเดียวกันลงนามพร้อมกันได้หลายคน)"""
    if request.status != "in_progress":
        return []
    return [s for s in request.steps if s.stage == request.current_order and s.status == "pending"]


def my_step(request: SigningRequest, user: User) -> Optional[SigningStep]:
    return next((s for s in request.steps if s.signer_user_id == user.id), None)


def record_view(db: Session, request: SigningRequest, user: User, client: ClientInfo) -> None:
    """บันทึกการเปิดดูเอกสารของผู้ลงนามที่ถึงคิว (ครั้งแรกเท่านั้น)"""
    if all(s.signer_user_id != user.id for s in pending_steps(request)):
        return
    seen = db.query(SigningEvent).filter(SigningEvent.request_id == request.id, SigningEvent.actor_user_id == user.id,
                                         SigningEvent.action == "viewed").first()
    if seen is None:
        _event(db, request, user, "viewed", client)
        db.commit()


# ---------------------------------------------------------------------------
# ลงนาม / ปฏิเสธ / ยกเลิก
# ---------------------------------------------------------------------------

def _require_turn(request: SigningRequest, user: User) -> SigningStep:
    if request.status != "in_progress":
        raise SigningError("คำขอนี้ไม่อยู่ในสถานะรอลงนามแล้ว", 409)
    step = my_step(request, user)
    if step is not None and step.status == "signed":
        raise SigningError("คุณลงนามเอกสารนี้ไปแล้ว", 409)
    if step is None or step not in pending_steps(request):
        raise SigningError("ยังไม่ถึงลำดับที่คุณต้องลงนาม", 409)
    return step


def passkey_purpose(request_id: int) -> str:
    return f"sign-{request_id}"


def passkey_options(db: Session, request_id: int, user: User) -> dict:
    """challenge สำหรับยืนยันตัวตนด้วย passkey ก่อนลงนามคำขอนี้ (ต้องถึงคิวแล้ว)"""
    request = get_request_for(db, request_id, user)
    _require_turn(request, user)
    try:
        return passkey_service.authentication_options(db, user, passkey_purpose(request.id))
    except passkey_service.PasskeyError as exc:
        raise SigningError(str(exc)) from exc


def sign(db: Session, request_id: int, user: User, sign_type: str, client: ClientInfo,
         signature_png: Optional[bytes] = None, pfx_bytes: Optional[bytes] = None,
         pfx_password: Optional[str] = None, reason: Optional[str] = None,
         passkey_flow_id: Optional[str] = None, passkey_credential: Optional[dict] = None) -> dict:
    request = get_request_for(db, request_id, user, lock=True)
    step = _require_turn(request, user)
    if sign_type not in ("electronic", "digital"):
        raise SigningError("ประเภทลายเซ็นไม่ถูกต้อง")
    if step.sign_type != "either" and step.sign_type != sign_type:
        label = "ลายเซ็นอิเล็กทรอนิกส์" if step.sign_type == "electronic" else "ลายเซ็นดิจิทัล (ใบรับรอง p12/pfx)"
        raise SigningError(f"ผู้ส่งกำหนดให้ขั้นนี้ใช้{label}")

    passkey = None
    if passkey_credential:
        try:
            passkey = passkey_service.verify_for_user(db, user, passkey_purpose(request.id),
                                                      passkey_flow_id or "", passkey_credential)
        except passkey_service.PasskeyError as exc:
            raise SigningError(str(exc), 403) from exc
    elif step.require_passkey:
        raise SigningError("ผู้ส่งกำหนดให้ยืนยันตัวตนด้วย passkey ก่อนลงนาม", 403)
    verified_note = f"ยืนยันตัวตนด้วย passkey ({passkey.name})" if passkey else None

    before = read_current(request)
    now_text = local_now_text()
    warning = None
    try:
        if signature_png:
            signature_png = signing_pdf.normalize_signature_image(signature_png)
        if sign_type == "electronic":
            if not signature_png:
                raise SigningError("กรุณาวาด/อัปโหลดลายเซ็นก่อน")
            signer = signing_pdf.system_seal_signer()
            who = f"{user.display_name} ({user.email})" if user.display_name else user.email
            caption = [who, f"ลงนามอิเล็กทรอนิกส์ {now_text}"]
            after = signing_pdf.sign_field(before, _field_spec(step), signer, caption, signature_png=signature_png,
                                           reason=reason or f"ลงนามอิเล็กทรอนิกส์โดย {user.email} "
                                           + (f"({verified_note})" if verified_note else "(ยืนยันตัวตนผ่านบัญชีผู้ใช้)"),
                                           name=_display(user))
            subject = who
        else:
            if not pfx_bytes:
                raise SigningError("กรุณาเลือกไฟล์ใบรับรอง (.p12/.pfx)")
            signer = signing_pdf.load_pkcs12_signer(pfx_bytes, pfx_password or "")
            cert = signing_pdf.signer_subject(signer)
            cn = cert.get("common_name") or _display(user)
            if cert.get("email") and str(cert["email"]).lower() != user.email.lower():
                warning = f"อีเมลในใบรับรอง ({cert['email']}) ไม่ตรงกับอีเมลบัญชี ({user.email})"
            caption = [f"ลงนามดิจิทัลโดย: {cn}", f"บัญชี: {user.email}", f"เวลา: {now_text}"]
            after = signing_pdf.sign_field(before, _field_spec(step), signer, caption,
                                           signature_png=signature_png, reason=reason, name=str(cn))
            subject = f"{cn}" + (f" <{cert['email']}>" if cert.get("email") else "")
    except signing_pdf.SigningPdfError as exc:
        raise SigningError(str(exc)) from exc

    _write_version(request, after)
    step.status = "signed"
    step.signed_type = sign_type
    step.signed_at = dt.datetime.now(dt.timezone.utc)
    step.cert_subject = subject[:255]
    if passkey is not None:
        step.verified_method = "passkey"
        step.verified_detail = passkey.name[:255]
        step.verified_at = step.signed_at
    _event(db, request, user, "signed", client, detail=f"ลำดับที่ {step.order} ({'อิเล็กทรอนิกส์' if sign_type == 'electronic' else 'ดิจิทัล'})"
           + (f" · {verified_note}" if verified_note else "")
           + (f" — {warning}" if warning else ""), before=before, after=after)

    signed_count = sum(1 for s in request.steps if s.status == "signed")
    progress = f"{_display(user)} ลงนาม \"{request.title}\" แล้ว ({signed_count}/{len(request.steps)})"
    if pending_steps(request):  # ยังมีคนในขั้นเดียวกันที่ยังไม่ได้ลงนาม
        _notify(db, request.owner_id, "sign_progress", progress, request)
    else:
        next_stage = [s for s in request.steps if s.stage == request.current_order + 1]
        if next_stage:
            request.current_order += 1
            for nxt in next_stage:
                nxt.status = "pending"
                _notify_turn(db, request, nxt, request.owner, lines=[f"{_display(user)} ลงนามลำดับที่ {step.order} แล้ว"])
            _turn_started(request)
            _notify(db, request.owner_id, "sign_progress", progress, request)
        else:
            _complete(db, request, after, client, last_signer=user)
    _commit(db)
    return {"status": request.status, "warning": warning}


def local_now_text() -> str:
    """เวลาบนตราลายเซ็นตามเขตเวลาของระบบ (APP_TIMEZONE) — เดิมใช้ datetime.now() ซึ่งเป็นเวลาเครื่อง
    image slim ไม่มี /usr/share/zoneinfo ตัวแปร TZ จึงไม่มีผล เวลาบนลายเซ็นเป็น UTC (ช้าไป 7 ชั่วโมง)"""
    from zoneinfo import ZoneInfo

    return dt.datetime.now(ZoneInfo(settings.APP_TIMEZONE)).strftime("%d/%m/%Y %H:%M")


def _unique_filename(db: Session, user_id: int, base: str) -> str:
    existing = {f for (f,) in db.query(FileRecord.filename).filter(FileRecord.user_id == user_id).all()}
    name, n = f"{base}.pdf", 2
    while name in existing:
        name, n = f"{base} ({n}).pdf", n + 1
    return name


def _complete(db: Session, request: SigningRequest, data: bytes, client: ClientInfo,
              last_signer: Optional[User] = None) -> None:
    """ครบทุกคน: สร้างไฟล์ในรายการไฟล์ของผู้ส่ง + แจ้งทุกคน"""
    request.status = "completed"
    request.current_order = 0
    request.completed_at = dt.datetime.now(dt.timezone.utc)
    storage_id = uuid.uuid4().hex
    target = file_storage.upload_path(storage_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(version_path(request), target)
    base = request.title[:-4] if request.title.lower().endswith(".pdf") else request.title
    name = _unique_filename(db, request.owner_id, f"{base[:200]} (ลงนามครบแล้ว)")  # ส่งเอกสารชื่อเดิมซ้ำ → (2), (3)
    record = FileRecord(user_id=request.owner_id, filename=name,
                        original_filename=name, storage_path=storage_id,
                        file_size=len(data))
    db.add(record)
    db.flush()
    request.result_file_id = record.id
    _event(db, request, None, "completed", client, after=data)
    _notify(db, request.owner_id, "sign_completed", f"\"{request.title}\" ลงนามครบทุกคนแล้ว", request,
            actor=last_signer, lines=["ไฟล์ที่ลงนามครบแล้วอยู่ในหน้า \"เอกสารของฉัน\""])
    for s in request.steps:
        if s.signer_user_id is not None and s.signer_user_id != request.owner_id:
            _notify(db, s.signer_user_id, "sign_completed", f"\"{request.title}\" ลงนามครบทุกคนแล้ว", request,
                    actor=request.owner)


def reject(db: Session, request_id: int, user: User, reason: str, client: ClientInfo) -> None:
    request = get_request_for(db, request_id, user, lock=True)
    step = _require_turn(request, user)
    reason = (reason or "").strip()
    if not reason:
        raise SigningError("กรุณาระบุเหตุผลที่ปฏิเสธ")
    step.status = "rejected"
    step.comment = reason[:2000]
    request.status = "rejected"
    request.current_order = 0
    _event(db, request, user, "rejected", client, detail=reason[:2000])
    _notify(db, request.owner_id, "sign_rejected", f"{_display(user)} ปฏิเสธการลงนาม \"{request.title}\"", request,
            actor=user, lines=[f"เหตุผล: {reason}"])
    _commit(db)


def cancel(db: Session, request_id: int, user: User, client: ClientInfo) -> None:
    request = get_request_for(db, request_id, user, lock=True)
    if request.owner_id != user.id:
        raise SigningError("เฉพาะผู้ส่งเท่านั้นที่ยกเลิกคำขอได้", 403)
    if request.status != "in_progress":
        raise SigningError("คำขอนี้จบไปแล้ว ยกเลิกไม่ได้", 409)
    waiting_for = pending_steps(request)
    request.status = "cancelled"
    request.current_order = 0
    _event(db, request, user, "cancelled", client)
    for step in waiting_for:
        if step.signer_user_id is not None:
            _notify(db, step.signer_user_id, "sign_cancelled", f"{_display(user)} ยกเลิกคำขอลงนาม \"{request.title}\"",
                    request, actor=user, lines=["ไม่ต้องลงนามเอกสารนี้แล้ว"])
    _commit(db)


# ---------------------------------------------------------------------------
# ส่งเตือน + ครบกำหนด (เฟส 2)
# ---------------------------------------------------------------------------

def _aware(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    if value is not None and value.tzinfo is None:  # SQLite คืนเวลาแบบไม่มี timezone
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def _turn_started(request: SigningRequest) -> None:
    """อีเมล "ถึงคิว" บอกวันครบกำหนดอยู่แล้ว — ถ้าใกล้ครบกำหนดอยู่แล้วตอนเริ่มคิว ไม่ต้องส่ง "ใกล้ครบกำหนด" ซ้ำทันที"""
    due = _aware(request.due_at)
    now = dt.datetime.now(dt.timezone.utc)
    if due is not None and due <= now + dt.timedelta(hours=settings.SIGNING_DUE_SOON_HOURS):
        request.due_soon_notified_at = now


def remind(db: Session, request_id: int, user: User, client: ClientInfo) -> None:
    """ผู้ส่งกดส่งเตือนผู้ลงนามที่ถึงคิว — เว้นช่วงตาม SIGNING_REMIND_COOLDOWN_MINUTES"""
    request = get_request_for(db, request_id, user, lock=True)
    if request.owner_id != user.id:
        raise SigningError("เฉพาะผู้ส่งเท่านั้นที่ส่งเตือนได้", 403)
    if request.status != "in_progress":
        raise SigningError("คำขอนี้จบไปแล้ว", 409)
    now = dt.datetime.now(dt.timezone.utc)
    last = _aware(request.last_reminded_at)
    cooldown = dt.timedelta(minutes=settings.SIGNING_REMIND_COOLDOWN_MINUTES)
    if last is not None and now - last < cooldown:
        wait = int((cooldown - (now - last)).total_seconds() // 60) + 1
        raise SigningError(f"เพิ่งส่งเตือนไป ส่งเตือนอีกครั้งได้ในอีก {wait} นาที", 429)
    waiting_for = pending_steps(request)
    request.last_reminded_at = now
    _event(db, request, user, "reminded", client,
           detail="เตือน " + ", ".join(f"ลำดับที่ {s.order} ({_step_name(s)})" for s in waiting_for))
    for step in waiting_for:
        if step.signer_user_id is not None:
            _notify(db, step.signer_user_id, "sign_reminder", f"{_display(user)} เตือนให้ลงนาม \"{request.title}\"",
                    request, actor=user)
        elif step.invite_email:
            _invite(db, step.invite_email, request, user, your_turn=True)
    _commit(db)


def process_due_dates(db: Session, now: Optional[dt.datetime] = None) -> dict:
    """งานเบื้องหลัง (ทุก CLEANUP_INTERVAL): เตือนผู้ลงนามเมื่อใกล้ครบกำหนด และแจ้งผู้ส่งเมื่อเลยกำหนด

    แต่ละเรื่องส่งครั้งเดียวต่อคำขอ — "จอง" ด้วย UPDATE แบบมีเงื่อนไขก่อน กันส่งซ้ำเมื่อรันหลาย instance พร้อมกัน
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    soon_limit = now + dt.timedelta(hours=settings.SIGNING_DUE_SOON_HOURS)
    counts = {"due_soon": 0, "overdue": 0}

    candidates = (db.query(SigningRequest.id)
                  .filter(SigningRequest.status == "in_progress", SigningRequest.due_at.isnot(None),
                          SigningRequest.due_at <= soon_limit,
                          or_(SigningRequest.due_soon_notified_at.is_(None), SigningRequest.overdue_notified_at.is_(None)))
                  .all())
    for (request_id,) in candidates:
        request = db.get(SigningRequest, request_id)
        due = _aware(request.due_at)
        waiting_for = pending_steps(request)
        if not waiting_for:
            continue
        names = ", ".join(_step_name(s) for s in waiting_for)
        if due <= now and request.overdue_notified_at is None:
            claimed = (db.query(SigningRequest)
                       .filter(SigningRequest.id == request_id, SigningRequest.overdue_notified_at.is_(None))
                       .update({SigningRequest.overdue_notified_at: now,
                                SigningRequest.due_soon_notified_at: func.coalesce(SigningRequest.due_soon_notified_at, now)},
                               synchronize_session=False))
            if claimed:
                _notify(db, request.owner_id, "sign_overdue",
                        f"\"{request.title}\" เลยกำหนดลงนามแล้ว (รอ {names})", request, actor=waiting_for[0].signer)
                for step in waiting_for:
                    if step.signer_user_id is not None:
                        _notify(db, step.signer_user_id, "sign_reminder",
                                f"\"{request.title}\" เลยกำหนดลงนามแล้ว — รอคุณลงนาม", request, actor=request.owner)
                    elif step.invite_email:
                        _invite(db, step.invite_email, request, request.owner, your_turn=True,
                                lines=["เอกสารนี้เลยกำหนดลงนามแล้ว"])
                counts["overdue"] += 1
        elif due > now and request.due_soon_notified_at is None:
            claimed = (db.query(SigningRequest)
                       .filter(SigningRequest.id == request_id, SigningRequest.due_soon_notified_at.is_(None))
                       .update({SigningRequest.due_soon_notified_at: now}, synchronize_session=False))
            if claimed:
                for step in waiting_for:
                    if step.signer_user_id is not None:
                        _notify(db, step.signer_user_id, "sign_reminder",
                                f"\"{request.title}\" ใกล้ครบกำหนดลงนาม", request, actor=request.owner)
                    elif step.invite_email:
                        _invite(db, step.invite_email, request, request.owner, your_turn=True,
                                lines=["เอกสารนี้ใกล้ครบกำหนดลงนามแล้ว"])
                counts["due_soon"] += 1
        _commit(db)
    return counts


# ---------------------------------------------------------------------------
# เชิญคนที่ยังไม่มีบัญชี + หลักฐานแนบท้าย (เฟส 3)
# ---------------------------------------------------------------------------

def claim_invites(db: Session, user: User) -> int:
    """ผูกคำเชิญที่ส่งถึงอีเมลนี้เข้ากับบัญชี — เรียกหลัง login/ยืนยันอีเมล (ต้องยืนยันอีเมลแล้วเท่านั้น)"""
    if not user.is_verified or not user.is_active:
        return 0
    steps = (db.query(SigningStep)
             .filter(SigningStep.signer_user_id.is_(None), SigningStep.invite_email == user.email.strip().lower())
             .all())
    claimed = 0
    for step in steps:
        request = step.request
        if any(s.signer_user_id == user.id for s in request.steps):
            continue  # อยู่ในคำขอนี้แล้ว (เช่นผู้ส่งเชิญตัวเองซ้ำ) — ปล่อยไว้ให้ผู้ส่งจัดการ
        step.signer_user_id = user.id
        claimed += 1
        _event(db, request, user, "invite_accepted", ClientInfo(),
               detail=f"ผูกบัญชี {user.email} กับผู้ลงนามลำดับที่ {step.order}")
        if step in pending_steps(request):
            _notify(db, user.id, "sign_turn", f"ถึงคิวคุณลงนาม \"{request.title}\" (ส่งโดย {_display(request.owner)})",
                    request, actor=request.owner)
    if claimed:
        _commit(db)
    return claimed


def evidence_pdf(db: Session, request: SigningRequest) -> bytes:
    """หนังสือรับรองการลงนาม (ไฟล์แยก ลงนามด้วยใบรับรองระบบ) — เก็บไว้เมื่อคำขอจบแล้ว ระหว่างทางสร้างใหม่ทุกครั้ง"""
    from app.services import signing_evidence

    cache = request_dir(request.id) / f"evidence-{request.status}.pdf"
    if request.status != "in_progress" and cache.is_file():
        return cache.read_bytes()
    try:
        data = signing_evidence.seal(signing_evidence.build_evidence_pdf(db, request))
    except Exception as exc:
        raise SigningError(f"สร้างหนังสือรับรองไม่สำเร็จ: {exc}", 500) from exc
    if request.status != "in_progress":
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(cache)
    return data


def set_email_preference(db: Session, user: User, enabled: bool) -> bool:
    user.signing_email_notifications = bool(enabled)
    db.commit()
    return user.signing_email_notifications


# ---------------------------------------------------------------------------
# แสดงผล
# ---------------------------------------------------------------------------

def page_sizes(request: SigningRequest) -> list[list[float]]:
    with fitz.open(version_path(request)) as doc:
        return [[p.rect.width, p.rect.height] for p in doc]


def render_page(request: SigningRequest, page: int, zoom: float) -> bytes:
    zoom = max(0.25, min(zoom, 3.0))
    with fitz.open(version_path(request)) as doc:
        if not (0 <= page < doc.page_count):
            raise SigningError("ไม่มีหน้านี้", 404)
        target = doc[page]
        # MuPDF วาดป้าย "SIGN" สีส้มบนฟิลด์ลายเซ็นที่ยังว่าง — ซ่อนเฉพาะในภาพตัวอย่าง (doc เปิดในหน่วยความจำ ไม่ได้บันทึก)
        # หน้าเว็บวาดกรอบกล่องลายเซ็นของแต่ละคนทับให้เองอยู่แล้ว
        for widget in target.widgets():
            if widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and doc.xref_get_key(widget.xref, "V")[0] == "null":
                doc.xref_set_key(widget.xref, "F", "2")  # Hidden
        return target.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")


def _signer_info(step: SigningStep) -> dict:
    if step.signer is not None:
        return {"id": step.signer.id, "email": step.signer.email, "name": _display(step.signer), "invited": False}
    if step.signer_label:  # ผู้ลงนามลบบัญชีไปแล้ว
        return {"id": None, "email": None, "name": step.signer_label, "invited": False, "deleted": True}
    return {"id": None, "email": step.invite_email, "name": step.invite_email, "invited": True}


def _iso(value: Optional[dt.datetime]) -> Optional[str]:
    return _aware(value).isoformat() if value else None


def _step_status(request: SigningRequest, step: SigningStep) -> str:
    """คำขอจบแล้ว (ยกเลิก/ถูกปฏิเสธ) คนที่ยังไม่ได้ลงนาม = "skipped" — เดิมยังแสดง "ถึงคิวลงนาม"/"รอคิว" ต่อ"""
    if request.status != "in_progress" and step.status in ("pending", "waiting"):
        return "skipped"
    return step.status


def serialize(request: SigningRequest, viewer: User, events: Optional[list[SigningEvent]] = None) -> dict:
    waiting_for = pending_steps(request)
    mine = next((s for s in waiting_for if s.signer_user_id == viewer.id), None)
    data = {
        "id": request.id,
        "title": request.title,
        "message": request.message,
        "status": request.status,
        "current_order": request.current_order,
        "owner_id": request.owner_id,
        "owner": {"id": request.owner.id, "email": request.owner.email, "name": _display(request.owner)},
        "is_owner": request.owner_id == viewer.id,
        "my_turn": mine is not None,
        "my_step_order": mine.order if mine else None,
        "my_require_passkey": bool(mine.require_passkey) if mine else False,
        "waiting_for": [_step_name(s) for s in waiting_for],
        "result_file_id": request.result_file_id if request.owner_id == viewer.id else None,
        "created_at": _iso(request.created_at),
        "completed_at": _iso(request.completed_at),
        "due_at": _iso(request.due_at),
        "overdue": bool(request.status == "in_progress" and request.due_at
                        and _aware(request.due_at) <= dt.datetime.now(dt.timezone.utc)),
        "last_reminded_at": _iso(request.last_reminded_at),
        "steps": [
            {
                "order": s.order,
                "stage": s.stage,
                "signer": _signer_info(s),
                "sign_type": s.sign_type,
                "status": _step_status(request, s),
                "signed_type": s.signed_type,
                "signed_at": _iso(s.signed_at),
                "cert_subject": s.cert_subject,
                "comment": s.comment,
                "require_passkey": bool(s.require_passkey),
                "verified_method": s.verified_method,
                "verified_detail": s.verified_detail,
                "page": s.page,
                "rect": {"x0": s.x0, "y0": s.y0, "x1": s.x1, "y1": s.y1},
            }
            for s in request.steps
        ],
    }
    if events is not None:
        data["events"] = [
            {"action": e.action, "actor_user_id": e.actor_user_id, "actor_label": e.actor_label, "detail": e.detail,
             "created_at": _iso(e.created_at),
             "sha256_after": e.sha256_after}
            for e in events
        ]
    return data


# ---------------------------------------------------------------------------
# ลบบัญชีผู้ใช้ (ดู services/account_service.py)
# ---------------------------------------------------------------------------

def user_label(user: User) -> str:
    """ชื่อ/อีเมลที่เก็บไว้ในประวัติการลงนามของเอกสารคนอื่น หลังผู้ใช้ลบบัญชี"""
    base = f"{user.display_name} <{user.email}>" if user.display_name else user.email
    return f"{base} (ลบบัญชีแล้ว)"[:255]


def release_deleted_user(db: Session, user: User, client: ClientInfo) -> dict:
    """เตรียมลบบัญชี: (1) ยกเลิกคำขอที่ผู้ใช้ส่งเองที่ยังค้าง (แจ้งผู้ลงนาม) (2) คำขอของคนอื่นที่ผู้ใช้ยังไม่ได้ลงนาม
    → ปฏิเสธอัตโนมัติ "ผู้ลงนามลบบัญชีแล้ว" (แจ้งเจ้าของ) (3) ตัดการเชื่อมบัญชีในเอกสารของคนอื่น แต่เก็บชื่อ/อีเมล
    ไว้เป็นหลักฐาน — ไม่ลบคำขอที่ผู้ใช้ส่งเอง (ผู้เรียกลบพร้อมบัญชี) คืนจำนวนที่จัดการ"""
    counts = {"cancelled": 0, "rejected": 0, "detached": 0}
    label = user_label(user)

    owned = (db.query(SigningRequest.id)
             .filter(SigningRequest.owner_id == user.id, SigningRequest.status == "in_progress").all())
    for (request_id,) in owned:
        cancel(db, request_id, user, client)
        counts["cancelled"] += 1

    others = (db.query(SigningRequest)
              .join(SigningStep, SigningStep.request_id == SigningRequest.id)
              .filter(SigningStep.signer_user_id == user.id, SigningRequest.owner_id != user.id)
              .distinct().all())
    for request in others:
        mine = [s for s in request.steps if s.signer_user_id == user.id]
        if request.status == "in_progress" and any(s.status != "signed" for s in mine):
            reason = "ผู้ลงนามลบบัญชีผู้ใช้แล้ว"
            for step in mine:
                if step.status != "signed":
                    step.status = "rejected"
                    step.comment = reason
            request.status = "rejected"
            request.current_order = 0
            _event(db, request, user, "rejected", client, detail=reason)
            _notify(db, request.owner_id, "sign_rejected",
                    f"{_display(user)} ลบบัญชีแล้ว — คำขอ \"{request.title}\" ถูกปฏิเสธอัตโนมัติ", request,
                    actor=None, lines=["ผู้ลงนามลบบัญชีผู้ใช้ จึงลงนามเอกสารนี้ต่อไม่ได้ — ส่งคำขอใหม่ถึงผู้ลงนามคนอื่นได้"])
            counts["rejected"] += 1
        for step in mine:
            step.signer_label = label
            step.signer_user_id = None
            counts["detached"] += 1
    # เหตุการณ์ที่ผู้ใช้เป็นคนทำในคำขอของคนอื่น (ลงนาม/ปฏิเสธ/เปิดดู) — เก็บชื่อไว้ ตัดการเชื่อมบัญชี
    (db.query(SigningEvent)
     .filter(SigningEvent.actor_user_id == user.id,
             SigningEvent.request_id.in_(db.query(SigningRequest.id).filter(SigningRequest.owner_id != user.id)))
     .update({SigningEvent.actor_label: label, SigningEvent.actor_user_id: None}, synchronize_session=False))
    # แจ้งเตือนในระบบของคนอื่นที่ชี้ไปยังคำขอที่จะถูกลบ — เก็บข้อความไว้ (ไม่ให้หายไปพร้อมคำขอ)
    owned_ids = db.query(SigningRequest.id).filter(SigningRequest.owner_id == user.id)
    (db.query(Notification)
     .filter(Notification.request_id.in_(owned_ids), Notification.user_id != user.id)
     .update({Notification.request_id: None}, synchronize_session=False))
    _commit(db)
    return counts
