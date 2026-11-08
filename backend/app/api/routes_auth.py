from pydantic import BaseModel, Field
from datetime import timedelta
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from typing import Optional
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport import requests
from app.core.config import settings

from app.db.database import get_db
from app.models.domain import User
from app.models.auth_schemas import UserCreate, UserResponse, Token, UpdateProfileRequest, PasswordChangeRequest, ForgotPasswordRequest, ResetPasswordRequest
from jose import jwt, JWTError
import logging
import secrets
import uuid
from app.core import ratelimit
from app.core.auth_session import auth_session_manager
from app.core.security import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.services.email_service import send_verification_email, send_reset_password_email
from app.services.donation_service import effective_plan
from app.api.deps import get_current_active_user

logger = logging.getLogger("routes_auth")

router = APIRouter()


def user_by_email(db: Session, email: str):
    """หาผู้ใช้จากอีเมลแบบไม่สนตัวพิมพ์เล็ก/ใหญ่ — เดิม "Somchai@x.com" กับ "somchai@x.com" เป็นคนละบัญชี:
    สมัครซ้ำได้ และพิมพ์ตัวใหญ่ตอน login/ลืมรหัสผ่านก็ไม่เจอบัญชี"""
    from sqlalchemy import func

    return (db.query(User).filter(func.lower(User.email) == (email or "").strip().lower())
            .order_by(User.id).first())


def _password_version(user: User) -> str:
    """ลายนิ้วมือของรหัสผ่านปัจจุบัน ใส่ในลิงก์รีเซ็ต — ตั้งรหัสใหม่แล้วลิงก์เดิมใช้ซ้ำไม่ได้"""
    import hashlib

    return hashlib.sha256((user.hashed_password or "").encode()).hexdigest()[:16]


def _token_jti(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        return jwt.decode(auth.split(" ", 1)[1], SECRET_KEY, algorithms=[ALGORITHM]).get("jti")
    except JWTError:
        return None

# ---------- จำกัดความถี่ (app/core/ratelimit.py) ----------
LOGIN_WINDOW = 15 * 60
LOGIN_MAX_FAILS_PER_ACCOUNT = 5     # ผิดครบ 5 ครั้งใน 15 นาที → ล็อกบัญชีนั้นจนครบ 15 นาที
LOGIN_MAX_FAILS_PER_IP = 30         # IP เดียวผิดรวมทุกบัญชี (กันเดาหลายบัญชี) — เผื่อออฟฟิศที่ใช้ IP ร่วมกัน
EMAIL_WINDOW = 60 * 60
EMAIL_MAX_PER_ADDRESS = 3           # ส่งอีเมล (ลืมรหัส/ยืนยันซ้ำ) ถึงอีเมลเดียวได้ 3 ครั้ง/ชม.
EMAIL_MAX_PER_IP = 20
REGISTER_MAX_PER_IP = 10            # สมัครบัญชีใหม่จาก IP เดียว 10 บัญชี/ชม.
_LOCKED_MSG = "ใส่รหัสผ่านผิดหลายครั้งเกินไป ระบบล็อกการเข้าสู่ระบบชั่วคราวเพื่อความปลอดภัย"
_EMAIL_MSG = "ขอส่งอีเมลบ่อยเกินไป"


def _email_quota(request: Request, email: str) -> None:
    """ลืมรหัสผ่าน / ส่งอีเมลยืนยันซ้ำ: กันยิงอีเมลใส่คนอื่นรัว ๆ — นับทุกครั้ง (รวมอีเมลที่ไม่มีบัญชี ไม่ให้ใช้เดาว่ามีบัญชีไหม)"""
    ip = ratelimit.client_ip(request)
    ratelimit.ensure_below("email-addr", email, EMAIL_MAX_PER_ADDRESS, _EMAIL_MSG)
    ratelimit.ensure_below("email-ip", ip, EMAIL_MAX_PER_IP, _EMAIL_MSG)
    ratelimit.hit("email-addr", email, EMAIL_WINDOW)
    if ip:
        ratelimit.hit("email-ip", ip, EMAIL_WINDOW)


@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, request: Request, db: Session = Depends(get_db)):
    ip = ratelimit.client_ip(request)
    ratelimit.ensure_below("register-ip", ip, REGISTER_MAX_PER_IP, "สมัครสมาชิกจากเครือข่ายนี้บ่อยเกินไป")
    if ip:
        ratelimit.hit("register-ip", ip, EMAIL_WINDOW)
    db_user = user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="อีเมลนี้สมัครสมาชิกแล้ว — เข้าสู่ระบบ หรือใช้ \"ลืมรหัสผ่าน\"")
    from app.services.account_service import SignupNotAllowed, check_new_account

    try:
        check_new_account(db, user.email)
    except SignupNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None

    hashed_password = get_password_hash(user.password)
    
    # ผู้ดูแลระบบคนแรก: อีเมลใน INITIAL_ADMIN_EMAILS หรือ (ไม่ตั้ง) ผู้ใช้คนแรกของระบบ
    from app.services.account_service import grants_initial_admin

    is_first_user = grants_initial_admin(db, user.email)
    
    new_user = User(
        email=user.email.strip().lower(),
        hashed_password=hashed_password,
        is_admin=is_first_user
    )
        
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Send verification email
    token = create_access_token({"sub": f"verify:{new_user.email}"}, expires_delta=timedelta(hours=24))
    send_verification_email(new_user.email, token)
    return new_user

# รหัสผ่านที่บัญชี Google เคยถูกตั้งให้ (เดาได้จากอีเมล) — ห้ามใช้ login เด็ดขาด ดู login_with_google
_LEGACY_GOOGLE_PASSWORD_PREFIX = "google_sso_random_password_"


def _claim_signing_invites(db: Session, user: User) -> None:
    """ผูกคำเชิญลงนามที่ส่งถึงอีเมลนี้ (เฟส 3) — ล้มเหลวก็ต้องไม่ทำให้ login ล้ม"""
    try:
        from app.services import signing_service

        signing_service.claim_invites(db, user)
    except Exception:
        db.rollback()
        logging.getLogger("routes_auth").exception("ผูกคำเชิญลงนามไม่สำเร็จ user=%s", user.id)


def issue_login_token(db: Session, user: User) -> dict:
    """ออก access token หลังยืนยันตัวตนสำเร็จ (รหัสผ่าน / Google / Passkey) — นับ session ตามแผน และผูกคำเชิญลงนาม"""
    _claim_signing_invites(db, user)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = str(uuid.uuid4())
    auth_session_manager.add_session(db, user.id, jti, effective_plan(user))
    access_token = create_access_token(
        data={"sub": str(user.id), "jti": jti}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email, ip = form_data.username.strip().lower(), ratelimit.client_ip(request)
    # เช็กก่อนตรวจรหัส — ระหว่างล็อก รหัสถูกก็เข้าไม่ได้ (ไม่งั้นเดาต่อได้เรื่อย ๆ แค่ดูว่าคำตอบเปลี่ยน)
    ratelimit.ensure_below("login-acct", email, LOGIN_MAX_FAILS_PER_ACCOUNT, _LOCKED_MSG)
    ratelimit.ensure_below("login-ip", ip, LOGIN_MAX_FAILS_PER_IP, _LOCKED_MSG)
    user = user_by_email(db, form_data.username)
    legacy_google = form_data.password == f"{_LEGACY_GOOGLE_PASSWORD_PREFIX}{form_data.username}"
    if not user or legacy_google or not verify_password(form_data.password, user.hashed_password):
        fails = ratelimit.hit("login-acct", email, LOGIN_WINDOW)
        if ip:
            ratelimit.hit("login-ip", ip, LOGIN_WINDOW)
        left = LOGIN_MAX_FAILS_PER_ACCOUNT - fails
        if left <= 0:
            logger.warning("login locked after %s failures (ip=%s)", fails, ip)
            raise ratelimit.too_many(_LOCKED_MSG, LOGIN_WINDOW)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง" + (f" (ลองได้อีก {left} ครั้งก่อนถูกล็อกชั่วคราว)" if left <= 2 else ""),
            headers={"WWW-Authenticate": "Bearer"},
        )
    ratelimit.reset("login-acct", email)
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="กรุณายืนยันอีเมลของคุณก่อนเข้าใช้งาน",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:  # เดิมออก token ให้บัญชีที่ถูกระงับ แล้วทุกหน้าขึ้น error แทน
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="บัญชีนี้ถูกระงับการใช้งาน — ติดต่อผู้ดูแลระบบ")

    return issue_login_token(db, user)


@router.post("/logout")
def logout(request: Request, current_user: User = Depends(get_current_active_user)):
    """ออกจากระบบ — เดิมแค่ลบ token ในเบราว์เซอร์ token เดิมยังใช้ได้จนหมดอายุ (และนับเป็นอุปกรณ์ที่ login อยู่)"""
    jti = _token_jti(request)
    if jti:
        auth_session_manager.revoke_session(current_user.id, jti)
    return {"status": "ok"}

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user



@router.put("/profile", response_model=UserResponse)
def update_profile(profile_data: UpdateProfileRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if profile_data.display_name is not None:
        current_user.display_name = " ".join(profile_data.display_name.split()) or None
    db.commit()
    db.refresh(current_user)
    return current_user

@router.put("/change-password")
def change_password(password_data: PasswordChangeRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    # token ที่หลุดไม่ควรใช้เดารหัสเดิมได้ไม่จำกัด — นับร่วมกับ login ของบัญชีเดียวกัน
    ratelimit.ensure_below("login-acct", current_user.email, LOGIN_MAX_FAILS_PER_ACCOUNT, _LOCKED_MSG)
    if not verify_password(password_data.old_password, current_user.hashed_password):
        ratelimit.hit("login-acct", current_user.email, LOGIN_WINDOW)
        raise HTTPException(status_code=400, detail="รหัสผ่านเดิมไม่ถูกต้อง")
    current_user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()
    # อุปกรณ์อื่นที่ login ไว้ (เช่น เครื่องที่ถูกขโมยรหัส) ต้อง login ใหม่ — เครื่องนี้ใช้ต่อได้
    auth_session_manager.revoke_all(current_user.id, keep_jti=_token_jti(request))
    return {"msg": "เปลี่ยนรหัสผ่านสำเร็จ — อุปกรณ์อื่นที่เข้าสู่ระบบไว้ต้องเข้าสู่ระบบใหม่"}

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    _email_quota(request, req.email)
    user = user_by_email(db, req.email)
    if not user:
        # Prevent user enumeration by not revealing if email exists
        return {"msg": "ถ้าอีเมลนี้มีบัญชีอยู่ ระบบได้ส่งลิงก์ตั้งรหัสผ่านใหม่ไปแล้ว"}

    # Generate reset token
    expires = timedelta(hours=1)
    reset_token = create_access_token(
        data={"sub": str(user.id), "type": "reset", "pwv": _password_version(user)}, expires_delta=expires
    )
    
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    send_reset_password_email(user.email, reset_link)

    return {"msg": "ถ้าอีเมลนี้มีบัญชีอยู่ ระบบได้ส่งลิงก์ตั้งรหัสผ่านใหม่ไปแล้ว"}

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(req.token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "reset":
            raise HTTPException(status_code=400, detail="ลิงก์รีเซ็ตรหัสผ่านไม่ถูกต้อง หรือหมดอายุแล้ว")
    except JWTError:
        raise HTTPException(status_code=400, detail="ลิงก์รีเซ็ตรหัสผ่านไม่ถูกต้อง หรือหมดอายุแล้ว")
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งาน")
    # ลิงก์ใช้ได้ครั้งเดียว: เดิมลิงก์เดียวกันตั้งรหัสซ้ำได้ตลอด 1 ชั่วโมง (คนที่เห็นอีเมลภายหลังก็เปลี่ยนรหัสได้)
    if payload.get("pwv") != _password_version(user):
        raise HTTPException(status_code=400, detail="ลิงก์นี้ใช้ตั้งรหัสผ่านไปแล้ว หรือหมดอายุ — ขอลิงก์ใหม่ที่หน้า \"ลืมรหัสผ่าน\"")

    user.hashed_password = get_password_hash(req.new_password)
    # ลิงก์รีเซ็ตส่งไปที่อีเมลของบัญชี — เปิดลิงก์ได้แปลว่าเป็นเจ้าของอีเมลจริง จึงถือว่ายืนยันอีเมลแล้วด้วย
    # (ไม่งั้นคนที่ลิงก์ยืนยันหายหรือหมดอายุจะตั้งรหัสใหม่ได้ แต่ยัง login ไม่ได้)
    user.is_verified = True
    db.commit()
    auth_session_manager.revoke_all(user.id)  # ทุกอุปกรณ์ที่ login ด้วยรหัสเดิมต้องเข้าสู่ระบบใหม่
    return {"msg": "ตั้งรหัสผ่านใหม่สำเร็จ สามารถเข้าสู่ระบบด้วยรหัสผ่านใหม่ได้เลย"}

class GoogleLoginRequest(BaseModel):
    credential: str

@router.post("/google", response_model=Token)
def login_with_google(req: GoogleLoginRequest, db: Session = Depends(get_db)):
    if not settings.google_enabled:
        raise HTTPException(status_code=503, detail="ระบบนี้ไม่ได้เปิดใช้การเข้าสู่ระบบด้วย Google")
        
    try:
        # Verify the token
        idinfo = id_token.verify_oauth2_token(req.credential, requests.Request(), settings.GOOGLE_CLIENT_ID)
        email = idinfo['email']
        name = idinfo.get('name', '')
    except ValueError:
        raise HTTPException(status_code=400, detail="ยืนยันตัวตนกับ Google ไม่สำเร็จ — ลองใหม่อีกครั้ง")

    # Check if user exists
    user = user_by_email(db, email)
    if not user:
        # Create new user
        from app.services.account_service import SignupNotAllowed, check_new_account, grants_initial_admin

        try:
            check_new_account(db, email)
        except SignupNotAllowed as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        is_first_user = grants_initial_admin(db, email)
        user = User(
            email=email,
            display_name=name,
            profile_picture=idinfo.get('picture', None),
            # บัญชี Google ไม่มีรหัสผ่าน — ตั้งค่าสุ่มที่เดาไม่ได้ (ถ้าอยากใช้รหัสผ่านให้ใช้ "ลืมรหัสผ่าน")
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),
            is_verified=True,
            is_admin=is_first_user
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.is_active:
            raise HTTPException(status_code=400, detail="บัญชีนี้ถูกระงับการใช้งาน — ติดต่อผู้ดูแลระบบ")
        
        # Update verification and profile picture if missing
        changed = False
        if not user.is_verified:
            user.is_verified = True
            changed = True
        if not user.profile_picture and idinfo.get('picture'):
            user.profile_picture = idinfo.get('picture')
            changed = True
        if changed:
            db.commit()

    return issue_login_token(db, user)

@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        from app.core.config import settings
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub or not sub.startswith("verify:"):
            raise HTTPException(status_code=400, detail="ลิงก์ยืนยันอีเมลไม่ถูกต้อง")
        email = sub.replace("verify:", "")

        user = user_by_email(db, email)
        if not user:
            raise HTTPException(status_code=404, detail="ไม่พบบัญชีของอีเมลนี้")
            
        user.is_verified = True
        db.commit()
        
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/verify-success")
    except JWTError:
        raise HTTPException(status_code=400, detail="ลิงก์ยืนยันอีเมลหมดอายุหรือไม่ถูกต้อง — ขอลิงก์ใหม่ได้ที่หน้าเข้าสู่ระบบ")

class ResendVerificationRequest(BaseModel):
    email: str

@router.post("/resend-verification")
def resend_verification(req: ResendVerificationRequest, request: Request, db: Session = Depends(get_db)):
    _email_quota(request, req.email)
    user = user_by_email(db, req.email)
    if not user:
        return {"status": "ok"}
    if user.is_verified:
        raise HTTPException(status_code=400, detail="อีเมลนี้ยืนยันแล้ว — เข้าสู่ระบบได้เลย")
        
    token = create_access_token({"sub": f"verify:{user.email}"}, expires_delta=timedelta(hours=24))
    success = send_verification_email(user.email, token)
    if not success:
        raise HTTPException(status_code=500, detail="ส่งอีเมลไม่สำเร็จ — ลองใหม่ภายหลัง หรือติดต่อผู้ดูแลระบบ")
    return {"status": "ok"}

from app.core.crypto import encrypt_api_key


class APIKeyRequest(BaseModel):
    api_key: str = ""
    provider: str = "gemini"   # gemini | anthropic | openai (ดู services/ai_client.py)
    model: str = ""            # ว่าง = รุ่นเริ่มต้นของค่าย (openai ต้องระบุ)
    base_url: str = ""         # openai: OpenAI-compatible endpoint · anthropic: proxy (ไม่บังคับ)
    test: bool = True          # ลองเรียกจริงก่อนบันทึก


@router.post("/api-key")
def update_api_key(req: APIKeyRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """บันทึก API key ส่วนตัว (ค่ายไหนก็ได้) — ลองเรียกจริงก่อน ใช้ไม่ได้ = ไม่บันทึก"""
    from app.services import ai_client

    if not settings.AI_USER_KEYS_ENABLED:
        raise HTTPException(status_code=403, detail="ระบบนี้ไม่เปิดให้ใช้ API key ส่วนตัว — ใช้ AI ของระบบ")
    provider = ai_client.normalize_provider(req.provider)
    if not provider:
        raise HTTPException(status_code=400, detail="ไม่รู้จักผู้ให้บริการ AI ที่เลือก")
    key = req.api_key.strip()
    model = req.model.strip()[:100]
    try:
        base_url = ai_client.validate_base_url(req.base_url, personal=True) if provider != "gemini" else ""
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if len(base_url) > 300:
        raise HTTPException(status_code=400, detail="URL ยาวเกินไป")
    if not key and not (provider == "openai" and base_url):
        raise HTTPException(status_code=400, detail="กรุณาใส่ API key")
    if provider == "openai" and not model:
        raise HTTPException(status_code=400, detail="API แบบ OpenAI ต้องระบุชื่อรุ่น (model)")
    tested_model = None
    if req.test:
        cfg = ai_client.AIConfig(provider, key, model, base_url, "personal")
        try:
            tested_model = ai_client.test_config(cfg)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"ทดสอบ API key ไม่ผ่าน: {ai_client.friendly_error(exc)}") from None
    # OpenAI-compatible ภายในที่ไม่ใช้ key — เก็บค่าว่างที่เข้ารหัสไม่ได้ จึงเก็บเครื่องหมายแทน
    current_user.encrypted_gemini_key = encrypt_api_key(key or "-", current_user)
    current_user.ai_provider = provider
    current_user.ai_model = model or None
    current_user.ai_base_url = base_url or None
    db.commit()
    return {"status": "success", "message": "บันทึก API key แล้ว", "provider": provider, "model": tested_model or model or None}


@router.delete("/api-key")
def delete_api_key(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    current_user.encrypted_gemini_key = None
    current_user.ai_provider = None
    current_user.ai_model = None
    current_user.ai_base_url = None
    db.commit()
    return {"status": "success"}

@router.post("/accept-tos")
def accept_tos(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    current_user.accepted_tos = True
    db.commit()
    return {"status": "success", "message": "Terms of Service accepted"}

@router.get("/ai-quota")
def get_personal_ai_quota(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.services import ai_usage

    ai_requests = ai_usage.get_count(db, current_user.id, ai_usage.PERSONAL_REQUEST)
    system_requests_today = ai_usage.get_count(db, current_user.id, ai_usage.SYSTEM_CONVERSION)

    from app.services import ai_client

    def preview(key: str | None) -> str | None:
        if not key or key == "-":
            return None
        return f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "***"

    system_ai = ai_client.system_config()
    personal_ai = ai_client.user_config(current_user)
    usable_personal = personal_ai if settings.AI_USER_KEYS_ENABLED else None
    return {
        # ไม่มีทั้ง AI ของระบบและ key ส่วนตัว → หน้าเว็บซ่อนกล่องโควต้าและตัวเลือก AI ทั้งหมด
        "ai_available": bool(system_ai or usable_personal),
        "ai_ocr": bool(usable_personal),  # อ่านข้อความในพื้นที่ที่เลือกด้วย AI ใช้ key ส่วนตัวเท่านั้น (ไม่งั้น Tesseract)
        "requests_today": ai_requests,
        "system_requests_today": system_requests_today,
        "system_daily_limit": settings.AI_SYSTEM_DAILY_LIMIT,
        "system_ai": bool(system_ai),
        "system_provider": system_ai.provider if system_ai else None,
        "system_provider_label": system_ai.label if system_ai else None,
        "system_model": (system_ai.model or None) if system_ai else None,
        "system_key_preview": preview(system_ai.api_key) if (system_ai and current_user.is_admin) else None,
        "user_keys_enabled": settings.AI_USER_KEYS_ENABLED,
        "providers": [{"value": k, "label": v} for k, v in ai_client.PROVIDERS.items()],
        "personal_provider": personal_ai.provider if personal_ai else None,
        "personal_model": (personal_ai.model or None) if personal_ai else None,
        "personal_base_url": (personal_ai.base_url or None) if personal_ai else None,
        "personal_key_preview": preview(personal_ai.api_key) if personal_ai else None,
    }


# ---------------------------------------------------------------- ลบบัญชี (หน้าโปรไฟล์)

class DeleteAccountRequest(BaseModel):
    confirm_email: str
    password: Optional[str] = None
    passkey_flow_id: Optional[str] = None
    passkey_credential: Optional[dict] = None


DELETE_ACCOUNT_PASSKEY_PURPOSE = "delete-account"


@router.get("/account/deletion-summary")
def account_deletion_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    from app.services import account_service

    return account_service.summary(db, current_user)


@router.post("/account/delete/passkey-options")
def account_delete_passkey_options(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    from app.services import passkey_service

    try:
        return passkey_service.authentication_options(db, current_user, DELETE_ACCOUNT_PASSKEY_PURPOSE)
    except passkey_service.PasskeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/account/delete")
def delete_my_account(req: DeleteAccountRequest, request: Request, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_active_user)):
    """ลบบัญชีถาวร — ต้องพิมพ์อีเมลของตัวเอง และยืนยันตัวตนด้วยรหัสผ่านหรือ passkey"""
    from app.services import account_service, passkey_service
    from app.services.signing_service import ClientInfo

    if (req.confirm_email or "").strip().lower() != current_user.email.lower():
        raise HTTPException(status_code=400, detail="อีเมลที่พิมพ์ไม่ตรงกับอีเมลของบัญชีนี้")
    if req.passkey_flow_id and req.passkey_credential:
        try:
            passkey_service.verify_for_user(db, current_user, DELETE_ACCOUNT_PASSKEY_PURPOSE,
                                            req.passkey_flow_id, req.passkey_credential)
        except passkey_service.PasskeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    elif not req.password or not verify_password(req.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="รหัสผ่านไม่ถูกต้อง")
    from app.api.deps import client_ip

    ip = client_ip(request)
    try:
        result = account_service.delete_account(db, current_user, ClientInfo(ip=ip, user_agent=request.headers.get("user-agent")))
    except account_service.AccountDeletionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    return {"deleted": True, **result}



# ---------- รูปโปรไฟล์ (หน้าโปรไฟล์ › รูปโปรไฟล์) — อัปโหลดเอง หรืออีโมจิที่วาดด้วย Pillow (services/avatar_service.py) ----------

class AvatarEmojiRequest(BaseModel):
    face: str = Field(max_length=20)
    face_color: str = Field(default="#FFC83D", max_length=7)
    bg_color: str = Field(default="#DBEAFE", max_length=7)


def _save_avatar(db: Session, user: User, png: bytes, emoji: Optional[str]) -> dict:
    from datetime import datetime, timezone
    user.avatar_png = png
    user.avatar_emoji = emoji
    user.avatar_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return {"status": "ok", "avatar_url": user.avatar_url, "avatar_emoji": user.avatar_emoji}


@router.get("/avatar/emojis")
def avatar_emojis(current_user: User = Depends(get_current_active_user)):
    from app.services import avatar_service
    return {"faces": [{"key": k, "label": v} for k, v in avatar_service.FACES.items()],
            "default_face_color": avatar_service.DEFAULT_FACE_COLOR, "default_bg_color": avatar_service.DEFAULT_BG_COLOR}


@router.get("/avatar/emoji-preview")
def avatar_emoji_preview(face: str, face_color: str = "#FFC83D", bg_color: str = "#DBEAFE", size: int = 128,
                         current_user: User = Depends(get_current_active_user)):
    from fastapi.responses import Response
    from app.services import avatar_service
    try:
        png = avatar_service.render_emoji(face, face_color, bg_color, size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/avatar/emoji")
def set_avatar_emoji(payload: AvatarEmojiRequest, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_active_user)):
    from app.services import avatar_service
    try:
        png = avatar_service.render_emoji(payload.face, payload.face_color.upper(), payload.bg_color.upper(),
                                          avatar_service.AVATAR_SIZE)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _save_avatar(db, current_user, png, f"{payload.face}|{payload.face_color.upper()}|{payload.bg_color.upper()}")


@router.post("/avatar/upload")
async def upload_avatar(file: UploadFile = File(...), db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_active_user)):
    from fastapi.concurrency import run_in_threadpool
    from app.services import avatar_service
    data = await file.read(avatar_service.MAX_UPLOAD_BYTES + 1)
    try:
        png = await run_in_threadpool(avatar_service.process_upload, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _save_avatar(db, current_user, png, None)


@router.delete("/avatar")
def delete_avatar(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    current_user.avatar_png = None
    current_user.avatar_emoji = None
    current_user.avatar_updated_at = None
    db.commit()
    return {"status": "ok"}


@router.get("/avatar/{user_id}.png")
def get_avatar(user_id: int, t: Optional[str] = None, db: Session = Depends(get_db)):
    """รูปโปรไฟล์ (ไม่ต้อง header — <img> ส่งไม่ได้) ต้องมี token ของเจ้าของรูปที่ได้จาก avatar_url"""
    from fastapi.responses import Response
    from app.core.security import verify_resource_token
    if verify_resource_token("avatar", t) != user_id:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ดูรูปนี้")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.avatar_png:
        raise HTTPException(status_code=404, detail="ไม่พบรูปโปรไฟล์")
    return Response(bytes(user.avatar_png), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=604800, immutable"})
