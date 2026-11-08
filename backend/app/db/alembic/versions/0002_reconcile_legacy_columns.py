"""เติมตาราง/คอลัมน์ที่ฐานข้อมูลรุ่นก่อน Alembic อาจขาด (เคยเพิ่มด้วยสคริปต์ SQL/ALTER ด้วยมือ)

Revision ID: 0002_reconcile_legacy
Revises: 0001_baseline
Create Date: 2026-10-17

ฐานข้อมูลใหม่ที่สร้างจาก 0001 จะมีครบอยู่แล้ว migration นี้จึงไม่ทำอะไร (idempotent)
แทนที่สคริปต์เดิม: migration_add_max_storage_mb.sql, app/db/migrate_admin.py, migrate_api_key.py
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_reconcile_legacy"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_EXPECTED_COLUMNS = {
    "users": [
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("profile_picture", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=True),
        sa.Column("accepted_tos", sa.Boolean(), server_default=sa.false(), nullable=True),
        sa.Column("plan_type", sa.String(), server_default="free", nullable=True),
        sa.Column("expire_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_sessions", sa.Integer(), server_default="1", nullable=True),
        sa.Column("encrypted_gemini_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    ],
    "files": [
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("file_size", sa.Integer(), server_default="0", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ],
    "plan_configs": [
        sa.Column("max_sessions", sa.Integer(), server_default="1", nullable=True),
        sa.Column("max_storage_mb", sa.Integer(), server_default="100", nullable=True),
    ],
}

# ค่าพื้นที่เก็บข้อมูลตามแพ็กเกจ (เดิมอยู่ใน migration_add_max_storage_mb.sql)
_STORAGE_DEFAULTS_MB = {"free": 100, "pro": 1024, "premium": 5120}


def upgrade() -> None:
    from app.db.alembic.baseline_schema import build_baseline_metadata

    bind = op.get_bind()
    # ตารางที่ยังไม่มีเลย (เช่น conversion_tasks ในฐานข้อมูลรุ่นแรกๆ) สร้างตาม baseline
    build_baseline_metadata().create_all(bind, checkfirst=True)
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    is_sqlite = bind.dialect.name == "sqlite"
    added_storage_column = False
    for table, columns in _EXPECTED_COLUMNS.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                col = column._copy()
                if is_sqlite and isinstance(getattr(col.server_default, "arg", None), sa.sql.functions.FunctionElement):
                    col.server_default = None  # SQLite เพิ่มคอลัมน์ที่ default เป็นฟังก์ชันไม่ได้ (ใช้เฉพาะตอนทดสอบ)
                op.add_column(table, col)
                if (table, column.name) == ("plan_configs", "max_storage_mb"):
                    added_storage_column = True
    if added_storage_column:
        for plan, mb in _STORAGE_DEFAULTS_MB.items():
            bind.execute(sa.text("UPDATE plan_configs SET max_storage_mb = :mb WHERE plan_type = :plan"),
                         {"mb": mb, "plan": plan})


def downgrade() -> None:
    # คอลัมน์เหล่านี้เป็นส่วนหนึ่งของ schema หลัก — ไม่ลบทิ้งตอน downgrade
    pass
