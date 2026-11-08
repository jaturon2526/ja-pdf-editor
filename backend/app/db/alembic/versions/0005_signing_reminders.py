"""ลงนามตามลำดับ เฟส 2: วันครบกำหนด การส่งเตือน และตั้งค่ารับอีเมลแจ้งเตือน

Revision ID: 0005_signing_reminders
Revises: 0004_sequential_signing
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_signing_reminders"
down_revision = "0004_sequential_signing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("signing_requests") as batch:
        batch.add_column(sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("due_soon_notified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("overdue_notified_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("signing_email_notifications", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("signing_email_notifications")
    with op.batch_alter_table("signing_requests") as batch:
        batch.drop_column("overdue_notified_at")
        batch.drop_column("due_soon_notified_at")
        batch.drop_column("last_reminded_at")
        batch.drop_column("due_at")
