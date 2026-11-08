"""ตารางนับการใช้ AI รายวัน (แทน counter ใน Redis)

Revision ID: 0003_ai_usage_daily
Revises: 0002_reconcile_legacy
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_ai_usage_daily"
down_revision = "0002_reconcile_legacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "usage_date", "kind", name="uq_ai_usage_user_date_kind"),
    )
    op.create_index("ix_ai_usage_daily_user_id", "ai_usage_daily", ["user_id"])
    op.create_index("ix_ai_usage_daily_usage_date", "ai_usage_daily", ["usage_date"])


def downgrade() -> None:
    op.drop_table("ai_usage_daily")
