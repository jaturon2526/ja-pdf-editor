"""รูปลายเซ็นที่ผู้ใช้บันทึกไว้และปลดล็อกด้วย Passkey (WebAuthn PRF — เข้ารหัสในเบราว์เซอร์)

Revision ID: 0019_user_signatures
Revises: 0018_certificate_passkeys
Create Date: 2026-11-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_user_signatures"
down_revision = "0018_certificate_passkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_signatures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("passkey_id", sa.Integer(), sa.ForeignKey("passkeys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("prf_salt", sa.String(length=64), nullable=False),
        sa.Column("encrypted_png", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_signatures_user_id", "user_signatures", ["user_id"])
    op.create_index("ix_user_signatures_passkey_id", "user_signatures", ["passkey_id"])


def downgrade() -> None:
    op.drop_index("ix_user_signatures_passkey_id", table_name="user_signatures")
    op.drop_index("ix_user_signatures_user_id", table_name="user_signatures")
    op.drop_table("user_signatures")
