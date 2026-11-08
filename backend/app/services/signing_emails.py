"""อีเมลแจ้งเตือนการลงนาม (เฟส 2) — สร้างเนื้อหาอีเมลตามชนิดแจ้งเตือน แล้วส่งผ่าน mailer หลัง commit

- ส่งเฉพาะผู้ใช้ที่เปิดรับอีเมล (User.signing_email_notifications) — แจ้งเตือนในระบบยังได้เสมอ
- ผู้ใช้ที่เชื่อม LINE และเปิดรับทาง LINE → ส่ง LINE แทนอีเมล (LINE ล้มเหลว/โควตาหมด → ส่งอีเมลแทนถ้าเปิดรับอีเมล)
  "ลงนามครบแล้ว" ส่ง LINE เฉพาะผู้ส่งเอกสาร (ประหยัดโควตา) ผู้ลงนามเห็นในแจ้งเตือนในระบบ
- ในอีเมลมีแค่ลิงก์ไปหน้าคำขอ (ต้อง login ก่อนเปิดเอกสาร) ไม่แนบไฟล์
- From = ที่อยู่ของระบบ, ชื่อผู้ส่ง = "ชื่อคนที่ทำให้เกิดเหตุการณ์ ผ่าน JA PDF Editor", Reply-To = อีเมลคนนั้น
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import SigningRequest, User
from app.services import line_service, mailer

# ชนิดแจ้งเตือนที่ส่งอีเมลด้วย (sign_progress = มีคนลงนามแล้วแต่ยังไม่ครบ → แจ้งในระบบอย่างเดียว ไม่รบกวนอีเมล)
EMAIL_KINDS = {"sign_turn", "sign_reminder", "sign_rejected", "sign_completed", "sign_cancelled", "sign_overdue",
               "sign_invite"}

_SUBJECTS = {
    "sign_turn": "ถึงคิวคุณลงนาม: {title}",
    "sign_reminder": "เตือน: รอคุณลงนาม \"{title}\"",
    "sign_rejected": "มีผู้ปฏิเสธการลงนาม: {title}",
    "sign_completed": "ลงนามครบทุกคนแล้ว: {title}",
    "sign_cancelled": "ยกเลิกคำขอลงนาม: {title}",
    "sign_overdue": "เลยกำหนดลงนาม: {title}",
    "sign_invite": "คุณได้รับเชิญให้ลงนามเอกสาร: {title}",
}

_BUTTON = {
    "sign_turn": "เปิดเอกสารเพื่อลงนาม",
    "sign_reminder": "เปิดเอกสารเพื่อลงนาม",
    "sign_completed": "ดูเอกสารที่ลงนามแล้ว",
    "sign_invite": "สมัครสมาชิกเพื่อลงนาม",
}


@dataclass
class OutgoingEmail:
    user_id: Optional[int]  # None = ผู้ถูกเชิญที่ยังไม่มีบัญชี (ส่งไปที่ to_email)
    kind: str
    request_id: int
    title: str  # ข้อความแจ้งเตือน (บรรทัดหลักในอีเมล)
    actor_id: Optional[int] = None  # คนที่ทำให้เกิดเหตุการณ์ → ชื่อผู้ส่ง + Reply-To
    lines: list[str] = field(default_factory=list)  # รายละเอียดเพิ่ม เช่น เหตุผลที่ปฏิเสธ, วันครบกำหนด
    to_email: Optional[str] = None


def queue(db: Session, item: OutgoingEmail) -> None:
    """เก็บไว้ส่งหลัง db.commit() สำเร็จ (ไม่ส่งอีเมลถ้าธุรกรรมถูก rollback)"""
    if item.kind in EMAIL_KINDS:
        db.info.setdefault("signing_outbox", []).append(item)


def discard(db: Session) -> None:
    db.info.pop("signing_outbox", None)


def request_url(request_id: int) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/signing/{request_id}"


def register_url(email: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/login?register=1&email={quote(email)}"


def format_due(due_at) -> str:
    if due_at is None:
        return ""
    try:
        from zoneinfo import ZoneInfo

        local = due_at.astimezone(ZoneInfo(settings.APP_TIMEZONE))
    except Exception:
        local = due_at
    return local.strftime("%d/%m/%Y %H:%M")


def _details(item: OutgoingEmail, request: SigningRequest) -> list[str]:
    details = list(item.lines)
    if request.message and item.kind in ("sign_turn", "sign_reminder", "sign_invite"):
        details.append(f"ข้อความจากผู้ส่ง: {request.message}")
    if request.due_at is not None and item.kind in ("sign_turn", "sign_reminder", "sign_overdue", "sign_invite"):
        details.append(f"ครบกำหนด: {format_due(request.due_at)}")
    return details


def _render(item: OutgoingEmail, request: SigningRequest, recipient_email: str, recipient_name: str,
            actor: Optional[User]) -> mailer.Mail:
    url = register_url(recipient_email) if item.kind == "sign_invite" else request_url(request.id)
    subject = _SUBJECTS[item.kind].format(title=request.title)
    details = _details(item, request)
    greeting = f"เรียน {recipient_name}"
    footer_hint = "" if item.kind == "sign_invite" else " — ปิดการรับอีเมลแจ้งเตือนได้ที่หน้า \"การลงนาม\""

    text = "\n".join([greeting, "", item.title, *details, "", f"เปิดดู: {url}", "",
                      f"อีเมลนี้ส่งอัตโนมัติจาก {settings.APP_NAME}" + footer_hint])
    esc = html.escape
    login_note = ("สมัครด้วยอีเมลนี้เท่านั้น ระบบจึงจะผูกเอกสารกับบัญชีของคุณ" if item.kind == "sign_invite"
                  else "ต้องเข้าสู่ระบบด้วยบัญชีของคุณก่อนเปิดเอกสาร")
    detail_html = "".join(f'<p style="margin:4px 0;color:#444">{esc(line)}</p>' for line in details)
    button = _BUTTON.get(item.kind, "เปิดคำขอลงนาม")
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#333;line-height:1.6;padding:20px">
<div style="max-width:600px;margin:0 auto;border:1px solid #ddd;border-radius:8px;padding:28px">
<h2 style="color:#2563eb;margin:0 0 16px">{esc(settings.APP_NAME)}</h2>
<p>{esc(greeting)}</p>
<p style="font-size:16px;font-weight:bold">{esc(item.title)}</p>
{detail_html}
<p style="text-align:center;margin:28px 0"><a href="{esc(url)}" style="background:#2563eb;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block">{esc(button)}</a></p>
<p style="font-size:13px;color:#666">ลิงก์: <a href="{esc(url)}" style="color:#2563eb">{esc(url)}</a><br>{esc(login_note)}</p>
<p style="font-size:12px;color:#999;margin-top:24px">อีเมลนี้ส่งอัตโนมัติ{esc(footer_hint)}</p>
</div></body></html>"""
    return mailer.Mail(
        to=recipient_email,
        subject=subject,
        text=text,
        html=body,
        reply_to=actor.email if actor else None,
        sender_name=(actor.display_name or actor.email) if actor else None,
    )


def flush(db: Session) -> int:
    """ส่งอีเมลที่เข้าคิวไว้ (เรียกหลัง db.commit()) คืนจำนวนที่ส่ง"""
    items: list[OutgoingEmail] = db.info.pop("signing_outbox", [])
    sent = 0
    for item in items:
        request = db.get(SigningRequest, item.request_id)
        if request is None:
            continue
        actor = db.get(User, item.actor_id) if item.actor_id else None
        if item.user_id is None:  # ผู้ถูกเชิญ (ยังไม่มีบัญชี)
            if not item.to_email:
                continue
            mailer.send(_render(item, request, item.to_email, item.to_email, actor))
            sent += 1
            continue
        recipient = db.get(User, item.user_id)
        if recipient is None or not recipient.is_active:
            continue
        mail = None
        if recipient.signing_email_notifications:
            mail = _render(item, request, recipient.email, recipient.display_name or recipient.email, actor)
        if line_service.uses_line(recipient):
            if item.kind == "sign_completed" and recipient.id != request.owner_id:
                continue  # ผู้ลงนาม: แจ้งในระบบอย่างเดียว
            message = line_service.signing_message(item.kind, item.title, _details(item, request),
                                                   request_url(request.id), _BUTTON.get(item.kind, "เปิดคำขอลงนาม"))
            fallback = (lambda m=mail: mailer.send(m)) if mail is not None else None
            line_service.push(recipient.line_user_id, [message], fallback=fallback)
            sent += 1
            continue
        if mail is None:
            continue
        mailer.send(mail)
        sent += 1
    return sent
