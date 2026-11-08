"""Alembic environment — ใช้ได้ทั้งจาก CLI (`alembic upgrade head` ใน backend/) และจากแอปตอน start
(app/db/migrations.py ส่ง connection ที่ถือ advisory lock ไว้แล้วมาทาง config.attributes)"""
from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models.domain  # noqa: F401  ลงทะเบียน model ทั้งหมดกับ Base.metadata (ใช้กับ autogenerate)
from app.db.database import DATABASE_URL, Base

config = context.config
target_metadata = Base.metadata


def _configure_and_run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure_and_run(connection)
        return
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = DATABASE_URL
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as conn:
        _configure_and_run(conn)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
