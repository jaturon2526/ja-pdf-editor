from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.domain import User, License
from app.api.deps import get_current_active_user
from app.models.auth_schemas import UserResponse

router = APIRouter()

class LicenseApplyRequest(BaseModel):
    license_key: str

@router.post("/apply", response_model=UserResponse)
def apply_license(req: LicenseApplyRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    db_license = db.query(License).filter(License.license_key == req.license_key).first()
    
    if not db_license:
        raise HTTPException(status_code=404, detail="Invalid license key")
    
    if db_license.is_used:
        raise HTTPException(status_code=400, detail="License key has already been used")
    
    # อัปเดตข้อมูลผู้ใช้
    current_user.plan_type = db_license.plan_type
    current_user.max_sessions = db_license.max_sessions
    
    if db_license.duration_days:
        # ถ้ายังไม่เคยมีวันหมดอายุ หรือหมดอายุไปแล้ว ให้เริ่มนับใหม่จากวันนี้
        if not current_user.expire_date or current_user.expire_date < datetime.now(timezone.utc):
            current_user.expire_date = datetime.now(timezone.utc) + timedelta(days=db_license.duration_days)
        else:
            # ถ้ายังมีวันเหลืออยู่ ให้ทบเข้าไป
            current_user.expire_date = current_user.expire_date + timedelta(days=db_license.duration_days)
    else:
        # ถ้า duration เป็น null คือถาวร
        current_user.expire_date = None
        
    # มาร์ค License ว่าถูกใช้แล้ว
    db_license.is_used = True
    db_license.used_by_user_id = current_user.id
    db_license.used_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(current_user)
    
    return current_user
