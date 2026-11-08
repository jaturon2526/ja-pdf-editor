from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import get_db
from app.models.domain import User
from app.core.security import get_password_hash
from datetime import datetime, timedelta
import random

DATABASE_URL = "postgresql://pdf_user:pdf_password@db:5432/pdf_editor"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

mock_users = [
    {
        "email": "somchai.free@example.com",
        "display_name": "สมชาย ใจดี",
        "plan_type": "free",
        "is_active": True,
        "is_verified": True
    },
    {
        "email": "sri.pro@example.com",
        "display_name": "ศรีสุดา น่ารัก",
        "plan_type": "pro",
        "expire_date": datetime.now() + timedelta(days=30),
        "is_active": True,
        "is_verified": True
    },
    {
        "email": "mana.premium@example.com",
        "display_name": "มานะ อดทน",
        "plan_type": "premium",
        "expire_date": datetime.now() + timedelta(days=365),
        "is_active": True,
        "is_verified": True
    },
    {
        "email": "suspended.user@example.com",
        "display_name": "นายสายลับ โดนแบน",
        "plan_type": "free",
        "is_active": False,
        "is_verified": True
    },
    {
        "email": "boss.premium@example.com",
        "display_name": "ท่านประธาน",
        "plan_type": "premium",
        "expire_date": None, # ถาวร
        "is_active": True,
        "is_verified": True
    }
]

for mu in mock_users:
    if not db.query(User).filter(User.email == mu["email"]).first():
        u = User(
            email=mu["email"],
            display_name=mu["display_name"],
            hashed_password=get_password_hash("Password123!"),
            is_active=mu["is_active"],
            is_verified=mu["is_verified"],
            plan_type=mu["plan_type"],
            expire_date=mu.get("expire_date")
        )
        db.add(u)

db.commit()
print("Mock users seeded successfully!")
