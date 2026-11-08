"""สร้าง (หรือรีเซ็ตรหัสผ่าน) ผู้ใช้ที่ยืนยันอีเมลแล้ว สำหรับ E2E test / ทดลองระบบ

ใช้: python -m scripts.create_test_user <email> <password>   (รันใน backend/ หรือใน container backend)
"""
import sys

from app.core.security import get_password_hash
from app.db.database import SessionLocal
from app.db.migrations import run_migrations
from app.models.domain import User


def main(email: str, password: str) -> None:
    run_migrations()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, plan_type="premium")
            db.add(user)
        user.hashed_password = get_password_hash(password)
        user.is_verified = True
        user.is_active = True
        user.accepted_tos = True
        db.commit()
        print(f"พร้อมใช้งาน: {email} (id={user.id})")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
