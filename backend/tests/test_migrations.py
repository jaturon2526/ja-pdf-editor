def test_schema_matches_models(client):
    """หลัง migrate แล้ว schema ต้องตรงกับ models (ถ้า fail = แก้ model แล้วลืมสร้าง migration)"""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    import app.models.domain  # noqa: F401
    from app.db.database import Base, engine

    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_legacy_database_is_upgraded(tmp_path, monkeypatch):
    import sqlalchemy as sa

    from app.db import migrations

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    eng = sa.create_engine(url)
    with eng.begin() as c:
        c.execute(sa.text("create table users (id integer primary key, email varchar not null, hashed_password varchar not null)"))
        c.execute(sa.text("create table plan_configs (plan_type varchar primary key, max_sessions integer)"))
        c.execute(sa.text("insert into plan_configs values ('premium', 10)"))
    monkeypatch.setattr(migrations, "engine", eng)
    monkeypatch.setattr(migrations, "DATABASE_URL", url)
    migrations.run_migrations()
    with eng.connect() as c:
        cols = {col["name"] for col in sa.inspect(c).get_columns("users")}
        assert {"is_admin", "encrypted_gemini_key", "accepted_tos"} <= cols
        assert c.execute(sa.text("select max_storage_mb from plan_configs")).scalar() == 5120
        assert {"files", "conversion_tasks", "licenses"} <= set(sa.inspect(c).get_table_names())


def test_postgres_fresh_and_restart(monkeypatch):
    """ฐานข้อมูล PostgreSQL ว่าง: สร้างครบทุกตารางและตรงกับ models · start ซ้ำไม่พัง
    รันเมื่อมี PostgreSQL ทดสอบ: PDF_TEST_PG_URL=postgresql://user@host:port/ชื่อฐานข้อมูลว่าง"""
    import os

    import pytest
    import sqlalchemy as sa
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    url = os.environ.get("PDF_TEST_PG_URL")
    if not url:
        pytest.skip("ไม่ได้ตั้ง PDF_TEST_PG_URL")
    import app.models.domain  # noqa: F401
    from app.db import migrations
    from app.db.database import Base

    eng = sa.create_engine(url)
    with eng.begin() as c:
        c.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    monkeypatch.setattr(migrations, "engine", eng)
    monkeypatch.setattr(migrations, "DATABASE_URL", url)
    migrations.run_migrations()
    migrations.run_migrations()
    with eng.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
