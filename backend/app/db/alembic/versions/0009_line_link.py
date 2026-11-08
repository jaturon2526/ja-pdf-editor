"""ผูกบัญชี LINE เพื่อรับแจ้งเตือนการลงนาม

Revision ID: 0009_line_link
Revises: 0008_signing_passkey
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_line_link"
down_revision = "0008_signing_passkey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("line_user_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("line_display_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("line_linked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("line_notifications", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_users_line_user_id", "users", ["line_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_line_user_id", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("line_notifications")
        batch.drop_column("line_linked_at")
        batch.drop_column("line_display_name")
        batch.drop_column("line_user_id")
