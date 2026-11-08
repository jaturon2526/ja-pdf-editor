"""LINE — ผูกบัญชีเพื่อรับแจ้งเตือนการลงนาม + webhook จาก LINE Platform

- GET    /line/status        สถานะการเชื่อมต่อของผู้ใช้ (+ โควตาเดือนนี้สำหรับแอดมิน)
- POST   /line/link-code     ขอรหัสผูก (ใช้ครั้งเดียว 10 นาที) + ลิงก์/QR เปิดแชท OA
- PUT    /line/preferences   เปิด/ปิดรับแจ้งเตือนทาง LINE
- DELETE /line/link          ยกเลิกการเชื่อมต่อ
- POST   /line/webhook       LINE เรียก (ไม่ต้อง login — ตรวจ X-Line-Signature แทน)
  URL ที่ตั้งใน console: https://<โดเมน>/api/line/webhook (nginx ตัด /api ออก)
"""
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.db.database import get_db
from app.models.domain import User
from app.services import line_service

logger = logging.getLogger("line")

router = APIRouter(prefix="/line", tags=["line"])


class PreferenceRequest(BaseModel):
    notifications: bool


def _require_enabled():
    if not settings.line_enabled:
        raise HTTPException(status_code=503, detail="ระบบยังไม่ได้เปิดใช้การแจ้งเตือนทาง LINE")


@router.get("/status")
def line_status(current_user: User = Depends(get_current_active_user)):
    return line_service.status(current_user)


@router.post("/link-code")
def link_code(current_user: User = Depends(get_current_active_user)):
    _require_enabled()
    return line_service.create_link_code(current_user)


@router.put("/preferences")
def preferences(payload: PreferenceRequest, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_active_user)):
    line_service.set_notifications(db, current_user, payload.notifications)
    return line_service.status(current_user)


@router.delete("/link")
def unlink(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    line_service.unlink(db, current_user)
    return line_service.status(current_user)


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db),
                  x_line_signature: str = Header(default="")):
    if not settings.line_enabled:
        raise HTTPException(status_code=503, detail="LINE ไม่ได้เปิดใช้")
    body = await request.body()
    if not line_service.verify_signature(body, x_line_signature):
        logger.warning("webhook LINE ลายเซ็นไม่ถูกต้อง — ปฏิเสธ")
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid body") from None
    await run_in_threadpool(line_service.handle_events, db, payload)  # เรียก LINE API/DB แบบ sync
    return {"ok": True}
