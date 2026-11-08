"""ลบบัญชีผู้ใช้: เก็บชื่อ/อีเมลของผู้ลงนามที่ลบบัญชีไว้ในประวัติการลงนามของเอกสารคนอื่น

Revision ID: 0011_account_deletion
Revises: 0010_service_usage
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_account_deletion"
down_revision = "0010_service_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("signing_steps") as batch:
        batch.add_column(sa.Column("signer_label", sa.String(length=255), nullable=True))
    with op.batch_alter_table("signing_events") as batch:
        batch.add_column(sa.Column("actor_label", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("signing_events") as batch:
        batch.drop_column("actor_label")
    with op.batch_alter_table("signing_steps") as batch:
        batch.drop_column("signer_label")
