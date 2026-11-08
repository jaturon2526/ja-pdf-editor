"""รัน Alembic migration ตอน start แอป

- ฐานข้อมูลใหม่ (ว่าง): สร้างทุกตารางผ่าน migration ตั้งแต่ 0001
- ฐานข้อมูลเดิมก่อนใช้ Alembic (มีตาราง users แต่ไม่มี alembic_version): stamp เป็น 0001_baseline
  ก่อน แล้วค่อย upgrade — 0002 จะเติมคอลัมน์ที่ขาดให้ครบ
- PostgreSQL: ถือ advisory lock ระหว่าง migrate กันหลาย replica start พร้อมกันแล้วชนกัน

สร้าง migration ใหม่ (รันใน backend/):  alembic revision --autogenerate -m "อธิบายการเปลี่ยนแปลง"
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.db.database import DATABASE_URL, engine

logger = logging.getLogger("migrations")

BASELINE_REVISION = "0001_baseline"
_ADVISORY_LOCK_ID = 727_001  # ค่าคงที่ใดๆ ที่ไม่ชนกับ advisory lock อื่นในระบบ


def _alembic_config(connection=None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).with_name("alembic")))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def run_migrations() -> None:
    with engine.connect() as conn:
        is_pg = conn.dialect.name == "postgresql"
        if is_pg:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_ID})
            conn.commit()
        try:
            cfg = _alembic_config(conn)
            tables = set(inspect(conn).get_table_names())
            if "alembic_version" not in tables and "users" in tables:
                logger.info("พบฐานข้อมูลรุ่นก่อนใช้ Alembic — stamp เป็น %s", BASELINE_REVISION)
                command.stamp(cfg, BASELINE_REVISION)
                conn.commit()
            command.upgrade(cfg, "head")
            conn.commit()
        finally:
            if is_pg:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_ID})
                conn.commit()
