"""รับบริจาค (PromptPay) + สิทธิ์ผู้สนับสนุน + กระดานรายชื่อ

ขั้นตอน: ผู้ใช้สแกน QR (สร้างจากเลขพร้อมเพย์ที่แอดมินตั้ง) → แจ้งโอน (ยอด เวลา สลิปถ้ามี การแสดงชื่อ)
→ แอดมินตรวจกับบัญชีธนาคารจริงแล้ว "อนุมัติ" (ได้สิทธิ์ตามระดับยอดเงิน) หรือ "ปฏิเสธ"
พร้อมเพย์ไม่มี callback แจ้งเงินเข้า และไม่ส่งสลิปไปบริการตรวจสลิปภายนอก (ข้อมูลบัญชีผู้โอน) — ตรวจโดยคน

สิทธิ์ = แพ็กเกจ (PlanConfig: พื้นที่/จำนวนอุปกรณ์) ชั่วคราว · ยอดสะสมไม่ได้ คิดต่อครั้ง · ได้แพ็กเกจเดิมซ้ำ = ต่อวันหมดอายุ
แพ็กเกจหมดอายุ → กลับเป็น free อัตโนมัติ (expire_plans เรียกจากงานเบื้องหลัง) — effective_plan ใช้ตอนตรวจโควต้าทันที
"""
from __future__ import annotations

import datetime as dt
import io
import json
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import Donation, Notification, PlanConfig, User
from app.services import app_settings, promptpay, slip_verify

logger = logging.getLogger(__name__)

SETTINGS_KEY = "donation"
PLAN_ORDER = {"free": 0, "pro": 1, "premium": 2}
DEFAULT_TIERS = [
    {"min_amount": 49, "plan": "pro", "days": 30},
    {"min_amount": 299, "plan": "pro", "days": 365},
    {"min_amount": 499, "plan": "premium", "days": 365},
]
MIN_AMOUNT = Decimal("1")
MAX_AMOUNT = Decimal("100000")
SLIP_MAX_BYTES = 5 * 1024 * 1024
SLIP_MAX_SIDE = 1600
ANONYMOUS_NAME = "ผู้สนับสนุนไม่ประสงค์ออกนาม"
VERIFY_PROVIDERS = ("none", "easyslip")


class DonationError(ValueError):
    pass


# ---------------------------------------------------------------- ค่าตั้ง

def get_config(db: Session) -> dict:
    raw = app_settings.get(db, SETTINGS_KEY, {}) or {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "promptpay_id": raw.get("promptpay_id") or "",
        "receiver_name": raw.get("receiver_name") or "",
        "tiers": _clean_tiers(raw.get("tiers", DEFAULT_TIERS)),
        "thank_you": raw.get("thank_you") or "",
        "verify_provider": raw.get("verify_provider") if raw.get("verify_provider") in VERIFY_PROVIDERS else "none",
        "verify_key_set": bool(raw.get("verify_key")),
        "verify_bank_account": raw.get("verify_bank_account") or "",
        "auto_approve": bool(raw.get("auto_approve", False)),
    }


def _verify_key(db: Session) -> str:
    return app_settings.decrypt_secret((app_settings.get(db, SETTINGS_KEY, {}) or {}).get("verify_key", ""))


def _clean_tiers(tiers) -> list[dict]:
    out = []
    for t in tiers or []:
        try:
            amount = int(t["min_amount"])
            days = int(t["days"])
        except (KeyError, TypeError, ValueError):
            continue
        plan = str(t.get("plan") or "")
        if amount >= 1 and 1 <= days <= 3650 and plan in PLAN_ORDER and plan != "free":
            out.append({"min_amount": amount, "plan": plan, "days": days})
    return sorted(out, key=lambda t: (t["min_amount"], PLAN_ORDER[t["plan"]], t["days"]))


def save_config(db: Session, *, enabled: bool, promptpay_id: str, receiver_name: str, tiers: list,
                thank_you: str = "", verify_provider: str = "none", verify_key: Optional[str] = None,
                verify_bank_account: str = "", auto_approve: bool = False) -> dict:
    """verify_key: None = คงค่าเดิม · "" = ลบ · ค่าอื่น = ตั้งใหม่ (เก็บแบบเข้ารหัส ไม่ส่งกลับให้หน้าเว็บ)"""
    old = app_settings.get(db, SETTINGS_KEY, {}) or {}
    stored_key = old.get("verify_key", "") if verify_key is None else app_settings.encrypt_secret(verify_key.strip())
    provider = verify_provider if verify_provider in VERIFY_PROVIDERS else "none"
    if provider != "none" and not stored_key:
        raise DonationError("ใส่ API key ของบริการตรวจสลิปก่อนเปิดใช้")
    pid = (promptpay_id or "").strip()
    if pid:
        promptpay.normalize_id(pid)  # ผิดรูปแบบ → PromptPayError
    elif enabled:
        raise DonationError("ต้องตั้งเลขพร้อมเพย์ก่อนเปิดรับบริจาค")
    app_settings.put(db, SETTINGS_KEY, {
        "enabled": bool(enabled), "promptpay_id": pid, "receiver_name": (receiver_name or "").strip()[:80],
        "tiers": _clean_tiers(tiers), "thank_you": (thank_you or "").strip()[:300],
        "verify_provider": provider, "verify_key": stored_key,
        "verify_bank_account": re.sub(r"[^0-9-]", "", verify_bank_account or "")[:20],
        "auto_approve": bool(auto_approve) and provider != "none",
    })
    db.commit()
    return get_config(db)


def public_info(db: Session) -> dict:
    """ข้อมูลที่ทุกคนเห็นได้ (ไม่มีเลขพร้อมเพย์เต็ม)"""
    cfg = get_config(db)
    enabled = cfg["enabled"] and bool(cfg["promptpay_id"])
    plans = {p.plan_type: {"max_storage_mb": p.max_storage_mb or settings.DEFAULT_STORAGE_MB, "max_sessions": p.max_sessions}
             for p in db.query(PlanConfig).all()}
    return {
        "enabled": enabled,
        "receiver_name": cfg["receiver_name"] if enabled else "",
        "promptpay_masked": promptpay.mask_id(cfg["promptpay_id"]) if enabled else "",
        "tiers": [{**t, **plans.get(t["plan"], {})} for t in cfg["tiers"]] if enabled else [],
        "free_plan": plans.get("free", {"max_storage_mb": settings.DEFAULT_STORAGE_MB, "max_sessions": 1}),
        "thank_you": cfg["thank_you"],
    }


def parse_amount(value) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise DonationError("ยอดเงินไม่ถูกต้อง")
    if amount < MIN_AMOUNT or amount > MAX_AMOUNT:
        raise DonationError(f"ยอดเงินต้องอยู่ระหว่าง {MIN_AMOUNT:,.0f}–{MAX_AMOUNT:,.0f} บาท")
    return amount


def qr_svg(db: Session, amount=None) -> str:
    cfg = get_config(db)
    if not (cfg["enabled"] and cfg["promptpay_id"]):
        raise DonationError("ยังไม่เปิดรับบริจาค")
    return promptpay.qr_svg(cfg["promptpay_id"], parse_amount(amount) if amount else None)


def tier_for(db: Session, amount: Decimal) -> Optional[dict]:
    """ระดับสิทธิ์ที่ได้จากยอดนี้ (ระดับสูงสุดที่ยอดถึง)"""
    best = None
    for t in get_config(db)["tiers"]:
        if amount >= t["min_amount"]:
            if best is None or (PLAN_ORDER[t["plan"]], t["days"]) > (PLAN_ORDER[best["plan"]], best["days"]):
                best = t
    return best


# ---------------------------------------------------------------- สลิป

def _slip_dir() -> Path:
    d = settings.UPLOAD_DIR / "_donations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_slip(data: bytes) -> str:
    """บันทึกสลิปเป็น JPEG ใหม่ (ตัด EXIF/ข้อมูลแฝง ย่อด้านยาว ≤ 1600px) คืนชื่อไฟล์"""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(data) > SLIP_MAX_BYTES:
        raise DonationError("ไฟล์สลิปใหญ่เกิน 5 MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((SLIP_MAX_SIDE, SLIP_MAX_SIDE))
            name = f"{uuid.uuid4().hex}.jpg"
            im.save(_slip_dir() / name, "JPEG", quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise DonationError("ไฟล์สลิปต้องเป็นรูปภาพ (JPG/PNG)")
    return name


def slip_path(donation: Donation) -> Optional[Path]:
    if not donation.slip_path:
        return None
    p = _slip_dir() / Path(donation.slip_path).name
    return p if p.is_file() else None


def delete_slip(donation: Donation) -> None:
    p = slip_path(donation)
    if p:
        p.unlink(missing_ok=True)
    donation.slip_path = None


# ---------------------------------------------------------------- แจ้งโอน / ตรวจ

def create(db: Session, user: User, *, amount, transferred_at: dt.datetime, anonymous: bool, show_on_board: bool,
           display_name: Optional[str], message: Optional[str], slip: Optional[bytes]) -> Donation:
    if not public_info(db)["enabled"]:
        raise DonationError("ยังไม่เปิดรับบริจาค")
    value = parse_amount(amount)
    now = dt.datetime.now(dt.timezone.utc)
    if transferred_at.tzinfo is None:
        transferred_at = transferred_at.replace(tzinfo=dt.timezone.utc)
    if transferred_at > now + dt.timedelta(minutes=10) or transferred_at < now - dt.timedelta(days=60):
        raise DonationError("วันเวลาที่โอนต้องอยู่ภายใน 60 วันที่ผ่านมา")
    name = (display_name or "").strip()[:80] or (user.display_name or "").strip()[:80] or None
    qr = slip_verify.read_slip_qr(slip) if slip else None
    if qr and db.query(Donation).filter(Donation.slip_ref == qr.trans_ref, Donation.status != "rejected").first():
        raise DonationError("สลิปนี้ถูกแจ้งไปแล้ว — ถ้าแจ้งผิด ติดต่อผู้ดูแลระบบ")
    donation = Donation(
        user_id=user.id, amount_satang=int(value * 100), transferred_at=transferred_at,
        anonymous=bool(anonymous), show_on_board=bool(show_on_board),
        display_name=name, message=(message or "").strip()[:200] or None,
        slip_path=store_slip(slip) if slip else None,
        slip_payload=qr.payload[:255] if qr else None, slip_ref=qr.trans_ref[:64] if qr else None,
        slip_bank=qr.bank_code[:8] if qr else None,
        verify_status=None if qr or not slip else "unreadable",
    )
    db.add(donation)
    db.flush()
    db.commit()
    db.refresh(donation)
    if qr and get_config(db)["verify_provider"] != "none":
        run_verification(db, donation)
    if donation.status == "pending":
        for admin in db.query(User).filter(User.is_admin.is_(True), User.is_active.is_(True)).all():
            db.add(Notification(user_id=admin.id, kind="donation_new",
                                title=f"มีผู้แจ้งโอนสนับสนุน {value:,.2f} บาท — รอตรวจสอบ"))
        db.commit()
    db.refresh(donation)
    return donation


def run_verification(db: Session, donation: Donation) -> Donation:
    """ตรวจสลิปกับบริการภายนอก (ใช้ข้อความใน QR) · ผ่าน + เปิดอนุมัติอัตโนมัติ → อนุมัติทันที"""
    cfg = get_config(db)
    if donation.status != "pending" or not donation.slip_payload or cfg["verify_provider"] == "none":
        return donation
    try:
        result = slip_verify.verify(
            donation.slip_payload, api_key=_verify_key(db), claimed_amount=Decimal(donation.amount_satang) / 100,
            transferred_at=donation.transferred_at, promptpay_id=cfg["promptpay_id"],
            bank_account=cfg["verify_bank_account"], receiver_name=cfg["receiver_name"])
    except slip_verify.VerifyError as exc:
        result = slip_verify.VerifyResult("error", problems=[str(exc)])
    donation.verify_status = result.status
    donation.verify_detail = json.dumps(result.detail(), ensure_ascii=False)
    donation.verified_at = dt.datetime.now(dt.timezone.utc)
    if result.status == "verified" and result.amount is not None:
        donation.amount_satang = int(result.amount * 100)  # ใช้ยอดจริงจากธนาคาร
    db.commit()
    if result.status == "verified" and cfg["auto_approve"]:
        approve(db, donation, None, note="อนุมัติอัตโนมัติ — ตรวจสลิปกับธนาคารผ่าน")
    elif result.status != "verified":
        logger.info("donation %s: ตรวจสลิป %s %s", donation.id, result.status, result.problems)
    return donation


def _grant(user: User, plan: str, days: int, now: dt.datetime) -> None:
    current = effective_plan(user, now)
    expire = user.expire_date
    if expire is not None and expire.tzinfo is None:
        expire = expire.replace(tzinfo=dt.timezone.utc)
    if current == plan and expire is not None and expire > now:
        user.expire_date = expire + dt.timedelta(days=days)
    elif current != "free" and PLAN_ORDER.get(current, 0) > PLAN_ORDER[plan] and (expire is None or expire > now):
        return  # มีแพ็กเกจสูงกว่าอยู่แล้ว (เช่นแอดมินให้ถาวร) — ไม่ลดลง
    else:
        user.plan_type = plan
        user.expire_date = now + dt.timedelta(days=days)


def approve(db: Session, donation: Donation, admin: Optional[User], *, amount=None, plan: Optional[str] = None,
            days: Optional[int] = None, note: Optional[str] = None) -> Donation:
    if donation.status != "pending":
        raise DonationError("รายการนี้ตรวจไปแล้ว")
    if amount is not None:  # แอดมินแก้ยอดตามที่เงินเข้าจริง
        donation.amount_satang = int(parse_amount(amount) * 100)
    value = Decimal(donation.amount_satang) / 100
    if plan is None:
        tier = tier_for(db, value)
        plan, days = (tier["plan"], tier["days"]) if tier else (None, None)
    elif plan not in PLAN_ORDER or plan == "free":
        plan, days = None, None
    now = dt.datetime.now(dt.timezone.utc)
    user = db.get(User, donation.user_id) if donation.user_id else None
    if user and plan and days:
        _grant(user, plan, int(days), now)
        donation.granted_plan, donation.granted_days = plan, int(days)
    donation.status = "approved"
    donation.reviewed_by, donation.reviewed_at = (admin.id if admin else None), now
    donation.admin_note = (note or "").strip()[:255] or None
    delete_slip(donation)
    if user:
        perk = f" — ได้รับสิทธิ์ {plan.capitalize()} {days} วัน" if donation.granted_plan else ""
        db.add(Notification(user_id=user.id, kind="donation_approved",
                            title=f"ขอบคุณที่สนับสนุน {value:,.2f} บาท{perk}"))
    db.commit()
    db.refresh(donation)
    return donation


def reject(db: Session, donation: Donation, admin: User, note: Optional[str] = None) -> Donation:
    if donation.status != "pending":
        raise DonationError("รายการนี้ตรวจไปแล้ว")
    donation.status = "rejected"
    donation.reviewed_by = admin.id
    donation.reviewed_at = dt.datetime.now(dt.timezone.utc)
    donation.admin_note = (note or "").strip()[:255] or None
    delete_slip(donation)
    if donation.user_id:
        reason = f" ({donation.admin_note})" if donation.admin_note else ""
        db.add(Notification(user_id=donation.user_id, kind="donation_rejected",
                            title=f"ไม่พบยอดโอนที่แจ้งไว้{reason} — ติดต่อผู้ดูแลระบบได้"))
    db.commit()
    db.refresh(donation)
    return donation


# ---------------------------------------------------------------- แพ็กเกจหมดอายุ

def effective_plan(user: User, now: Optional[dt.datetime] = None) -> str:
    """แพ็กเกจที่ใช้ได้จริงตอนนี้ — หมดอายุแล้ว = free (แม้งานเบื้องหลังยังไม่ได้ปรับ plan_type)"""
    plan = user.plan_type or "free"
    expire = user.expire_date
    if plan != "free" and expire is not None:
        if expire.tzinfo is None:
            expire = expire.replace(tzinfo=dt.timezone.utc)
        if expire <= (now or dt.datetime.now(dt.timezone.utc)):
            return "free"
    return plan


def expire_plans(db: Session) -> int:
    """ปรับผู้ใช้ที่แพ็กเกจหมดอายุกลับเป็น free + แจ้งเตือนในระบบ คืนจำนวนที่ปรับ"""
    now = dt.datetime.now(dt.timezone.utc)
    users = db.query(User).filter(User.plan_type != "free", User.expire_date.isnot(None), User.expire_date <= now).all()
    for u in users:
        old = u.plan_type
        u.plan_type, u.expire_date = "free", None
        db.add(Notification(user_id=u.id, kind="plan_expired",
                            title=f"สิทธิ์ผู้สนับสนุน ({(old or '').capitalize()}) ครบกำหนดแล้ว — ขอบคุณที่ร่วมสนับสนุน"))
    if users:
        db.commit()
    return len(users)


# ---------------------------------------------------------------- แสดงผล

def board(db: Session, limit: int = 200) -> list[dict]:
    """กระดานผู้สนับสนุน: รายการที่อนุมัติแล้วและเลือกแสดง — ไม่แสดงยอดเงินและอีเมล"""
    rows = (db.query(Donation).filter(Donation.status == "approved", Donation.show_on_board.is_(True))
            .order_by(Donation.reviewed_at.desc()).limit(limit).all())
    return [{
        "name": ANONYMOUS_NAME if d.anonymous or not d.display_name else d.display_name,
        "anonymous": bool(d.anonymous or not d.display_name),
        "message": d.message,
        "date": (d.reviewed_at or d.created_at).date().isoformat() if (d.reviewed_at or d.created_at) else None,
    } for d in rows]


def to_dict(d: Donation, *, admin: bool = False, user: Optional[User] = None) -> dict:
    out = {
        "id": d.id, "amount": d.amount_satang / 100, "transferred_at": d.transferred_at.isoformat() if d.transferred_at else None,
        "status": d.status, "anonymous": d.anonymous, "show_on_board": d.show_on_board, "display_name": d.display_name,
        "message": d.message, "granted_plan": d.granted_plan, "granted_days": d.granted_days,
        "admin_note": d.admin_note, "created_at": d.created_at.isoformat() if d.created_at else None,
        "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
    }
    out["verify_status"] = d.verify_status
    if admin:
        out["has_slip"] = slip_path(d) is not None
        out["slip_ref"], out["slip_bank"] = d.slip_ref, d.slip_bank
        out["can_verify"] = bool(d.slip_payload) and d.status == "pending"
        try:
            out["verify_detail"] = json.loads(d.verify_detail) if d.verify_detail else None
        except ValueError:
            out["verify_detail"] = None
        out["user"] = ({"id": user.id, "email": user.email, "display_name": user.display_name,
                        "plan_type": effective_plan(user), "expire_date": user.expire_date.isoformat() if user.expire_date else None}
                       if user else None)
    return out
