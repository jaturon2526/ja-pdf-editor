from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import ConfigDict, BaseModel
from typing import List, Optional
from datetime import datetime

from app.db.database import get_db
from app.models.domain import User, FileRecord
from app.api.deps import get_current_admin_user

router = APIRouter(prefix="/admin", tags=["admin"])

class AdminUserObj(BaseModel):
    id: int
    email: str
    display_name: Optional[str]
    is_active: bool
    is_admin: bool
    is_verified: bool
    plan_type: str
    expire_date: Optional[datetime]
    total_files: int
    total_storage: int
    ai_requests_today: int = 0

class AdminUserListResponse(BaseModel):
    users: List[AdminUserObj]

class AdminUpdatePlanRequest(BaseModel):
    plan_type: str
    expire_date: Optional[datetime] = None

class AdminUpdateStatusRequest(BaseModel):
    is_active: bool
    is_admin: bool

class AdminStatsResponse(BaseModel):
    total_users: int
    total_files: int
    total_storage: int
    ai_requests_today: int = 0

@router.get("/users", response_model=AdminUserListResponse)
def get_all_users(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    users = db.query(User).order_by(User.id.asc()).all()
    results = []
    for u in users:
        # Calculate storage usage
        files = db.query(FileRecord).filter(FileRecord.user_id == u.id).all()
        total_files = len(files)
        total_storage = sum(f.file_size for f in files if f.file_size)
        
        results.append(AdminUserObj(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            is_active=u.is_active,
            is_admin=u.is_admin,
            is_verified=u.is_verified,
            plan_type=u.plan_type,
            expire_date=u.expire_date,
            total_files=total_files,
            total_storage=total_storage
        ))
    return AdminUserListResponse(users=results)

@router.put("/users/{user_id}/plan")
def update_user_plan(user_id: int, payload: AdminUpdatePlanRequest, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.plan_type = payload.plan_type
    user.expire_date = payload.expire_date
    db.commit()
    return {"status": "ok"}

@router.put("/users/{user_id}/status")
def update_user_status(user_id: int, payload: AdminUpdateStatusRequest, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = payload.is_active
    user.is_admin = payload.is_admin
    db.commit()
    return {"status": "ok"}

@router.get("/stats", response_model=AdminStatsResponse)
def get_stats(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    total_users = db.query(User).count()
    total_files = db.query(FileRecord).count()
    total_storage = db.query(func.sum(FileRecord.file_size)).scalar() or 0
    from app.services import ai_usage

    ai_requests = ai_usage.total(db, [ai_usage.AI_REQUEST])

    return AdminStatsResponse(
        total_users=total_users,
        total_files=total_files,
        total_storage=int(total_storage),
        ai_requests_today=ai_requests
    )

class PlanConfigResponse(BaseModel):
    plan_type: str
    max_sessions: int
    max_storage_mb: int

    model_config = ConfigDict(from_attributes=True)

class PlanConfigUpdateRequest(BaseModel):
    max_sessions: int
    max_storage_mb: int

@router.get("/plans", response_model=List[PlanConfigResponse])
def get_plans(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    from app.models.domain import PlanConfig
    plans = db.query(PlanConfig).all()
    
    order = {"free": 1, "pro": 2, "premium": 3}
    plans.sort(key=lambda x: order.get(x.plan_type, 99))
    return plans

@router.put("/plans/{plan_type}", response_model=PlanConfigResponse)
def update_plan(plan_type: str, payload: PlanConfigUpdateRequest, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    from app.models.domain import PlanConfig
    plan = db.query(PlanConfig).filter(PlanConfig.plan_type == plan_type).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan.max_sessions = payload.max_sessions
    plan.max_storage_mb = payload.max_storage_mb
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/quotas")
def get_quotas(refresh: bool = False, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """โควต้า/เครดิตของบริการภายนอก + สถิติรายวันย้อนหลัง 30 วัน (refresh=true ดึงจาก API ใหม่ไม่ใช้ cache)"""
    from datetime import timezone as _tz

    from app.core.config import settings
    from app.services import quota_service

    return {
        "items": quota_service.snapshot(db, refresh=refresh),
        "history": quota_service.history(db),
        "series": quota_service.chart_series(),
        "alert_percent": settings.QUOTA_ALERT_PERCENT,
        "checked_at": datetime.now(_tz.utc).isoformat(),
    }
