"""ลงนาม เฟส 3: ลงนามพร้อมกันในขั้นเดียวกัน (stage) และเชิญคนที่ยังไม่มีบัญชี (invite_email)

Revision ID: 0006_signing_phase3
Revises: 0005_signing_reminders
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_signing_phase3"
down_revision = "0005_signing_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("signing_steps") as batch:
        batch.add_column(sa.Column("stage", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("invite_email", sa.String(length=255), nullable=True))
        batch.alter_column("signer_user_id", existing_type=sa.Integer(), nullable=True)
        batch.create_index(batch.f("ix_signing_steps_invite_email"), ["invite_email"], unique=False)
    # คำขอเดิมเป็นแบบทีละคน: ขั้น = ลำดับ
    op.execute('UPDATE signing_steps SET stage = "order"')


def downgrade() -> None:
    op.execute("DELETE FROM signing_steps WHERE signer_user_id IS NULL")
    with op.batch_alter_table("signing_steps") as batch:
        batch.drop_index(batch.f("ix_signing_steps_invite_email"))
        batch.alter_column("signer_user_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("invite_email")
        batch.drop_column("stage")
