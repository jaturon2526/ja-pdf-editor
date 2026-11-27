"""อีเมลยืนยันตัวตน (ยืนยันอีเมลตอนสมัคร / ตั้งรหัสผ่านใหม่) — ส่งผ่าน mailer เหมือนอีเมลแจ้งเตือนการลงนาม

From ใช้ SMTP_FROM (ไม่ตั้ง = SMTP_USERNAME) ผ่าน mailer เสมอ — เดิมไฟล์นี้ตั้ง From เป็น SMTP_USERNAME เอง
ใช้ได้กับ Gmail แต่บริการส่งอีเมล (เช่น Brevo) ที่ login เป็น xxx@smtp-brevo.com จะไม่ส่งให้ เพราะไม่ใช่ผู้ส่งที่ยืนยันแล้ว
ส่งแบบรอผล (ไม่ใช่เบื้องหลัง) เพราะ /auth/resend-verification ต้องรู้ว่าส่งสำเร็จไหม
"""
import html
import logging

from app.core.config import settings
from app.core.i18n import t as i18n_t
from app.services import mailer

logger = logging.getLogger("mailer")


def _layout(heading_lines: list[str], button_text: str, url: str, footer: str, lang: str = "th") -> str:
    esc = html.escape
    paragraphs = "".join(f"<p>{esc(line)}</p>" for line in heading_lines)
    greeting = i18n_t(lang, "email.greeting")
    fallback = i18n_t(lang, "email.fallback_link")
    return f"""<html><body style="font-family:Arial,sans-serif;color:#333;line-height:1.6;padding:20px">
<div style="max-width:600px;margin:0 auto;background:#fff;border:1px solid #ddd;border-radius:8px;padding:30px">
<h2 style="color:#2563eb;text-align:center;margin-bottom:20px">{esc(settings.APP_NAME)}</h2>
<p>{esc(greeting)}</p>
{paragraphs}
<div style="text-align:center;margin:30px 0"><a href="{esc(url)}" style="background-color:#2563eb;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block">{esc(button_text)}</a></div>
<p style="font-size:14px;color:#666">{esc(fallback)}<br><a href="{esc(url)}" style="color:#2563eb">{esc(url)}</a></p>
<p style="margin-top:30px;font-size:13px;color:#999">{esc(footer)}</p>
</div></body></html>"""


def _send(to_email: str, subject: str, lines: list[str], button: str, url: str, footer: str, lang: str = "th") -> bool:
    greeting = i18n_t(lang, "email.greeting")
    text = "\n".join([greeting, "", *lines, "", f"{button}: {url}", "", footer])
    return mailer.send_now(mailer.Mail(to=to_email, subject=subject, text=text,
                                       html=_layout(lines, button, url, footer, lang=lang)))


def send_verification_email(to_email: str, token: str, lang: str = "th") -> bool:
    verify_url = f"{settings.FRONTEND_URL.rstrip('/')}/api/auth/verify-email?token={token}"
    return _send(
        to_email,
        i18n_t(lang, "email.verify.subject", app_name=settings.APP_NAME),
        [i18n_t(lang, "email.verify.line1", app_name=settings.APP_NAME),
         i18n_t(lang, "email.verify.line2")],
        i18n_t(lang, "email.verify.button"),
        verify_url,
        i18n_t(lang, "email.verify.footer"),
        lang=lang,
    )


def send_reset_password_email(to_email: str, reset_link: str, lang: str = "th") -> bool:
    return _send(
        to_email,
        i18n_t(lang, "email.reset.subject", app_name=settings.APP_NAME),
        [i18n_t(lang, "email.reset.line1"),
         i18n_t(lang, "email.reset.line2")],
        i18n_t(lang, "email.reset.button"),
        reset_link,
        i18n_t(lang, "email.reset.footer"),
        lang=lang,
    )


def send_line_login_confirm_email(to_email: str, confirm_link: str, lang: str = "th") -> bool:
    return _send(
        to_email,
        i18n_t(lang, "email.line_confirm.subject", app_name=settings.APP_NAME),
        [i18n_t(lang, "email.line_confirm.line1"),
         i18n_t(lang, "email.line_confirm.line2"),
         i18n_t(lang, "email.line_confirm.line3")],
        i18n_t(lang, "email.line_confirm.button"),
        confirm_link,
        i18n_t(lang, "email.line_confirm.footer"),
        lang=lang,
    )
