"""ลบบัญชีผู้ใช้ถาวร (ผู้ใช้กดเองที่หน้าโปรไฟล์) — ไฟล์และข้อมูลทั้งหมดของผู้ใช้ถูกลบ กู้คืนไม่ได้

ลำดับ:
1. ยืนยันตัวตนอีกครั้ง (รหัสผ่าน หรือ passkey) + พิมพ์อีเมลของตัวเอง — ตรวจใน route
2. คำขอลงนาม (signing_service.release_deleted_user): ที่ส่งเองและยังค้าง → ยกเลิก แจ้งผู้ลงนาม · ในเอกสารของคนอื่น
   ที่ยังไม่ได้ลงนาม → ปฏิเสธอัตโนมัติ แจ้งเจ้าของ · ประวัติที่ลงนามไปแล้วในเอกสารของคนอื่นยังอยู่ (เก็บชื่อ/อีเมล
   เป็นหลักฐานของเจ้าของเอกสาร) แต่ตัดการเชื่อมกับบัญชี
3. ลบไฟล์บนดิสก์: ไฟล์ทุกไฟล์ของผู้ใช้ (+ ไฟล์ Word ที่แปลง), โฟลเดอร์คำขอลงนามที่ส่งเอง, ฟอนต์ที่ติดตั้งเอง
4. ลบแถวในฐานข้อมูล: คำขอที่ส่งเอง (steps/events ตามไป), ไฟล์, งานแปลง, passkey, แจ้งเตือน, สถิติ AI, ผู้ใช้
   — License ที่เคยใช้ตั้ง used_by_user_id = NULL (เก็บประวัติคีย์ไว้)
5. ส่งอีเมลยืนยันว่าลบแล้ว (เผื่อไม่ได้ลบเอง จะได้รู้ตัว)
"""
from __future__ import annotations

import logging
import os
import shutil

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.session import session_manager
from app.models.domain import (AIUsageDaily, ConversionTask, FileRecord, License, Notification, Passkey,
                               SigningEvent, SigningRequest, SigningStep, User)
from app.services import file_storage, mailer, signing_service
from app.services.signing_service import ClientInfo

logger = logging.getLogger("account")


class AccountDeletionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _is_last_admin(db: Session, user: User) -> bool:
    if not user.is_admin:
        return False
    others = (db.query(func.count(User.id))
              .filter(User.is_admin.is_(True), User.is_active.is_(True), User.id != user.id).scalar())
    return not others


def summary(db: Session, user: User) -> dict:
    """สิ่งที่จะถูกลบ — แสดงในหน้ายืนยันก่อนลบ"""
    files = db.query(func.count(FileRecord.id), func.coalesce(func.sum(FileRecord.file_size), 0)) \
        .filter(FileRecord.user_id == user.id).one()
    owned = dict(db.query(SigningRequest.status, func.count(SigningRequest.id))
                 .filter(SigningRequest.owner_id == user.id).group_by(SigningRequest.status).all())
    pending_as_signer = (db.query(func.count(func.distinct(SigningRequest.id)))
                         .join(SigningStep, SigningStep.request_id == SigningRequest.id)
                         .filter(SigningStep.signer_user_id == user.id, SigningStep.status != "signed",
                                 SigningRequest.owner_id != user.id, SigningRequest.status == "in_progress")
                         .scalar())
    signed_for_others = (db.query(func.count(func.distinct(SigningStep.request_id)))
                         .join(SigningRequest, SigningRequest.id == SigningStep.request_id)
                         .filter(SigningStep.signer_user_id == user.id, SigningStep.status == "signed",
                                 SigningRequest.owner_id != user.id).scalar())
    return {
        "email": user.email,
        "files": int(files[0] or 0),
        "storage_bytes": int(files[1] or 0),
        "requests_in_progress": int(owned.get("in_progress", 0)),
        "requests_total": int(sum(owned.values())),
        "pending_as_signer": int(pending_as_signer or 0),
        "signed_for_others": int(signed_for_others or 0),
        "passkeys": db.query(func.count(Passkey.id)).filter(Passkey.user_id == user.id).scalar() or 0,
        "line_linked": bool(user.line_user_id),
        "is_last_admin": _is_last_admin(db, user),
    }


def _remove(path) -> None:
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif path and os.path.exists(path):
            os.remove(path)
    except Exception:
        logger.warning("ลบไฟล์ไม่สำเร็จ: %s", path, exc_info=True)


def delete_account(db: Session, user: User, client: ClientInfo) -> dict:
    if _is_last_admin(db, user):
        raise AccountDeletionError("คุณเป็นผู้ดูแลระบบคนสุดท้าย — แต่งตั้งผู้ดูแลระบบคนอื่นก่อนจึงจะลบบัญชีได้", 409)
    user_id, email = user.id, user.email
    info = summary(db, user)

    counts = signing_service.release_deleted_user(db, user, client)
    user = db.get(User, user_id)

    # ไฟล์บนดิสก์
    owned_requests = [rid for (rid,) in db.query(SigningRequest.id).filter(SigningRequest.owner_id == user_id).all()]
    records = db.query(FileRecord).filter(FileRecord.user_id == user_id).all()
    record_ids = [r.id for r in records]
    task_filter = [ConversionTask.user_id == user_id]
    if record_ids:
        task_filter.append(ConversionTask.file_record_id.in_(record_ids))
    tasks = db.query(ConversionTask).filter(or_(*task_filter)).all()
    for record in records:
        for path in file_storage.all_existing_paths(record):
            _remove(path)
        try:
            session_manager.close(record.storage_path)
        except Exception:
            logger.warning("ปิด session %s ไม่สำเร็จ", record.storage_path, exc_info=True)
    for task in tasks:
        _remove(task.result_file_path)
    for rid in owned_requests:
        _remove(signing_service.request_dir(rid))
    _remove(settings.UPLOAD_DIR / "users" / str(user_id))

    # ฐานข้อมูล (ลบเองให้ครบ — ไม่พึ่ง ON DELETE CASCADE ซึ่ง SQLite ไม่บังคับ)
    for request in db.query(SigningRequest).filter(SigningRequest.owner_id == user_id).all():
        db.delete(request)  # steps ตามไปด้วย (cascade ใน ORM)
    db.flush()
    if owned_requests:
        db.query(SigningEvent).filter(SigningEvent.request_id.in_(owned_requests)).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.request_id.in_(owned_requests)).delete(synchronize_session=False)
    for task in tasks:
        db.delete(task)
    db.flush()
    for record in records:
        db.delete(record)
    db.query(Passkey).filter(Passkey.user_id == user_id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == user_id).delete(synchronize_session=False)
    db.query(AIUsageDaily).filter(AIUsageDaily.user_id == user_id).delete(synchronize_session=False)
    db.query(License).filter(License.used_by_user_id == user_id).update({License.used_by_user_id: None},
                                                                          synchronize_session=False)
    db.delete(user)
    db.commit()
    logger.info("ลบบัญชีผู้ใช้ %s แล้ว (ไฟล์ %d, คำขอลงนาม %d)", user_id, len(records), len(owned_requests))

    url = settings.FRONTEND_URL.rstrip("/")
    lines = [f"บัญชี {email} ถูกลบออกจาก {settings.APP_NAME} แล้ว พร้อมไฟล์และข้อมูลทั้งหมด",
             "หากคุณไม่ได้เป็นผู้ลบบัญชีนี้ กรุณาติดต่อผู้ดูแลระบบโดยเร็ว",
             f"ต้องการใช้งานอีกครั้ง สมัครใหม่ได้ที่ {url}"]
    mailer.send(mailer.Mail(to=email, subject=f"บัญชีของคุณถูกลบแล้ว - {settings.APP_NAME}",
                            text="\n".join(lines), html="".join(f"<p>{line}</p>" for line in lines)))
    return {**info, **counts}


def grants_initial_admin(db: Session, email: str) -> bool:
    """ผู้ใช้ใหม่คนนี้ควรเป็นผู้ดูแลระบบอัตโนมัติไหม — INITIAL_ADMIN_EMAILS ตั้งไว้: เฉพาะอีเมลในรายการ
    ไม่ตั้ง: ผู้ใช้คนแรกของระบบ (พฤติกรรมเดิม — เว็บเปิดสาธารณะแล้วคนนอกสมัครก่อนจะได้สิทธิ์ผู้ดูแล)"""
    from app.core.config import settings

    allowed = {e.strip().lower() for e in settings.INITIAL_ADMIN_EMAILS.split(",") if e.strip()}
    if allowed:
        return (email or "").strip().lower() in allowed
    return db.query(User).count() == 0


class SignupNotAllowed(Exception):
    """สร้างบัญชีใหม่ไม่ได้ตามนโยบายของระบบ (ALLOW_SELF_REGISTRATION / ALLOWED_EMAIL_DOMAINS) — ข้อความแสดงให้ผู้ใช้"""


def _has_signing_invite(db: Session, email: str) -> bool:
    return db.query(SigningStep.id).filter(SigningStep.signer_user_id.is_(None),
                                           SigningStep.invite_email == email).first() is not None


def email_domain_allowed(email: str) -> bool:
    domains = settings.ALLOWED_EMAIL_DOMAINS
    if not domains:
        return True
    domain = (email or "").strip().lower().rsplit("@", 1)[-1]
    return domain in domains


def check_new_account(db: Session, email: str) -> None:
    """ตรวจก่อนสร้างบัญชีใหม่ (สมัคร / Google / LINE ครั้งแรก) — raise SignupNotAllowed ถ้าไม่อนุญาต
    ยกเว้นเสมอ: อีเมลใน INITIAL_ADMIN_EMAILS (ตั้งผู้ดูแลคนแรกได้) และผู้ได้รับคำเชิญลงนามที่ยังไม่มีบัญชี"""
    email = (email or "").strip().lower()
    initial = {e.strip().lower() for e in settings.INITIAL_ADMIN_EMAILS.split(",") if e.strip()}
    if email in initial or _has_signing_invite(db, email):
        return
    if not settings.ALLOW_SELF_REGISTRATION:
        raise SignupNotAllowed("ระบบนี้ปิดการสมัครสมาชิกด้วยตนเอง — ติดต่อผู้ดูแลระบบขององค์กร")
    if not email_domain_allowed(email):
        allowed = ", ".join("@" + d for d in settings.ALLOWED_EMAIL_DOMAINS)
        raise SignupNotAllowed(f"สมัครได้เฉพาะอีเมลขององค์กร ({allowed})")
