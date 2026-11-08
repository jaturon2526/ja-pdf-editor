"""รับบริจาคผ่าน PromptPay + สิทธิ์ผู้สนับสนุน + กระดานรายชื่อ

- app_settings : ค่าตั้งที่แอดมินแก้ในหน้าเว็บ (key → JSON) — เลขพร้อมเพย์ ชื่อผู้รับ ระดับสิทธิ์ เปิด/ปิด
- donations    : รายการแจ้งโอน (รอตรวจ/อนุมัติ/ปฏิเสธ) · สลิปเก็บเป็นไฟล์ชั่วคราว ลบทันทีที่ตรวจเสร็จ

Revision ID: 0015_donations
Revises: 0014_user_avatar
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_donations"
down_revision = "0014_user_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "donations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("amount_satang", sa.Integer(), nullable=False),
        sa.Column("transferred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slip_path", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending", index=True),
        sa.Column("show_on_board", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("message", sa.String(length=200), nullable=True),
        sa.Column("admin_note", sa.String(length=255), nullable=True),
        sa.Column("granted_plan", sa.String(length=32), nullable=True),
        sa.Column("granted_days", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


    # แพ็กเกจ pro/premium เดิม seed ไว้โดยไม่ตั้งพื้นที่ → ได้ค่า default 100 MB เท่า free (สิทธิ์ผู้สนับสนุนไม่มีผล)
    # ปรับเฉพาะแถวที่ยังเป็นค่า default (แอดมินตั้งเองแล้วไม่แตะ)
    op.execute("UPDATE plan_configs SET max_storage_mb = 1024 WHERE plan_type = 'pro' AND (max_storage_mb IS NULL OR max_storage_mb = 100)")
    op.execute("UPDATE plan_configs SET max_storage_mb = 5120 WHERE plan_type = 'premium' AND (max_storage_mb IS NULL OR max_storage_mb = 100)")


def downgrade() -> None:
    op.drop_table("donations")
    op.drop_table("app_settings")
