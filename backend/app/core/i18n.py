"""ระบบแปลภาษาฝั่ง Backend (i18n) สำหรับอีเมล, LINE และแจ้งเตือนในระบบ (Notification)

รองรับภาษาไทย ('th' — ค่าเริ่มต้น) และอังกฤษ ('en') โดยอ่านจาก user.language หรือ header Accept-Language
"""
from __future__ import annotations

from typing import Any

DEFAULT_LANG = "th"
SUPPORTED_LANGUAGES = ("th", "en")

_MESSAGES: dict[str, dict[str, str]] = {
    "th": {
        # ---- Auth emails ----
        "email.greeting": "สวัสดีครับ,",
        "email.fallback_link": "หากปุ่มคลิกไม่ได้ สามารถคัดลอกลิงก์ด้านล่างไปวางในเบราว์เซอร์ได้เลยครับ:",
        "email.verify.subject": "ยืนยันอีเมลของคุณ - {app_name}",
        "email.verify.line1": "ขอบคุณที่สมัครสมาชิกเพื่อใช้งาน {app_name}",
        "email.verify.line2": "กรุณาคลิกปุ่มด้านล่างเพื่อยืนยันที่อยู่อีเมลของคุณ และเริ่มต้นใช้งาน",
        "email.verify.button": "ยืนยันอีเมลของฉัน",
        "email.verify.footer": "หากคุณไม่ได้เป็นผู้สมัครสมาชิก กรุณาละเว้นอีเมลฉบับนี้ (ลิงก์มีอายุ 24 ชั่วโมง)",
        "email.reset.subject": "ตั้งรหัสผ่านใหม่ (Reset Password) - {app_name}",
        "email.reset.line1": "มีการร้องขอเพื่อตั้งรหัสผ่านใหม่สำหรับบัญชีของคุณ",
        "email.reset.line2": "กรุณาคลิกปุ่มด้านล่างเพื่อตั้งรหัสผ่านใหม่ (ลิงก์มีอายุ 1 ชั่วโมง)",
        "email.reset.button": "ตั้งรหัสผ่านใหม่",
        "email.reset.footer": "หากคุณไม่ได้ทำการร้องขอ โปรดละเว้นอีเมลฉบับนี้",
        "email.line_confirm.subject": "ยืนยันอีเมลเพื่อเข้าสู่ระบบด้วย LINE - {app_name}",
        "email.line_confirm.line1": "มีการเข้าสู่ระบบด้วย LINE และระบุอีเมลนี้เป็นอีเมลของบัญชี",
        "email.line_confirm.line2": "กดปุ่มด้านล่างเพื่อยืนยันอีเมลและเข้าสู่ระบบ (ลิงก์มีอายุ 30 นาที ใช้ได้ครั้งเดียว)",
        "email.line_confirm.line3": "ถ้าอีเมลนี้มีบัญชีอยู่แล้ว บัญชี LINE จะถูกเชื่อมกับบัญชีเดิม",
        "email.line_confirm.button": "ยืนยันอีเมลและเข้าสู่ระบบ",
        "email.line_confirm.footer": "หากคุณไม่ได้ทำรายการนี้ โปรดละเว้นอีเมลฉบับนี้ — จะไม่มีอะไรเปลี่ยนแปลง",
        # ---- Signing emails & LINE ----
        "signing.subject.sign_turn": "ถึงคิวคุณลงนาม: {title}",
        "signing.subject.sign_reminder": "เตือน: รอคุณลงนาม \"{title}\"",
        "signing.subject.sign_rejected": "มีผู้ปฏิเสธการลงนาม: {title}",
        "signing.subject.sign_completed": "ลงนามครบทุกคนแล้ว: {title}",
        "signing.subject.sign_cancelled": "ยกเลิกคำขอลงนาม: {title}",
        "signing.subject.sign_overdue": "เลยกำหนดลงนาม: {title}",
        "signing.subject.sign_invite": "คุณได้รับเชิญให้ลงนามเอกสาร: {title}",
        "signing.button.sign_turn": "เปิดเอกสารเพื่อลงนาม",
        "signing.button.sign_reminder": "เปิดเอกสารเพื่อลงนาม",
        "signing.button.sign_completed": "ดูเอกสารที่ลงนามแล้ว",
        "signing.button.sign_invite": "สมัครสมาชิกเพื่อลงนาม",
        "signing.button.default": "เปิดคำขอลงนาม",
        "signing.greeting": "เรียน {name}",
        "signing.sender_message": "ข้อความจากผู้ส่ง: {message}",
        "signing.due_at": "ครบกำหนด: {due}",
        "signing.open_link": "เปิดดู: {url}",
        "signing.link_label": "ลิงก์:",
        "signing.footer_auto": "อีเมลนี้ส่งอัตโนมัติจาก {app_name}",
        "signing.footer_auto_short": "อีเมลนี้ส่งอัตโนมัติ",
        "signing.footer_disable": " — ปิดการรับอีเมลแจ้งเตือนได้ที่หน้า \"การลงนาม\"",
        "signing.login_note.invite": "สมัครด้วยอีเมลนี้เท่านั้น ระบบจึงจะผูกเอกสารกับบัญชีของคุณ",
        "signing.login_note.default": "ต้องเข้าสู่ระบบด้วยบัญชีของคุณก่อนเปิดเอกสาร",
        # ---- Donations & Plan Notifications ----
        "donation.approved": "ขอบคุณที่สนับสนุน {amount} บาท{perk}",
        "donation.approved_perk": " — ได้รับสิทธิ์ {plan} {days} วัน",
        "donation.rejected": "ไม่พบยอดโอนที่แจ้งไว้{reason} — ติดต่อผู้ดูแลระบบได้",
        "donation.plan_expired": "สิทธิ์ผู้สนับสนุน ({plan}) ครบกำหนดแล้ว — ขอบคุณที่ร่วมสนับสนุน",
    },
    "en": {
        # ---- Auth emails ----
        "email.greeting": "Hello,",
        "email.fallback_link": "If the button does not work, copy and paste the link below into your browser:",
        "email.verify.subject": "Verify your email - {app_name}",
        "email.verify.line1": "Thank you for signing up for {app_name}.",
        "email.verify.line2": "Please click the button below to verify your email address and get started.",
        "email.verify.button": "Verify My Email",
        "email.verify.footer": "If you did not create an account, you can safely ignore this email (link expires in 24 hours).",
        "email.reset.subject": "Reset Password - {app_name}",
        "email.reset.line1": "We received a request to reset the password for your account.",
        "email.reset.line2": "Please click the button below to set a new password (link expires in 1 hour).",
        "email.reset.button": "Reset Password",
        "email.reset.footer": "If you did not request a password reset, please ignore this email.",
        "email.line_confirm.subject": "Confirm email for LINE Sign-In - {app_name}",
        "email.line_confirm.line1": "Someone signed in with LINE and entered this email address.",
        "email.line_confirm.line2": "Click the button below to confirm your email and sign in (link expires in 30 minutes, single use).",
        "email.line_confirm.line3": "If an account already exists with this email, your LINE account will be linked to it.",
        "email.line_confirm.button": "Confirm Email & Sign In",
        "email.line_confirm.footer": "If you did not initiate this request, you can ignore this email — nothing will change.",
        # ---- Signing emails & LINE ----
        "signing.subject.sign_turn": "Your turn to sign: {title}",
        "signing.subject.sign_reminder": "Reminder: Waiting for your signature on \"{title}\"",
        "signing.subject.sign_rejected": "Signing request declined: {title}",
        "signing.subject.sign_completed": "All signatures completed: {title}",
        "signing.subject.sign_cancelled": "Signing request cancelled: {title}",
        "signing.subject.sign_overdue": "Signing request overdue: {title}",
        "signing.subject.sign_invite": "You are invited to sign: {title}",
        "signing.button.sign_turn": "Open Document to Sign",
        "signing.button.sign_reminder": "Open Document to Sign",
        "signing.button.sign_completed": "View Signed Document",
        "signing.button.sign_invite": "Sign Up to Sign Document",
        "signing.button.default": "Open Signing Request",
        "signing.greeting": "Dear {name},",
        "signing.sender_message": "Message from sender: {message}",
        "signing.due_at": "Due date: {due}",
        "signing.open_link": "Open: {url}",
        "signing.link_label": "Link:",
        "signing.footer_auto": "This is an automated email from {app_name}",
        "signing.footer_auto_short": "This is an automated email",
        "signing.footer_disable": " — You can disable email notifications on the \"Signing\" page",
        "signing.login_note.invite": "Please register with this exact email address so the document links to your account.",
        "signing.login_note.default": "Please sign in with your account to open the document.",
        # ---- Donations & Plan Notifications ----
        "donation.approved": "Thank you for supporting {amount} THB{perk}",
        "donation.approved_perk": " — {plan} plan granted for {days} days",
        "donation.rejected": "Transfer could not be verified{reason} — please contact support",
        "donation.plan_expired": "Your supporter plan ({plan}) has expired — thank you for your support",
    },
}


def normalize_lang(value: str | None) -> str:
    """แปลงรหัสภาษาหรือ Accept-Language header เป็น 'th' หรือ 'en'"""
    if not value or not isinstance(value, str):
        return DEFAULT_LANG
    for part in value.split(","):
        code = part.split(";")[0].strip().lower().split("-")[0]
        if code in SUPPORTED_LANGUAGES:
            return code
    return DEFAULT_LANG


def user_lang(user: Any) -> str:
    return normalize_lang(getattr(user, "language", None))


def request_lang(request: Any, user: Any = None) -> str:
    if user is not None and getattr(user, "language", None):
        return user_lang(user)
    if request is not None:
        header = request.headers.get("accept-language") if hasattr(request, "headers") else None
        if header:
            return normalize_lang(header)
    return DEFAULT_LANG


def t(lang: str | None, key: str, **params: Any) -> str:
    code = normalize_lang(lang)
    template = _MESSAGES.get(code, {}).get(key) or _MESSAGES[DEFAULT_LANG].get(key) or key
    return template.format(**params) if params else template
