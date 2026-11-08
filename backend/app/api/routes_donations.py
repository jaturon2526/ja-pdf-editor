"""รับบริจาค (PromptPay) — ดู services/donation_service.py

สาธารณะ: /donations/info, /donations/qr.svg, /donations/board · ผู้ใช้: แจ้งโอน, ประวัติของตัวเอง
แอดมิน: /admin/donations/* (ตั้งเลขพร้อมเพย์/ระดับสิทธิ์, ตรวจรายการ, ดูสลิป, อนุมัติ/ปฏิเสธ, ซ่อนจากกระดาน)
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_admin_user
from app.core import ratelimit
from app.db.database import get_db
from app.models.domain import Donation, User
from app.services import donation_service as svc
from app.services.promptpay import PromptPayError

router = APIRouter(tags=["donations"])

REPORTS_PER_HOUR = 5


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/donations/info")
def info(db: Session = Depends(get_db)):
    return svc.public_info(db)


@router.get("/donations/qr.svg")
def qr(amount: Optional[str] = Query(None, max_length=12), db: Session = Depends(get_db)):
    try:
        svg = svc.qr_svg(db, amount or None)
    except (svc.DonationError, PromptPayError) as exc:
        raise _bad(exc)
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/donations/board")
def board(db: Session = Depends(get_db)):
    return {"items": svc.board(db)}


@router.post("/donations")
async def report(
    amount: str = Form(..., max_length=12),
    transferred_at: dt.datetime = Form(...),
    anonymous: bool = Form(False),
    show_on_board: bool = Form(True),
    display_name: Optional[str] = Form(None, max_length=80),
    message: Optional[str] = Form(None, max_length=200),
    slip: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    ratelimit.ensure_below("donation_report", str(user.id), REPORTS_PER_HOUR, "แจ้งโอนบ่อยเกินไป")
    data = None
    if slip is not None and slip.filename:
        data = await slip.read(svc.SLIP_MAX_BYTES + 1)
    try:
        donation = svc.create(db, user, amount=amount, transferred_at=transferred_at, anonymous=anonymous,
                              show_on_board=show_on_board, display_name=display_name, message=message, slip=data)
    except svc.DonationError as exc:
        raise _bad(exc)
    ratelimit.hit("donation_report", str(user.id), 3600)
    return svc.to_dict(donation)


@router.get("/donations/mine")
def mine(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(Donation).filter(Donation.user_id == user.id).order_by(Donation.id.desc()).limit(50).all()
    return {"items": [svc.to_dict(d) for d in rows], "plan": svc.effective_plan(user),
            "expire_date": user.expire_date.isoformat() if user.expire_date else None}


# ---------------------------------------------------------------- แอดมิน

class ConfigPayload(BaseModel):
    enabled: bool = False
    promptpay_id: str = Field("", max_length=32)
    receiver_name: str = Field("", max_length=80)
    tiers: list[dict] = Field(default_factory=list, max_length=10)
    thank_you: str = Field("", max_length=300)
    verify_provider: str = Field("none", max_length=20)
    verify_key: Optional[str] = Field(None, max_length=500)   # None = คงเดิม · "" = ลบ
    verify_bank_account: str = Field("", max_length=30)
    auto_approve: bool = False


class ApprovePayload(BaseModel):
    amount: Optional[float] = None
    plan: Optional[str] = Field(None, max_length=32)   # None = ตามระดับยอดเงิน · "none" = ไม่ให้สิทธิ์
    days: Optional[int] = Field(None, ge=1, le=3650)
    note: Optional[str] = Field(None, max_length=255)


class RejectPayload(BaseModel):
    note: Optional[str] = Field(None, max_length=255)


class BoardPayload(BaseModel):
    show_on_board: bool


def _get(db: Session, donation_id: int) -> Donation:
    d = db.get(Donation, donation_id)
    if d is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการ")
    return d


@router.get("/admin/donations/config")
def get_config(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    return svc.get_config(db)


@router.put("/admin/donations/config")
def put_config(payload: ConfigPayload, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    try:
        return svc.save_config(db, **payload.model_dump())
    except (svc.DonationError, PromptPayError) as exc:
        raise _bad(exc)


@router.get("/admin/donations")
def list_donations(status: str = Query("pending", pattern="^(pending|approved|rejected|all)$"),
                   db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    q = db.query(Donation)
    if status != "all":
        q = q.filter(Donation.status == status)
    rows = q.order_by(Donation.id.desc()).limit(200).all()
    users = {u.id: u for u in db.query(User).filter(User.id.in_({d.user_id for d in rows if d.user_id})).all()} if rows else {}
    items = []
    for d in rows:
        item = svc.to_dict(d, admin=True, user=users.get(d.user_id))
        if d.status == "pending":
            item["suggested"] = svc.tier_for(db, Decimal(d.amount_satang) / 100)
        items.append(item)
    pending = db.query(Donation).filter(Donation.status == "pending").count()
    return {"items": items, "pending": pending}


@router.get("/admin/donations/{donation_id}/slip")
def slip(donation_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    path = svc.slip_path(_get(db, donation_id))
    if path is None:
        raise HTTPException(status_code=404, detail="ไม่มีสลิป")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/admin/donations/{donation_id}/approve")
def approve(donation_id: int, payload: ApprovePayload, db: Session = Depends(get_db),
            admin: User = Depends(get_current_admin_user)):
    try:
        plan = payload.plan
        if plan == "none":
            plan = "free"  # ไม่ให้สิทธิ์
        d = svc.approve(db, _get(db, donation_id), admin, amount=payload.amount, plan=plan,
                        days=payload.days, note=payload.note)
    except svc.DonationError as exc:
        raise _bad(exc)
    return svc.to_dict(d, admin=True, user=db.get(User, d.user_id) if d.user_id else None)


@router.post("/admin/donations/{donation_id}/reject")
def reject(donation_id: int, payload: RejectPayload, db: Session = Depends(get_db),
           admin: User = Depends(get_current_admin_user)):
    try:
        d = svc.reject(db, _get(db, donation_id), admin, payload.note)
    except svc.DonationError as exc:
        raise _bad(exc)
    return svc.to_dict(d, admin=True)


@router.post("/admin/donations/{donation_id}/verify")
def reverify(donation_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """ตรวจสลิปกับบริการตรวจสลิปอีกครั้ง (เช่น ครั้งก่อนธนาคารยังไม่พร้อม)"""
    d = _get(db, donation_id)
    if not d.slip_payload:
        raise HTTPException(status_code=400, detail="รายการนี้ไม่มีข้อมูล QR จากสลิป")
    if svc.get_config(db)["verify_provider"] == "none":
        raise HTTPException(status_code=400, detail="ยังไม่ได้ตั้งบริการตรวจสลิป")
    svc.run_verification(db, d)
    db.refresh(d)
    return svc.to_dict(d, admin=True, user=db.get(User, d.user_id) if d.user_id else None)


@router.put("/admin/donations/{donation_id}/board")
def set_board(donation_id: int, payload: BoardPayload, db: Session = Depends(get_db),
              admin: User = Depends(get_current_admin_user)):
    d = _get(db, donation_id)
    d.show_on_board = payload.show_on_board
    db.commit()
    return svc.to_dict(d, admin=True)
