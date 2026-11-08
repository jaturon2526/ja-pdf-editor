"""เข้าสู่ระบบด้วย LINE (ดู services/line_login_service.py)

- GET    /auth/line/config        เปิดใช้หรือไม่ (หน้า Login ใช้ตัดสินใจแสดงปุ่ม)
- POST   /auth/line/start         เริ่มเข้าสู่ระบบ → URL หน้าอนุญาตของ LINE
- POST   /auth/line/link-start    (ล็อกอินอยู่) เริ่มเชื่อม LINE กับบัญชีนี้
- POST   /auth/line/callback      {code, state} หลัง LINE ส่งกลับ → token / linked / need_email
- POST   /auth/line/email         {pending, email} ไม่มีอีเมลจาก LINE → ส่งลิงก์ยืนยัน
- POST   /auth/line/confirm       {token, pending} กดลิงก์ในอีเมล → token
- DELETE /auth/line/link          (ล็อกอินอยู่) ยกเลิกการเข้าสู่ระบบด้วย LINE
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.db.database import get_db
from app.models.domain import User
from app.services import line_login_service as svc

router = APIRouter(prefix="/auth/line", tags=["auth"])


class CallbackRequest(BaseModel):
    code: str
    state: str


class EmailRequest(BaseModel):
    pending: str
    email: str


class ConfirmRequest(BaseModel):
    token: str
    pending: str = ""


def _fail(exc: svc.LineLoginError):
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None


def _login(db: Session, user: User) -> dict:
    from app.api.routes_auth import issue_login_token

    return {"status": "login", **issue_login_token(db, user)}


@router.get("/config")
def config():
    return {"enabled": settings.line_login_enabled}


@router.post("/start")
def start():
    try:
        return svc.start("login")
    except svc.LineLoginError as exc:
        _fail(exc)


@router.post("/link-start")
def link_start(current_user: User = Depends(get_current_active_user)):
    try:
        return svc.start("link", current_user)
    except svc.LineLoginError as exc:
        _fail(exc)


@router.post("/callback")
async def callback(payload: CallbackRequest, db: Session = Depends(get_db)):
    try:
        result = await run_in_threadpool(svc.complete, db, payload.code, payload.state)  # เรียก LINE แบบ sync
    except svc.LineLoginError as exc:
        _fail(exc)
    if result["status"] == "login":
        return _login(db, result["user"])
    return result


@router.post("/email")
async def email(payload: EmailRequest):
    try:
        return await run_in_threadpool(svc.request_email, payload.pending, payload.email)
    except svc.LineLoginError as exc:
        _fail(exc)


@router.post("/confirm")
def confirm(payload: ConfirmRequest, db: Session = Depends(get_db)):
    try:
        user = svc.confirm(db, payload.token, payload.pending)
    except svc.LineLoginError as exc:
        _fail(exc)
    return _login(db, user)


@router.delete("/link")
def unlink(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc.unlink(db, current_user)
    return svc.status(current_user)
