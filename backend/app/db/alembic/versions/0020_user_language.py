"""ภาษาที่ผู้ใช้เลือกในหน้าโปรไฟล์ (users.language — ค่าเริ่มต้น 'th')

Revision ID: 0020_user_language
Revises: 0019_user_signatures
Create Date: 2026-11-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_user_language"
down_revision = "0019_user_signatures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("language", sa.String(length=10), nullable=False, server_default="th"))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("language")
