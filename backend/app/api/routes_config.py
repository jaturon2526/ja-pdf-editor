"""ค่าคอนฟิกที่หน้าเว็บต้องรู้ก่อนเข้าสู่ระบบ (ไม่ต้อง login) — ปุ่ม Google/LINE, การสมัครสมาชิก, โดเมนอีเมลที่สมัครได้

frontend โหลดตอนเปิดแอป แทนการฝังค่าตอน build (VITE_GOOGLE_CLIENT_ID) — image เดียวกันใช้ได้ทั้ง public และ onprem
ห้ามใส่ค่าลับในนี้ (ทุกคนอ่านได้)
"""
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["config"])


@router.get("/config/public")
def public_config():
    return {
        "app_name": settings.APP_NAME,
        "profile": settings.DEPLOYMENT_PROFILE,
        "google_client_id": settings.GOOGLE_CLIENT_ID if settings.google_enabled else None,
        "line_login": settings.line_login_enabled,
        "self_registration": settings.ALLOW_SELF_REGISTRATION,
        "allowed_email_domains": settings.ALLOWED_EMAIL_DOMAINS,
        "source_url": settings.SOURCE_CODE_URL,
        "license": "AGPL-3.0-or-later",
    }
