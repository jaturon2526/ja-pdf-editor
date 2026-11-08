"""ยืนยันตัวตนด้วย passkey ก่อนลงนาม (ผู้ส่งบังคับได้รายคน)

Revision ID: 0008_signing_passkey
Revises: 0007_passkeys
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_signing_passkey"
down_revision = "0007_passkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("signing_steps") as batch:
        batch.add_column(sa.Column("require_passkey", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("verified_method", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("verified_detail", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("signing_steps") as batch:
        batch.drop_column("verified_at")
        batch.drop_column("verified_detail")
        batch.drop_column("verified_method")
        batch.drop_column("require_passkey")
