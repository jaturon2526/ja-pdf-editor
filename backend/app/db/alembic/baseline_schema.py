"""นิยาม schema ณ baseline (0001) — ใช้ร่วมกันระหว่าง migration 0001 (สร้างทั้งหมด) และ 0002 (สร้างเฉพาะ
ตารางที่ฐานข้อมูลรุ่นเก่าอาจขาด) ห้ามแก้ไฟล์นี้หลังจากนี้: การเปลี่ยน schema ใหม่ให้สร้าง migration ใหม่เสมอ"""
import sqlalchemy as sa


def build_baseline_metadata() -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("profile_picture", sa.String(), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=True),
        sa.Column("accepted_tos", sa.Boolean(), server_default=sa.false(), nullable=True),
        sa.Column("plan_type", sa.String(), nullable=True),
        sa.Column("expire_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_sessions", sa.Integer(), nullable=True),
        sa.Column("encrypted_gemini_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    sa.Index("ix_users_id", metadata.tables["users"].c.id)
    sa.Index("ix_users_email", metadata.tables["users"].c.email, unique=True)

    sa.Table(
        "files",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    sa.Index("ix_files_id", metadata.tables["files"].c.id)

    sa.Table(
        "licenses",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("license_key", sa.String(), nullable=False),
        sa.Column("plan_type", sa.String(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("max_sessions", sa.Integer(), nullable=True),
        sa.Column("is_used", sa.Boolean(), nullable=True),
        sa.Column("used_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    sa.Index("ix_licenses_id", metadata.tables["licenses"].c.id)
    sa.Index("ix_licenses_license_key", metadata.tables["licenses"].c.license_key, unique=True)

    sa.Table(
        "plan_configs",
        metadata,
        sa.Column("plan_type", sa.String(), primary_key=True),
        sa.Column("max_sessions", sa.Integer(), nullable=True),
        sa.Column("max_storage_mb", sa.Integer(), nullable=True),
    )
    sa.Index("ix_plan_configs_plan_type", metadata.tables["plan_configs"].c.plan_type)

    sa.Table(
        "conversion_tasks",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("file_record_id", sa.Integer(), sa.ForeignKey("files.id"), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("result_file_path", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    sa.Index("ix_conversion_tasks_id", metadata.tables["conversion_tasks"].c.id)


    return metadata
