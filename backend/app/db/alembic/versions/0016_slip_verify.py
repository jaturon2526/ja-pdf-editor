"""ตรวจสลิป: เลขอ้างอิงจาก QR ในสลิป (กันแจ้งซ้ำ) + ผลตรวจจากบริการตรวจสลิป

+ ระดับสิทธิ์เริ่มต้นเปลี่ยนเป็น 49 / 299 / 499 บาท (ผู้ใช้ขอ) — แก้ค่าที่บันทึกไว้เฉพาะเมื่อยังเป็นชุดเดิม 50/300/500
+ ลดพื้นที่แพ็กเกจผู้สนับสนุนให้พอกับดิสก์เซิร์ฟเวอร์ (ผู้ใช้ขอ 2026-11-08): pro 500 MB, premium 1024 MB
  (ปรับเฉพาะแถวที่ยังเป็นค่าที่ 0015 ตั้งหรือค่า default เดิม — แอดมินตั้งเองแล้วไม่แตะ)

Revision ID: 0016_slip_verify
Revises: 0015_donations
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_slip_verify"
down_revision = "0015_donations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("donations") as batch:
        batch.add_column(sa.Column("slip_payload", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("slip_ref", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("slip_bank", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("verify_status", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("verify_detail", sa.Text(), nullable=True))
        batch.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_donations_slip_ref", ["slip_ref"])
    op.execute("UPDATE plan_configs SET max_storage_mb = 500 WHERE plan_type = 'pro' AND (max_storage_mb IS NULL OR max_storage_mb IN (100, 1024))")
    op.execute("UPDATE plan_configs SET max_storage_mb = 1024 WHERE plan_type = 'premium' AND (max_storage_mb IS NULL OR max_storage_mb IN (100, 5120))")


    _retier_saved_defaults()


OLD_TIERS = [{"min_amount": 50, "plan": "pro", "days": 30}, {"min_amount": 300, "plan": "pro", "days": 365},
             {"min_amount": 500, "plan": "premium", "days": 365}]
NEW_TIERS = [{"min_amount": 49, "plan": "pro", "days": 30}, {"min_amount": 299, "plan": "pro", "days": 365},
             {"min_amount": 499, "plan": "premium", "days": 365}]


def _retier_saved_defaults() -> None:
    import json

    conn = op.get_bind()
    row = conn.execute(sa.text("SELECT value FROM app_settings WHERE key = 'donation'")).fetchone()
    if not row:
        return
    try:
        cfg = json.loads(row[0])
    except ValueError:
        return
    if cfg.get("tiers") == OLD_TIERS:
        cfg["tiers"] = NEW_TIERS
        conn.execute(sa.text("UPDATE app_settings SET value = :v WHERE key = 'donation'"),
                     {"v": json.dumps(cfg, ensure_ascii=False)})


def downgrade() -> None:
    with op.batch_alter_table("donations") as batch:
        batch.drop_index("ix_donations_slip_ref")
        for col in ("verified_at", "verify_detail", "verify_status", "slip_bank", "slip_ref", "slip_payload"):
            batch.drop_column(col)
