"""นับการใช้ AI รายวันในฐานข้อมูล (ดู models.domain.AIUsageDaily)

ทำงานได้เหมือนกันทั้งมีและไม่มี Redis และนับถูกต้องเมื่อมีหลาย replica — การจองโควต้าใช้ UPDATE แบบมี
เงื่อนไข (count < limit) ซึ่งเป็น atomic ในฐานข้อมูล จึงกันกรณีกดแปลงหลายไฟล์พร้อมกันจนเกินโควต้าได้
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.domain import AIUsageDaily

logger = logging.getLogger("ai_usage")

SYSTEM_CONVERSION = "system_conversion"
PERSONAL_REQUEST = "personal_request"
AI_REQUEST = "ai_request"


def today() -> date:
    try:
        return datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()
    except Exception:
        return datetime.now().date()


def _conditional_increment(db, user_id: int, kind: str, by: int, day: date, limit: Optional[int]) -> bool:
    stmt = (
        update(AIUsageDaily)
        .where(AIUsageDaily.user_id == user_id, AIUsageDaily.usage_date == day, AIUsageDaily.kind == kind)
        .values(count=AIUsageDaily.count + by)
    )
    if limit is not None:
        stmt = stmt.where(AIUsageDaily.count + by <= limit)
    if db.execute(stmt).rowcount:
        db.commit()
        return True
    exists = db.query(AIUsageDaily.id).filter_by(user_id=user_id, usage_date=day, kind=kind).first()
    if exists:  # มีแถวอยู่แล้วแต่เกิน limit
        db.rollback()
        return False
    if limit is not None and by > limit:
        return False
    db.add(AIUsageDaily(user_id=user_id, usage_date=day, kind=kind, count=by))
    try:
        db.commit()
        return True
    except IntegrityError:  # อีกคำขอสร้างแถวไปพร้อมกัน — ลอง UPDATE อีกครั้ง
        db.rollback()
        return _conditional_increment(db, user_id, kind, by, day, limit)


def try_reserve(user_id: int, kind: str, limit: int) -> bool:
    """จองโควต้า 1 ครั้ง — คืน False ถ้าใช้ครบ limit แล้ววันนี้"""
    with SessionLocal() as db:
        return _conditional_increment(db, user_id, kind, 1, today(), limit)


def release(user_id: int, kind: str) -> None:
    """คืนโควต้าที่จองไว้ (เช่น งานล้มเหลว หรือ AI ใช้ไม่ได้จนต้องใช้วิธีสำรอง)"""
    with SessionLocal() as db:
        db.execute(
            update(AIUsageDaily)
            .where(AIUsageDaily.user_id == user_id, AIUsageDaily.usage_date == today(),
                   AIUsageDaily.kind == kind, AIUsageDaily.count > 0)
            .values(count=AIUsageDaily.count - 1)
        )
        db.commit()


def add(user_id: Optional[int], kind: str, by: int = 1) -> None:
    if not user_id or by <= 0:
        return
    try:
        with SessionLocal() as db:
            _conditional_increment(db, user_id, kind, by, today(), None)
    except Exception:
        logger.warning("บันทึกการใช้ AI ไม่สำเร็จ user=%s kind=%s", user_id, kind, exc_info=True)


def get_count(db, user_id: int, kind: str, day: Optional[date] = None) -> int:
    row = db.query(AIUsageDaily.count).filter_by(user_id=user_id, usage_date=day or today(), kind=kind).first()
    return int(row[0]) if row else 0


def total(db, kinds: Iterable[str], day: Optional[date] = None) -> int:
    value = (
        db.query(func.coalesce(func.sum(AIUsageDaily.count), 0))
        .filter(AIUsageDaily.usage_date == (day or today()), AIUsageDaily.kind.in_(list(kinds)))
        .scalar()
    )
    return int(value or 0)
