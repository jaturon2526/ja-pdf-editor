"""Passkey (WebAuthn) — /auth/passkeys/*

- ลงทะเบียน (ต้อง login): POST register/options → POST register/verify
- เข้าสู่ระบบ (ไม่ต้อง login): POST login/options → POST login/verify → access token แบบเดียวกับ /auth/login
- จัดการ (ต้อง login): GET / · PATCH /{id} (เปลี่ยนชื่อ) · DELETE /{id}
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.api.routes_auth import issue_login_token
from app.db.database import get_db
from app.models.auth_schemas import Token
from app.models.domain import User
from app.services import passkey_service
from app.services.passkey_service import PasskeyError

router = APIRouter()


class RegisterVerifyRequest(BaseModel):
    flow_id: str = Field(max_length=100)
    credential: dict[str, Any]
    name: str | None = Field(default=None, max_length=200)


class LoginVerifyRequest(BaseModel):
    flow_id: str = Field(max_length=100)
    credential: dict[str, Any]


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _bad(exc: PasskeyError):
    return HTTPException(status_code=400, detail=str(exc))


@router.get("")
def list_passkeys(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return {"passkeys": [passkey_service.to_dict(p) for p in passkey_service.list_passkeys(db, current_user)]}


@router.post("/register/options")
def register_options(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    try:
        return passkey_service.registration_options(db, current_user)
    except PasskeyError as exc:
        raise _bad(exc)


@router.post("/register/verify")
def register_verify(req: RegisterVerifyRequest, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_active_user)):
    try:
        passkey = passkey_service.register(db, current_user, req.flow_id, req.credential, req.name)
    except PasskeyError as exc:
        raise _bad(exc)
    return passkey_service.to_dict(passkey)


@router.post("/login/options")
def login_options():
    return passkey_service.authentication_options()


@router.post("/login/verify", response_model=Token)
def login_verify(req: LoginVerifyRequest, db: Session = Depends(get_db)):
    try:
        user = passkey_service.authenticate(db, req.flow_id, req.credential)
    except PasskeyError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return issue_login_token(db, user)


@router.patch("/{passkey_id}")
def rename_passkey(passkey_id: int, req: RenameRequest, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_active_user)):
    passkey = passkey_service.get_owned(db, current_user, passkey_id)
    if passkey is None:
        raise HTTPException(status_code=404, detail="ไม่พบ passkey")
    return passkey_service.to_dict(passkey_service.rename(db, passkey, req.name))


@router.delete("/{passkey_id}")
def delete_passkey(passkey_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_active_user)):
    passkey = passkey_service.get_owned(db, current_user, passkey_id)
    if passkey is None:
        raise HTTPException(status_code=404, detail="ไม่พบ passkey")
    passkey_service.delete(db, passkey)
    return {"status": "ok"}
