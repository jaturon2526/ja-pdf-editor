"""เข้าสู่ระบบด้วย LINE: users.line_login_id (userId จาก LINE Login)

Revision ID: 0012_line_login
Revises: 0011_account_deletion
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_line_login"
down_revision = "0011_account_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("line_login_id", sa.String(length=64), nullable=True))
    op.create_index("ix_users_line_login_id", "users", ["line_login_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_line_login_id", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("line_login_id")
