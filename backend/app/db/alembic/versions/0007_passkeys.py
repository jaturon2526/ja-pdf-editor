"""Passkey (WebAuthn) — เข้าสู่ระบบโดยไม่ใช้รหัสผ่าน

Revision ID: 0007_passkeys
Revises: 0006_signing_phase3
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_passkeys"
down_revision = "0006_signing_phase3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passkeys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.String(length=512), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_handle", sa.String(length=128), nullable=False),
        sa.Column("transports", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("aaguid", sa.String(length=64), nullable=True),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_passkeys_user_id", "passkeys", ["user_id"])
    op.create_index("ix_passkeys_credential_id", "passkeys", ["credential_id"], unique=True)


def downgrade() -> None:
    op.drop_table("passkeys")
