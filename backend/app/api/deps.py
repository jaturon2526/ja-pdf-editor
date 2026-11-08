from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.security import SECRET_KEY, ALGORITHM
from app.models.domain import User
from app.core.auth_session import auth_session_manager

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        jti: str = payload.get("jti")
        # token ยืนยันอีเมล/รีเซ็ตรหัสผ่านใช้ sub แบบ "verify:..."/"reset:..." — ห้ามใช้แทน access token
        # และ access token ทุกตัวต้องมี jti (ใช้ตรวจจำนวนอุปกรณ์ที่ login พร้อมกันตาม plan)
        if user_id is None or not str(user_id).isdigit() or not jti:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    if not auth_session_manager.is_session_valid(int(user_id), jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or logged in from another device",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

def get_optional_user(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """คืน User ถ้าแนบ Bearer token ที่ถูกต้องมา ไม่งั้นคืน None (สำหรับ endpoint ที่ใช้ได้ทั้งแบบ login
    และไม่ login) — ตรวจ token ด้วยกฎเดียวกับ get_current_user ทุกอย่าง รวมถึง jti"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        user = get_current_user(authorization.split(" ", 1)[1], db)
    except HTTPException:
        return None
    return user if user.is_active else None


def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_admin_user(current_user: User = Depends(get_current_active_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user


# ---------- ตรวจสิทธิ์เจ้าของ PDF session ----------
# ทุก endpoint ที่รับ {session_id} ต้องใช้ dependency นี้แทนการเรียก session_manager.get() ตรงๆ
# เพื่อให้มั่นใจว่า (1) ผู้เรียก login อยู่ และ (2) session นั้นเป็นของผู้เรียกจริง
# ถ้าไม่ใช่เจ้าของจะตอบ 404 (ไม่ใช่ 403) เพื่อไม่ให้รู้ว่า session_id นั้นมีอยู่จริง
_SESSION_NOT_FOUND = "ไม่พบ session นี้ (อาจหมดอายุแล้ว) กรุณาเปิดไฟล์ใหม่"


def ensure_session_owner(session, user: User, db: Session) -> None:
    """ตรวจว่า session เป็นของ user — raise 404 ถ้าไม่ใช่

    session ที่สร้างก่อนมีระบบนี้ (user_id เป็น None) จะยอมให้เฉพาะผู้ที่เป็นเจ้าของ FileRecord
    ที่ชี้มายัง session นี้ และผูก user_id ให้ทันที (claim) เพื่อให้ครั้งต่อไปตรวจแบบปกติได้
    """
    from app.core.session import session_manager
    from app.models.domain import FileRecord

    if session.user_id is not None:
        if session.user_id != user.id:
            raise HTTPException(status_code=404, detail=_SESSION_NOT_FOUND)
        return
    owns_record = (
        db.query(FileRecord)
        .filter(FileRecord.storage_path == session.session_id, FileRecord.user_id == user.id)
        .first()
        is not None
    )
    if not owns_record:
        raise HTTPException(status_code=404, detail=_SESSION_NOT_FOUND)
    session.user_id = user.id
    session_manager.save(session)


def get_owned_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """FastAPI dependency: คืน PDFSession ของ {session_id} ที่ผู้ใช้ปัจจุบันเป็นเจ้าของ"""
    from app.core.session import session_manager

    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=_SESSION_NOT_FOUND)
    ensure_session_owner(session, current_user, db)
    return session


def client_ip(request) -> str | None:
    """IP ของผู้ใช้สำหรับบันทึกหลักฐาน (ประวัติการลงนาม/ลบบัญชี)

    nginx ของระบบตั้ง X-Real-IP = $remote_addr ทับค่าที่ผู้ใช้ส่งมาเสมอ จึงเชื่อถือได้ — ถ้าไม่มี ใช้ค่าท้ายสุดของ
    X-Forwarded-For (nginx ต่อท้ายให้) · เดิมใช้ค่าแรกของ X-Forwarded-For ซึ่งผู้ใช้ใส่เองได้ = ปลอม IP ในหลักฐานได้"""
    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return real[:64]
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if forwarded:
        return forwarded[-1][:64]
    return request.client.host if request.client else None
