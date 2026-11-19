"""passkey ที่ปลดล็อกใบรับรองที่เก็บไว้ได้ (WebAuthn PRF — รหัสถูกเข้ารหัสในเครื่องผู้ใช้)

Revision ID: 0018_certificate_passkeys
Revises: 0017_user_certificates
Create Date: 2026-11-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_certificate_passkeys"
down_revision = "0017_user_certificates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "certificate_passkeys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("certificate_id", sa.Integer(), sa.ForeignKey("user_certificates.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("passkey_id", sa.Integer(), sa.ForeignKey("passkeys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prf_salt", sa.String(length=64), nullable=False),
        sa.Column("wrapped", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("certificate_id", "passkey_id", name="uq_certificate_passkeys_cert_pk"),
    )
    op.create_index("ix_certificate_passkeys_certificate_id", "certificate_passkeys", ["certificate_id"])
    op.create_index("ix_certificate_passkeys_passkey_id", "certificate_passkeys", ["passkey_id"])


def downgrade() -> None:
    op.drop_index("ix_certificate_passkeys_passkey_id", table_name="certificate_passkeys")
    op.drop_index("ix_certificate_passkeys_certificate_id", table_name="certificate_passkeys")
    op.drop_table("certificate_passkeys")
