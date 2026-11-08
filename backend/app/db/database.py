import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ดึง URL จาก Environment Variable (ค่าเริ่มต้นสำหรับรันในเครื่องแบบไม่มี Docker)
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://pdf_user:pdf_password@localhost:5432/pdf_editor")

# pool ต่อ worker (BACKEND_WORKERS) — PostgreSQL max_connections (ค่าเริ่มต้น 100) ต้องมากกว่า workers × (pool + overflow)
_pool = {} if DATABASE_URL.startswith("sqlite") else {
    "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
    "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}
engine = create_engine(DATABASE_URL, **_pool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
