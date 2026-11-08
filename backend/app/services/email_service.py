"""อีเมลยืนยันตัวตน (ยืนยันอีเมลตอนสมัคร / ตั้งรหัสผ่านใหม่) — ส่งผ่าน mailer เหมือนอีเมลแจ้งเตือนการลงนาม

From ใช้ SMTP_FROM (ไม่ตั้ง = SMTP_USERNAME) ผ่าน mailer เสมอ — เดิมไฟล์นี้ตั้ง From เป็น SMTP_USERNAME เอง
ใช้ได้กับ Gmail แต่บริการส่งอีเมล (เช่น Brevo) ที่ login เป็น xxx@smtp-brevo.com จะไม่ส่งให้ เพราะไม่ใช่ผู้ส่งที่ยืนยันแล้ว
ส่งแบบรอผล (ไม่ใช่เบื้องหลัง) เพราะ /auth/resend-verification ต้องรู้ว่าส่งสำเร็จไหม
"""
import html
import logging

from app.core.config import settings
from app.services import mailer

logger = logging.getLogger("mailer")


def _layout(heading_lines: list[str], button_text: str, url: str, footer: str) -> str:
    esc = html.escape
    paragraphs = "".join(f"<p>{esc(line)}</p>" for line in heading_lines)
    return f"""<html><body style="font-family:Arial,sans-serif;color:#333;line-height:1.6;padding:20px">
<div style="max-width:600px;margin:0 auto;background:#fff;border:1px solid #ddd;border-radius:8px;padding:30px">
<h2 style="color:#2563eb;text-align:center;margin-bottom:20px">{esc(settings.APP_NAME)}</h2>
<p>สวัสดีครับ,</p>
{paragraphs}
<div style="text-align:center;margin:30px 0"><a href="{esc(url)}" style="background-color:#2563eb;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block">{esc(button_text)}</a></div>
<p style="font-size:14px;color:#666">หากปุ่มคลิกไม่ได้ สามารถคัดลอกลิงก์ด้านล่างไปวางในเบราว์เซอร์ได้เลยครับ:<br><a href="{esc(url)}" style="color:#2563eb">{esc(url)}</a></p>
<p style="margin-top:30px;font-size:13px;color:#999">{esc(footer)}</p>
</div></body></html>"""


def _send(to_email: str, subject: str, lines: list[str], button: str, url: str, footer: str) -> bool:
    text = "\n".join(["สวัสดีครับ,", "", *lines, "", f"{button}: {url}", "", footer])
    return mailer.send_now(mailer.Mail(to=to_email, subject=subject, text=text,
                                       html=_layout(lines, button, url, footer)))


def send_verification_email(to_email: str, token: str) -> bool:
    verify_url = f"{settings.FRONTEND_URL.rstrip('/')}/api/auth/verify-email?token={token}"
    return _send(
        to_email,
        f"ยืนยันอีเมลของคุณ - {settings.APP_NAME}",
        [f"ขอบคุณที่สมัครสมาชิกเพื่อใช้งาน {settings.APP_NAME}",
         "กรุณาคลิกปุ่มด้านล่างเพื่อยืนยันที่อยู่อีเมลของคุณ และเริ่มต้นใช้งาน"],
        "ยืนยันอีเมลของฉัน",
        verify_url,
        "หากคุณไม่ได้เป็นผู้สมัครสมาชิก กรุณาละเว้นอีเมลฉบับนี้ (ลิงก์มีอายุ 24 ชั่วโมง)",
    )


def send_reset_password_email(to_email: str, reset_link: str) -> bool:
    return _send(
        to_email,
        f"ตั้งรหัสผ่านใหม่ (Reset Password) - {settings.APP_NAME}",
        ["มีการร้องขอเพื่อตั้งรหัสผ่านใหม่สำหรับบัญชีของคุณ",
         "กรุณาคลิกปุ่มด้านล่างเพื่อตั้งรหัสผ่านใหม่ (ลิงก์มีอายุ 1 ชั่วโมง)"],
        "ตั้งรหัสผ่านใหม่",
        reset_link,
        "หากคุณไม่ได้ทำการร้องขอ โปรดละเว้นอีเมลฉบับนี้",
    )


def send_line_login_confirm_email(to_email: str, confirm_link: str) -> bool:
    return _send(
        to_email,
        f"ยืนยันอีเมลเพื่อเข้าสู่ระบบด้วย LINE - {settings.APP_NAME}",
        ["มีการเข้าสู่ระบบด้วย LINE และระบุอีเมลนี้เป็นอีเมลของบัญชี",
         "กดปุ่มด้านล่างเพื่อยืนยันอีเมลและเข้าสู่ระบบ (ลิงก์มีอายุ 30 นาที ใช้ได้ครั้งเดียว)",
         "ถ้าอีเมลนี้มีบัญชีอยู่แล้ว บัญชี LINE จะถูกเชื่อมกับบัญชีเดิม"],
        "ยืนยันอีเมลและเข้าสู่ระบบ",
        confirm_link,
        "หากคุณไม่ได้ทำรายการนี้ โปรดละเว้นอีเมลฉบับนี้ — จะไม่มีอะไรเปลี่ยนแปลง",
    )
