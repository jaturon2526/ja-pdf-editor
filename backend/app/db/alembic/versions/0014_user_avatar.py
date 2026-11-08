"""รูปโปรไฟล์ที่ผู้ใช้ตั้งเอง (อัปโหลด หรืออีโมจิที่วาดด้วย Pillow): users.avatar_png / avatar_emoji / avatar_updated_at

เก็บ PNG (~256px, ไม่กี่สิบ KB) ในฐานข้อมูล — ไม่ต้องมีไฟล์บนดิสก์ (หลาย worker/เครื่องเห็นเหมือนกัน)
รูปจาก Google/LINE (users.profile_picture) ยังใช้เมื่อไม่ได้ตั้งเอง

Revision ID: 0014_user_avatar
Revises: 0013_ai_provider
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_user_avatar"
down_revision = "0013_ai_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("avatar_png", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("avatar_emoji", sa.String(length=60), nullable=True))
        batch.add_column(sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("avatar_updated_at")
        batch.drop_column("avatar_emoji")
        batch.drop_column("avatar_png")
