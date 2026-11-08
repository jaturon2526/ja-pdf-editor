"""นับการใช้บริการภายนอกรายวัน (อีเมล / LINE) สำหรับหน้าโควต้าของแอดมิน

Revision ID: 0010_service_usage
Revises: 0009_line_link
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_service_usage"
down_revision = "0009_line_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_usage_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("usage_date", "service", name="uq_service_usage_date_service"),
    )
    op.create_index("ix_service_usage_daily_usage_date", "service_usage_daily", ["usage_date"])


def downgrade() -> None:
    op.drop_table("service_usage_daily")
