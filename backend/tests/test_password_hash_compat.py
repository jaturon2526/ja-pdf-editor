"""SEC-05: ย้ายจาก passlib ไปใช้ bcrypt ตรง ๆ — hash ที่ passlib 1.7.4 + bcrypt 3.2.2 สร้างไว้ต้องตรวจได้เหมือนเดิม"""
from app.core.security import get_password_hash, verify_password

# สร้างด้วย passlib.context.CryptContext(schemes=["bcrypt"]).hash(...) (ของจริงจาก production รุ่นก่อน)
PASSLIB_HASH = "$2b$12$URlHBS1rehuxxW82owONTu5BS0pFueTEb6BQzs9BeX82KLRNxd1GK"  # "password123"
PASSLIB_LONG = "$2b$12$QspBrFE8jgPHPZbIZScPn.W.tms4kZ9e/KTjh5imjIgEW/6kQpMbC"  # "ก" * 30 (90 ไบต์ > 72)


def test_passlib_hashes_still_verify():
    assert verify_password("password123", PASSLIB_HASH)
    assert not verify_password("password124", PASSLIB_HASH)
    # passlib ตัดเหลือ 72 ไบต์แรก — รหัสยาวเกินยังเข้าได้ และพฤติกรรมเดียวกันคงอยู่
    assert verify_password("ก" * 30, PASSLIB_LONG)
    assert verify_password("ก" * 24, PASSLIB_LONG)


def test_new_hashes_and_bad_inputs():
    h = get_password_hash("ก" * 40)  # ยาวเกิน 72 ไบต์ต้องไม่ error
    assert h.startswith("$2b$12$") and verify_password("ก" * 40, h)
    assert not verify_password("x", "not-a-bcrypt-hash")
    assert not verify_password("", h) and not verify_password("x", None)
