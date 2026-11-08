"""AI หลายค่าย: ค่ายของ API key ส่วนตัว (users.ai_provider / ai_model / ai_base_url)

key เดิมเก็บใน users.encrypted_gemini_key (ชื่อคงเดิม — เก็บ key ของทุกค่าย) · ai_provider ว่าง = gemini

Revision ID: 0013_ai_provider
Revises: 0012_line_login
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_ai_provider"
down_revision = "0012_line_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("ai_provider", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("ai_model", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("ai_base_url", sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("ai_base_url")
        batch.drop_column("ai_model")
        batch.drop_column("ai_provider")
