"""ส่งเอกสารให้ลงนามตามลำดับ: คำขอ ขั้นตอน บันทึกเหตุการณ์ และแจ้งเตือนในระบบ

Revision ID: 0004_sequential_signing
Revises: 0003_ai_usage_daily
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_sequential_signing"
down_revision = "0003_ai_usage_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signing_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("result_file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="in_progress"),
        sa.Column("current_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_signing_requests_owner_id", "signing_requests", ["owner_id"])
    op.create_index("ix_signing_requests_status", "signing_requests", ["status"])

    op.create_table(
        "signing_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("signing_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("signer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sign_type", sa.String(length=20), nullable=False, server_default="either"),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("x0", sa.Float(), nullable=False),
        sa.Column("y0", sa.Float(), nullable=False),
        sa.Column("x1", sa.Float(), nullable=False),
        sa.Column("y1", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="waiting"),
        sa.Column("signed_type", sa.String(length=20), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cert_subject", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.UniqueConstraint("request_id", "order", name="uq_signing_step_order"),
    )
    op.create_index("ix_signing_steps_request_id", "signing_steps", ["request_id"])
    op.create_index("ix_signing_steps_signer_user_id", "signing_steps", ["signer_user_id"])

    op.create_table(
        "signing_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("signing_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("sha256_before", sa.String(length=64), nullable=True),
        sa.Column("sha256_after", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_signing_events_request_id", "signing_events", ["request_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("signing_requests.id", ondelete="CASCADE"), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("signing_events")
    op.drop_table("signing_steps")
    op.drop_table("signing_requests")
