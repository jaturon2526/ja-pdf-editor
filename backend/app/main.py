import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

import fitz  # PyMuPDF
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_admin,
    routes_annotation,
    routes_auth,
    routes_autogen,
    routes_config,
    routes_compare,
    routes_convert,
    routes_donations,
    routes_edit,
    routes_license,
    routes_line,
    routes_line_login,
    routes_passkey,
    routes_signature,
    routes_signing,
)
from app.api.pdf import router as pdf_router
from app.core.config import settings
from app.core.security import validate_secret_config
from app.core.heavy import ServerBusyError
from app.core.session import SessionBusyError, session_manager
from app.services import fonts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# ปิดการพ่น error/warning ดิบของ MuPDF ไปที่ stderr ตรงๆ แล้วให้ pdf_service ดึงข้อความเดียวกันมา log
# ผ่าน logging ของแอปแทน (ดู _flush_mupdf_warnings ใน app/services/pdf_service.py)
fitz.TOOLS.mupdf_display_errors(False)


def _cleanup_unreferenced_uploads() -> int:
    from app.db.database import SessionLocal
    from app.services import file_storage

    db = SessionLocal()
    try:
        active = set(getattr(session_manager, "_sessions", {}).keys())
        return file_storage.cleanup_unreferenced_files(db, active_ids=active)
    finally:
        db.close()


def _run_once_per_interval(name: str, seconds: float) -> bool:
    """งานเบื้องหลังที่ต้องทำครั้งเดียวทั้งระบบ (หลาย worker: BACKEND_WORKERS / หลายเครื่อง) — worker แรกที่จองได้ทำ
    ไม่มี Redis (worker เดียว) = ทำเสมอ"""
    from app.core.redis_client import get_redis

    r = get_redis()
    if r is None:
        return True
    try:
        return bool(r.set(f"bgjob:{name}", str(os.getpid()).encode(), nx=True, ex=max(5, int(seconds) - 5)))
    except Exception:
        logger.warning("bgjob: จอง %s ใน Redis ไม่สำเร็จ — ทำในเครื่องนี้", name)
        return True


async def _periodic_cleanup() -> None:
    """เก็บกวาด session/ไฟล์ที่ค้างเกิน SESSION_TTL_MINUTES เป็นระยะทุกๆ CLEANUP_INTERVAL_MINUTES นาที
    รันเป็น background task แยกจาก request loop · cleanup_expired ทำทุก worker (ปิดเอกสารที่เปิดค้างใน worker นั้น)
    ส่วนลบไฟล์ค้างบนดิสก์ทำ worker เดียว"""
    interval = max(1, settings.CLEANUP_INTERVAL_MINUTES) * 60
    while True:
        try:
            expired = session_manager.cleanup_expired()
            orphans = 0
            if _run_once_per_interval("cleanup-files", interval):
                orphans = session_manager.cleanup_orphan_files()
                orphans += _cleanup_unreferenced_uploads()
                orphans += routes_compare.cleanup_old_tasks()
            if expired or orphans:
                logger.info("cleanup: เคลียร์ session หมดอายุ %d รายการ, ไฟล์ค้าง %d ไฟล์", expired, orphans)
        except Exception:
            logger.exception("cleanup: เกิดข้อผิดพลาดระหว่างเก็บกวาดข้อมูลเก่า")
        await asyncio.sleep(interval)


def _check_signing_due_dates() -> None:
    from app.db.database import SessionLocal
    from app.services import signing_service

    db = SessionLocal()
    try:
        counts = signing_service.process_due_dates(db)
        if any(counts.values()):
            logger.info("signing: เตือนใกล้ครบกำหนด %d รายการ, เลยกำหนด %d รายการ", counts["due_soon"], counts["overdue"])
    finally:
        db.close()


def _check_quotas() -> None:
    from app.db.database import SessionLocal
    from app.services import quota_service

    with SessionLocal() as db:
        sent = quota_service.check_and_alert(db)
        if sent:
            logger.info("quota: แจ้งแอดมิน %d เรื่อง", sent)
    from app.services import donation_service

    with SessionLocal() as db:
        expired = donation_service.expire_plans(db)
        if expired:
            logger.info("plans: แพ็กเกจหมดอายุกลับเป็น free %d บัญชี", expired)


async def _periodic_quota_check() -> None:
    """ตรวจโควต้าบริการภายนอก + แจ้งแอดมินเมื่อใกล้เต็ม ทุก QUOTA_CHECK_INTERVAL_MINUTES นาที
    (เรียก Brevo API เป็นประจำ — key จึงไม่หมดอายุเพราะไม่ถูกใช้ 90 วัน)"""
    await asyncio.sleep(60)  # รอให้ระบบพร้อมก่อน
    interval = max(5, settings.QUOTA_CHECK_INTERVAL_MINUTES) * 60
    while True:
        try:
            if _run_once_per_interval("quota-check", interval):
                await run_in_threadpool(_check_quotas)
        except Exception:
            logger.exception("quota: ตรวจโควต้าไม่สำเร็จ")
        await asyncio.sleep(interval)


async def _periodic_signing_reminders() -> None:
    """เตือนคำขอลงนามที่ใกล้ครบกำหนด/เลยกำหนด ทุก SIGNING_CHECK_INTERVAL_MINUTES นาที"""
    interval = max(1, settings.SIGNING_CHECK_INTERVAL_MINUTES) * 60
    while True:
        try:
            if _run_once_per_interval("signing-due", interval):
                await run_in_threadpool(_check_signing_due_dates)
        except Exception:
            logger.exception("signing: ตรวจวันครบกำหนดไม่สำเร็จ")
        await asyncio.sleep(interval)


def _seed_plan_configs() -> None:
    from app.db.database import SessionLocal
    from app.models.domain import PlanConfig

    db = SessionLocal()
    try:
        if not db.query(PlanConfig).first():
            db.add_all([
                PlanConfig(plan_type="free", max_sessions=2, max_storage_mb=settings.DEFAULT_STORAGE_MB),
                PlanConfig(plan_type="pro", max_sessions=5, max_storage_mb=500),
                PlanConfig(plan_type="premium", max_sessions=10, max_storage_mb=1024),
            ])
            db.commit()
    except Exception:
        logger.exception("seed PlanConfig ไม่สำเร็จ")
    finally:
        db.close()


def _log_deployment_profile() -> None:
    """สรุปรูปแบบการติดตั้งใน log ตอนเริ่ม — ตรวจได้ทันทีว่า .env ถูกอ่านตามที่ตั้งใจ"""
    smtp = (f"{settings.SMTP_SERVER}:{settings.SMTP_PORT} ({settings.smtp_security}, "
            f"{'login' if settings.smtp_auth else 'no-auth'})" if settings.smtp_configured else "จำลอง (ไม่ได้ตั้งค่า)")
    logger.info("รูปแบบการติดตั้ง: %s · Google: %s · LINE: %s · สมัครเอง: %s · โดเมน: %s · SMTP: %s",
                settings.DEPLOYMENT_PROFILE, "เปิด" if settings.google_enabled else "ปิด",
                "เปิด" if (settings.line_login_enabled or settings.line_enabled) else "ปิด",
                "ได้" if settings.ALLOW_SELF_REGISTRATION else "ไม่ได้",
                ",".join(settings.ALLOWED_EMAIL_DOMAINS) or "ทุกโดเมน", smtp)
    if settings.is_onprem and not settings.SMTP_FROM:
        logger.warning("onprem: ยังไม่ได้ตั้ง SMTP_FROM — อีเมลยืนยัน/รีเซ็ตรหัสผ่านอาจส่งไม่ออก (ตั้งเป็นอีเมลของโดเมนองค์กร)")
    if settings.is_onprem and not settings.FRONTEND_URL.startswith("https://"):
        logger.warning("onprem: FRONTEND_URL ไม่ใช่ https — passkey ใช้ได้เฉพาะเว็บ https (ยกเว้น localhost)")


def _warn_open_admin_signup() -> None:
    """ระบบยังไม่มีผู้ใช้ และไม่ได้ตั้ง INITIAL_ADMIN_EMAILS — ใครสมัครก่อนได้สิทธิ์ผู้ดูแลระบบ"""
    from app.db.database import SessionLocal
    from app.models.domain import User

    if settings.INITIAL_ADMIN_EMAILS.strip():
        return
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            logger.warning("ยังไม่มีผู้ใช้ในระบบ และไม่ได้ตั้ง INITIAL_ADMIN_EMAILS — ผู้ที่สมัครคนแรกจะได้สิทธิ์ผู้ดูแลระบบ "
                           "(ตั้ง INITIAL_ADMIN_EMAILS=อีเมลของคุณ ใน .env ก่อนเปิดเว็บสาธารณะ)")
    except Exception:
        logger.debug("ตรวจผู้ใช้คนแรกไม่สำเร็จ", exc_info=True)
    finally:
        db.close()


def _check_frontend_url() -> None:
    """FRONTEND_URL ใช้สร้างลิงก์ในอีเมล — เตือนถ้าค่าดูผิด เช่นบรรทัดใน .env ติดกับบรรทัดถัดไป (ไม่พิมพ์ค่าออกมา)"""
    from urllib.parse import urlparse

    url = settings.FRONTEND_URL or ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(c in url for c in "= \t"):
        logger.warning("FRONTEND_URL ดูไม่ถูกต้อง (ลิงก์ในอีเมลจะใช้ไม่ได้) — ตรวจว่าใน .env เป็น "
                       "FRONTEND_URL=http://host:port บรรทัดเดียว ไม่ติดกับค่าอื่น")


def _log_signing_seal() -> None:
    """บอกใน log ว่าลายเซ็นอิเล็กทรอนิกส์ใช้ใบรับรองไหน — ตั้ง SIGNING_SEAL_P12 ผิดจะเห็นตั้งแต่ตอน start"""
    try:
        from app.services import signing_pdf

        info = signing_pdf.seal_info()
        logger.info("ใบรับรองระบบสำหรับลงนาม: %s (ออกโดย %s, หมดอายุ %s, แหล่ง %s)",
                    info["subject"], info["issuer"], info["not_after"][:10], info["source"])
        for warning in info["warnings"]:
            logger.warning("ใบรับรองระบบสำหรับลงนาม: %s", warning)
    except Exception as exc:
        logger.error("ใบรับรองระบบสำหรับลงนามใช้งานไม่ได้: %s", exc)


def _warm_up_thai() -> None:
    try:
        from app.services import thai_text

        thai_text.dictionary_coverage("ทดสอบการตัดคำภาษาไทย")
    except Exception:  # pragma: no cover — ไม่มี pythainlp ก็ยังทำงานต่อได้
        logging.getLogger("thai_text").warning("โหลดพจนานุกรมภาษาไทยไม่สำเร็จ", exc_info=True)


def _check_thai_shaping() -> None:
    """เครื่องจัดรูปอักษรไทย: fpdf2 ใช้ uharfbuzz (ข้อความที่แก้/แทรก) · Pillow ใช้ RAQM (ข้อความบนตราลายเซ็นดิจิทัล)
    ถ้าขาดตัวใดตัวหนึ่ง สระ/วรรณยุกต์จะวางผิดตำแหน่งแบบเงียบ ๆ — เตือนใน log ตั้งแต่ตอน start"""
    try:
        from PIL import features

        if not features.check("raqm"):
            logger.warning("Pillow ไม่มี RAQM — ข้อความไทยบนตราลายเซ็นดิจิทัลจะวางสระ/วรรณยุกต์ผิดตำแหน่ง "
                           "(ติดตั้ง Pillow wheel ทางการ หรือ libraqm + libfribidi)")
        import uharfbuzz  # noqa: F401
    except ImportError:
        logger.warning("ไม่มี uharfbuzz — fpdf2 จัดรูปอักษรไทยไม่ได้ (pip install uharfbuzz)")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_secret_config()
    _check_frontend_url()
    _check_thai_shaping()
    settings.ensure_dirs()

    # สร้าง/อัปเกรด schema ฐานข้อมูลผ่าน Alembic (ดู app/db/migrations.py)
    from app.db.migrations import run_migrations

    run_migrations()
    _seed_plan_configs()
    _log_deployment_profile()
    _warn_open_admin_signup()
    _log_signing_seal()

    # ดาวน์โหลดฟอนต์ไทยเพิ่มเติมจาก Google Fonts แบบ best-effort ใน thread แยก (ไม่บล็อกการ start
    # ถ้าไม่มีเน็ต/เน็ตช้า — ครั้งถัดไปจะใช้ไฟล์ที่ cache ไว้)
    threading.Thread(target=fonts.sync_google_fonts, daemon=True).start()
    threading.Thread(target=_warm_up_thai, daemon=True).start()  # โหลดพจนานุกรมไทยไว้ก่อน ไม่ให้คำขอแรกช้า
    tasks = []
    if settings.BACKGROUND_JOBS:
        tasks = [asyncio.create_task(job()) for job in (_periodic_cleanup, _periodic_signing_reminders, _periodic_quota_check)]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()


app = FastAPI(
    title="PDF Editor API",
    description="Backend สำหรับ PDF Editor Web App — เปิด/ปลดล็อกรหัสผ่าน, annotation, แก้ไขข้อความ/รูปภาพ",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_admin.router)
app.include_router(routes_passkey.router, prefix="/auth/passkeys", tags=["auth"])
app.include_router(routes_auth.router, prefix="/auth", tags=["auth"])
app.include_router(routes_license.router, prefix="/license", tags=["license"])
app.include_router(pdf_router)
app.include_router(routes_annotation.router)
app.include_router(routes_edit.router)
app.include_router(routes_signature.router)
app.include_router(routes_autogen.router)
app.include_router(routes_convert.router)
app.include_router(routes_compare.router)
app.include_router(routes_signing.router)
app.include_router(routes_signing.notifications_router)
app.include_router(routes_line.router)
app.include_router(routes_line_login.router)
app.include_router(routes_config.router)
app.include_router(routes_donations.router)


@app.exception_handler(ServerBusyError)
async def _server_busy_handler(_request: Request, exc: ServerBusyError):
    # คิวงานหนัก (Ghostscript/LibreOffice/OCR) เต็ม — ให้ลองใหม่ภายหลัง (ดู app/core/heavy.py)
    return JSONResponse(status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "30"})


@app.exception_handler(SessionBusyError)
async def _session_busy_handler(_request: Request, exc: SessionBusyError):
    # มีคำขออื่น (หรือ pod อื่น) กำลังแก้ไขเอกสารเดียวกันอยู่นานเกินกำหนด — ให้ frontend ลองใหม่
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
def health():
    return {"status": "ok"}
