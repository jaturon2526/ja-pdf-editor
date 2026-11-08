"""หนังสือรับรองการลงนาม (Certificate of Completion) — หลักฐานแนบท้ายของคำขอลงนาม

ทำเป็นไฟล์ PDF แยก ไม่ต่อท้ายเอกสารที่ลงนามแล้ว: ถ้าเพิ่มหน้าลงในเอกสารหลังมีลายเซ็น โปรแกรมอ่าน PDF จะแจ้งว่า
เอกสารถูกแก้ไขหลังลงนาม (แบบเดียวกับที่บริการ e-signature ทั่วไปแยก "certificate of completion" เป็นอีกไฟล์)
ไฟล์หลักฐานลงนามด้วยใบรับรองของระบบ (system seal) เพื่อให้ตรวจได้ว่าไม่ถูกแก้ไข และระบุ SHA-256 ของเอกสาร
ต้นฉบับ/ฉบับสุดท้ายไว้ให้เทียบกับไฟล์จริงได้
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import SigningEvent, SigningRequest, User
from app.services import signing_pdf, thai_text

STATUS_TH = {"in_progress": "กำลังลงนาม", "completed": "ลงนามครบแล้ว", "rejected": "ถูกปฏิเสธ", "cancelled": "ยกเลิกแล้ว"}
STEP_STATUS_TH = {"waiting": "รอถึงคิว", "pending": "ถึงคิวลงนาม", "signed": "ลงนามแล้ว", "rejected": "ปฏิเสธ"}
SIGN_TYPE_TH = {"electronic": "อิเล็กทรอนิกส์", "digital": "ดิจิทัล (ใบรับรอง)", "either": "เลือกได้"}
EVENT_TH = {
    "created": "ส่งให้ลงนาม", "viewed": "เปิดดูเอกสาร", "signed": "ลงนาม", "rejected": "ปฏิเสธ", "cancelled": "ยกเลิก",
    "completed": "ลงนามครบทุกคน", "reminded": "ส่งเตือน", "invite_accepted": "รับคำเชิญ (ผูกบัญชี)",
}


def _fonts() -> tuple[str, str]:
    from app.services import fonts

    regular = fonts.resolve_font_path("sarabun")[1]
    bold = regular.replace("Sarabun-Regular", "Sarabun-Bold")
    return regular, bold


def _t(text) -> str:
    """ข้อความไทยในตาราง/ย่อหน้า: แทรกจุดตัดบรรทัดระหว่างคำ (fpdf2 ตัดบรรทัดเฉพาะที่ช่องว่าง ไม่งั้นตัดกลางคำ)"""
    return thai_text.with_break_opportunities(str(text))


def _fmt(value: Optional[dt.datetime]) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        value = value.astimezone(ZoneInfo(settings.APP_TIMEZONE))
    except Exception:
        pass
    return value.strftime("%d/%m/%Y %H:%M:%S")


def _user_label(user: Optional[User]) -> str:
    if user is None:
        return "ระบบ"
    return f"{user.display_name} <{user.email}>" if user.display_name else user.email


def build_evidence_pdf(db: Session, request: SigningRequest) -> bytes:
    """สร้าง PDF หลักฐาน (ยังไม่ลงนาม) จากข้อมูลคำขอ ผู้ลงนาม และ signing_events ทั้งหมด"""
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    events = (db.query(SigningEvent).filter(SigningEvent.request_id == request.id)
              .order_by(SigningEvent.created_at, SigningEvent.id).all())
    actor_ids = {e.actor_user_id for e in events if e.actor_user_id}
    actors = {u.id: u for u in db.query(User).filter(User.id.in_(actor_ids)).all()} if actor_ids else {}

    created = next((e for e in events if e.action == "created"), None)
    finished = next((e for e in reversed(events) if e.sha256_after), None)
    signed_events = {}
    for e in events:  # ผู้ลงนามที่ลบบัญชีแล้วจับคู่ด้วยชื่อที่เก็บไว้ (actor_label = signer_label)
        if e.action == "signed" and (e.actor_user_id or e.actor_label):
            signed_events[e.actor_user_id or e.actor_label] = e

    regular, bold = _fonts()
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_font("Sarabun", "", regular)
    pdf.add_font("Sarabun", "B", bold)
    pdf.set_text_shaping(True, script="thai", language="tha")
    pdf.set_title(f"หลักฐานการลงนาม - {request.title}")
    pdf.set_creator(settings.APP_NAME)
    pdf.add_page()

    pdf.set_font("Sarabun", "B", 16)
    pdf.cell(0, 9, "หนังสือรับรองการลงนามเอกสาร", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Sarabun", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, f"Certificate of Completion — {settings.APP_NAME} · ออกเมื่อ {_fmt(dt.datetime.now(dt.timezone.utc))}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    head = FontFace(emphasis="BOLD", fill_color=(235, 240, 250))

    def section(title: str) -> None:
        pdf.ln(2)
        pdf.set_font("Sarabun", "B", 12)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Sarabun", "", 9.5)

    section("ข้อมูลเอกสาร")
    rows = [
        ("เลขที่คำขอ", f"#{request.id}"),
        ("ชื่อเอกสาร", request.title),
        ("ผู้ส่ง", _user_label(request.owner)),
        ("สถานะ", STATUS_TH.get(request.status, request.status)),
        ("ส่งเมื่อ", _fmt(request.created_at)),
        ("ครบเมื่อ", _fmt(request.completed_at)),
        ("ครบกำหนด", _fmt(request.due_at) if request.due_at else "-"),
        ("SHA-256 ต้นฉบับ", created.sha256_before if created and created.sha256_before else "-"),
        ("SHA-256 ฉบับล่าสุด", finished.sha256_after if finished else "-"),
    ]
    with pdf.table(col_widths=(40, 140), first_row_as_headings=False, line_height=6.5,
                   borders_layout="HORIZONTAL_LINES", text_align="LEFT") as table:
        for label, value in rows:
            r = table.row()
            r.cell(_t(label), style=FontFace(emphasis="BOLD"))
            r.cell(_t(str(value)))

    section("ผู้ลงนาม")
    with pdf.table(col_widths=(14, 52, 26, 22, 30, 36), line_height=5.5, headings_style=head, text_align="LEFT") as table:
        h = table.row()
        for text in ("ลำดับ", "ผู้ลงนาม", "วิธีลงนาม", "สถานะ", "เวลาที่ลงนาม", "IP / ใบรับรอง / ยืนยันตัวตน"):
            h.cell(_t(text))
        for s in request.steps:
            if s.signer:
                name = _user_label(s.signer)
            elif s.signer_label:
                name = s.signer_label
            else:
                name = f"{s.invite_email} (เชิญทางอีเมล)"
            ev = signed_events.get(s.signer_user_id or s.signer_label) if (s.signer_user_id or s.signer_label) else None
            extra = []
            if ev and ev.ip:
                extra.append(ev.ip)
            if s.cert_subject:
                extra.append(s.cert_subject)
            if s.verified_method == "passkey":
                extra.append(f"ยืนยันตัวตนด้วย Passkey ({s.verified_detail or '-'})")
            elif s.require_passkey and s.status != "signed":
                extra.append("ต้องยืนยันด้วย Passkey")
            r = table.row()
            r.cell(_t(f"{s.order}" + (f" (ขั้น {s.stage})" if s.stage != s.order else "")))
            r.cell(_t(name))
            r.cell(_t(SIGN_TYPE_TH.get(s.signed_type or s.sign_type, s.signed_type or s.sign_type)))
            r.cell(_t(STEP_STATUS_TH.get(s.status, s.status) + (f": {s.comment}" if s.comment else "")))
            r.cell(_t(_fmt(s.signed_at) if s.signed_at else "-"))
            r.cell(_t("\n".join(extra) or "-"))

    section("ประวัติเหตุการณ์")
    with pdf.table(col_widths=(32, 28, 50, 70), line_height=5.2, headings_style=head, text_align="LEFT") as table:
        h = table.row()
        for text in ("เวลา", "เหตุการณ์", "ผู้ดำเนินการ", "รายละเอียด / IP / SHA-256"):
            h.cell(_t(text))
        for e in events:
            detail = [e.detail] if e.detail else []
            if e.ip:
                detail.append(f"IP {e.ip}")
            if e.sha256_after:
                detail.append(f"SHA-256 {e.sha256_after}")
            r = table.row()
            r.cell(_t(_fmt(e.created_at)))
            r.cell(_t(EVENT_TH.get(e.action, e.action)))
            r.cell(_t(_user_label(actors.get(e.actor_user_id)) if e.actor_user_id else (e.actor_label or "ระบบ")))
            r.cell(_t("\n".join(detail) or "-"))

    pdf.ln(4)
    pdf.set_font("Sarabun", "", 8.5)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 4.6, align="L", text=_t(
        "หนังสือฉบับนี้สร้างโดยระบบจากบันทึกเหตุการณ์ของคำขอลงนาม และลงนามด้วยใบรับรองของระบบเพื่อป้องกันการแก้ไข "
        "ตรวจสอบได้ว่าเอกสารที่ถืออยู่คือฉบับเดียวกับที่ลงนามโดยเทียบค่า SHA-256 ของไฟล์ "
        "(macOS/Linux: shasum -a 256 ชื่อไฟล์.pdf · Windows: certutil -hashfile ชื่อไฟล์.pdf SHA256) "
        "กับค่า \"SHA-256 ฉบับล่าสุด\" ด้านบน — เวลาทั้งหมดเป็นเวลาของเซิร์ฟเวอร์ "
        f"({settings.APP_TIMEZONE})"))
    return bytes(pdf.output())


def seal(pdf_bytes: bytes) -> bytes:
    """ลงนามไฟล์หลักฐานด้วยใบรับรองของระบบ (ฟิลด์ลายเซ็นแบบไม่แสดงผล)"""
    from pyhanko.sign import signers

    meta = signers.PdfSignatureMetadata(field_name="EvidenceSeal", reason="หนังสือรับรองการลงนาม (ออกโดยระบบ)",
                                        name=settings.APP_NAME)
    return signing_pdf.sign_with_optional_tsa(pdf_bytes, meta, signing_pdf.system_seal_signer())
