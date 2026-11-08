"""ผู้ใช้สำหรับ load test — รันใน container backend (run.sh ส่งไฟล์นี้ทาง stdin: docker exec -i pdf_backend_prod python - ...)

  python - seed <จำนวน> <รหัสผ่าน>   สร้าง lt0001@loadtest.invalid … (ยืนยันอีเมลแล้ว, แพ็กเกจ premium, ยอมรับข้อตกลง)
                                    แล้วพิมพ์ token เข้าระบบของทุกบัญชี (บรรทัด TOKEN<tab>อีเมล<tab>token) — Locust ใช้ token นี้
                                    แทนการ login ทุกคนพร้อมกัน (ซึ่งจะโดน rate limit ของหน้าเข้าสู่ระบบตัดตามที่ควรเป็น)
  python - cleanup                  ลบบัญชี @loadtest.invalid ทั้งหมดพร้อมไฟล์ (ไม่ส่งอีเมลแจ้งลบบัญชี)
โดเมน .invalid ส่งอีเมลไม่ได้จริงตามมาตรฐาน — และ load test ไม่มีขั้นตอนที่ส่งอีเมล (login/อัปโหลด/แก้ไข/บันทึก)"""
import sys

sys.path.insert(0, "/app")

from app.core.security import get_password_hash  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.domain import User  # noqa: E402

DOMAIN = "@loadtest.invalid"


def seed(count: int, password: str) -> None:
    db = SessionLocal()
    hashed = get_password_hash(password)
    made = 0
    try:
        for i in range(1, count + 1):
            email = f"lt{i:04d}{DOMAIN}"
            if db.query(User.id).filter(User.email == email).first():
                continue
            db.add(User(email=email, display_name=f"Load test {i}", hashed_password=hashed, is_active=True,
                        is_verified=True, accepted_tos=True, plan_type="premium", max_sessions=5))
            made += 1
        db.commit()
        from app.api.routes_auth import issue_login_token
        for i in range(1, count + 1):
            email = f"lt{i:04d}{DOMAIN}"
            user = db.query(User).filter(User.email == email).first()
            print(f"TOKEN\t{email}\t{issue_login_token(db, user)['access_token']}")
    finally:
        db.close()
    print(f"seed: สร้างใหม่ {made} บัญชี (รวม {count})", file=sys.stderr)


def cleanup() -> None:
    from app.services import account_service, mailer
    from app.services.signing_service import ClientInfo

    mailer.send = lambda *a, **k: None  # ไม่ส่งอีเมล "บัญชีถูกลบ"
    db = SessionLocal()
    removed = 0
    try:
        for (uid,) in db.query(User.id).filter(User.email.like(f"%{DOMAIN}")).all():
            user = db.get(User, uid)
            account_service.delete_account(db, user, ClientInfo(ip="loadtest", user_agent="loadtest-cleanup"))
            removed += 1
    finally:
        db.close()
    print(f"cleanup: ลบ {removed} บัญชี")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "seed":
        seed(int(sys.argv[2]), sys.argv[3])
    elif cmd == "cleanup":
        cleanup()
    else:
        sys.exit("ใช้: seed <จำนวน> <รหัสผ่าน> | cleanup")
