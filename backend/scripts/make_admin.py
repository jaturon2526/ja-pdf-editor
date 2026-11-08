"""ตั้ง/ถอนสิทธิ์ผู้ดูแลระบบจากบรรทัดคำสั่ง (เช่น เว็บใหม่ที่คนอื่นสมัครก่อน หรือผู้ดูแลคนเดียวลืมรหัส)

ใช้ (ในเซิร์ฟเวอร์):
  docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend python -m scripts.make_admin <email>
  ... python -m scripts.make_admin <email> --revoke
"""
import sys

from sqlalchemy import func

from app.db.database import SessionLocal
from app.models.domain import User


def main(email: str, revoke: bool = False) -> int:
    with SessionLocal() as db:
        user = db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()
        if user is None:
            print(f"ไม่พบบัญชี {email} — ให้สมัครสมาชิกก่อน")
            return 1
        if revoke and db.query(User).filter(User.is_admin.is_(True), User.id != user.id).count() == 0:
            print("ถอนสิทธิ์ไม่ได้: เป็นผู้ดูแลระบบคนสุดท้าย")
            return 1
        user.is_admin = not revoke
        db.commit()
        print(f"{'ถอนสิทธิ์' if revoke else 'ตั้งเป็น'}ผู้ดูแลระบบ: {user.email} (id={user.id})")
        return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--revoke"]
    if len(args) != 1:
        sys.exit(__doc__)
    sys.exit(main(args[0], revoke="--revoke" in sys.argv))
