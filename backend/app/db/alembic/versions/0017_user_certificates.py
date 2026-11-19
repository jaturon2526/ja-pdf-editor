"""ใบรับรองลายเซ็นดิจิทัลที่ผู้ใช้เก็บไว้บนระบบ (ไม่เก็บรหัสผ่าน)

Revision ID: 0017_user_certificates
Revises: 0016_slip_verify
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_user_certificates"
down_revision = "0016_slip_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_certificates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("subject_cn", sa.String(length=255), nullable=True),
        sa.Column("organization", sa.String(length=255), nullable=True),
        sa.Column("issuer_cn", sa.String(length=255), nullable=True),
        sa.Column("serial_hex", sa.String(length=130), nullable=True),
        sa.Column("fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("self_signed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pfx_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "fingerprint_sha256", name="uq_user_certificates_user_fp"),
    )
    op.create_index("ix_user_certificates_user_id", "user_certificates", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_certificates_user_id", table_name="user_certificates")
    op.drop_table("user_certificates")
