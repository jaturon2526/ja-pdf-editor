"""ส่งอีเมลของระบบแบบไม่บล็อก request (thread pool) — ไม่มีค่า SMTP จะพิมพ์ลง log แทน (โหมดจำลอง)

ใช้กับอีเมลแจ้งเตือนการลงนาม: From เป็นที่อยู่ของระบบเสมอ (ส่งในนามโดเมนของผู้ใช้ไม่ได้ — SPF/DKIM/DMARC)
แต่ชื่อผู้ส่งแสดงเป็น "ชื่อผู้ใช้ ผ่าน JA PDF Editor" และ Reply-To เป็นอีเมลของผู้ใช้คนนั้น ตอบกลับแล้วถึงตัวคน
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Callable, Optional

from app.core.config import settings

logger = logging.getLogger("mailer")

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mailer")


@dataclass
class Mail:
    to: str
    subject: str
    text: str
    html: str
    reply_to: Optional[str] = None
    sender_name: Optional[str] = None  # ชื่อคนที่ทำให้เกิดอีเมลนี้ (แสดงเป็น "... ผ่าน JA PDF Editor")


def _from_address() -> Optional[str]:
    return settings.SMTP_FROM or settings.SMTP_USERNAME


def build_message(mail: Mail) -> EmailMessage:
    msg = EmailMessage()
    display = f"{mail.sender_name} ผ่าน {settings.APP_NAME}" if mail.sender_name else settings.APP_NAME
    msg["From"] = formataddr((display, _from_address() or "no-reply@localhost"))
    msg["To"] = mail.to
    if mail.reply_to:
        msg["Reply-To"] = mail.reply_to
    msg["Subject"] = mail.subject
    msg.set_content(mail.text)
    msg.add_alternative(mail.html, subtype="html")
    return msg


def _ssl_context() -> ssl.SSLContext:
    """ตรวจใบรับรองของ mail server เสมอ — SMTP_CA_FILE = CA ขององค์กร (mail server ภายในที่ใช้ใบรับรองขององค์กรเอง)"""
    return ssl.create_default_context(cafile=settings.SMTP_CA_FILE) if settings.SMTP_CA_FILE else ssl.create_default_context()


def _send_now(mail: Mail) -> bool:
    if not settings.smtp_configured:
        logger.info("[EMAIL SIMULATION] ถึง %s | %s\n%s", mail.to, mail.subject, mail.text)
        return False
    try:
        msg = build_message(mail)
        # ssl = SMTP over SSL ตั้งแต่ต้น (พอร์ต 465) · starttls = เริ่มแบบธรรมดาแล้วยกระดับ (587) · none = relay ภายใน (25)
        security = settings.smtp_security
        if security == "ssl":
            server_cm = smtplib.SMTP_SSL(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=20, context=_ssl_context())
        else:
            server_cm = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=20)
        with server_cm as server:
            if security == "starttls":
                server.starttls(context=_ssl_context())
            if settings.smtp_auth:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("ส่งอีเมลถึง %s แล้ว: %s", mail.to, mail.subject)
        from app.services import quota_service  # นับรายวันสำหรับหน้าโควต้าของแอดมิน

        quota_service.record(quota_service.EMAIL)
        return True
    except Exception:
        logger.exception("ส่งอีเมลถึง %s ไม่สำเร็จ", mail.to)
        return False


def send_now(mail: Mail) -> bool:
    """ส่งทันทีแบบรอผล (อีเมลยืนยันตัวตน) — คืน True ถ้าส่งสำเร็จ ไม่ raise"""
    return _send_now(mail)


# เทสต์แทนที่ตัวนี้เพื่อเก็บอีเมลไว้ตรวจ แทนการส่งจริง
deliver: Callable[[Mail], object] = lambda mail: _executor.submit(_send_now, mail)  # noqa: E731


def send(mail: Mail) -> None:
    """ส่งเบื้องหลัง — ไม่ raise (อีเมลล้มเหลวต้องไม่ทำให้การลงนามล้ม)"""
    try:
        deliver(mail)
    except Exception:  # pragma: no cover
        logger.exception("เข้าคิวอีเมลไม่สำเร็จ")


