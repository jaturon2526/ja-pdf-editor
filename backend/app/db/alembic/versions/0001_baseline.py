"""baseline schema (users, files, licenses, plan_configs, conversion_tasks)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-17

ฐานข้อมูลที่มีอยู่ก่อนใช้ Alembic (สร้างด้วย Base.metadata.create_all) จะถูก stamp เป็น revision นี้
อัตโนมัติ (ดู app/db/migrations.py) แล้ว 0002 จะเติมคอลัมน์ที่อาจขาดให้ครบ
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.alembic.baseline_schema import build_baseline_metadata

    build_baseline_metadata().create_all(op.get_bind())


def downgrade() -> None:
    op.drop_table("conversion_tasks")
    op.drop_table("plan_configs")
    op.drop_table("licenses")
    op.drop_table("files")
    op.drop_table("users")
