import sqlite3

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.database import migrate
from app.database.base import Base


def test_upgrade_creates_schema_matching_models(tmp_path):
    db = tmp_path / "m.db"
    migrate.upgrade_sync(f"sqlite+aiosqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models drifted from migrations: {diff}"


def test_downgrade_to_base_and_upgrade_again(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    migrate.upgrade_sync(url)
    from alembic import command

    command.downgrade(migrate._config(url), "base")
    con = sqlite3.connect(tmp_path / "m.db")
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert tables <= {"alembic_version"}
    migrate.upgrade_sync(url)


def test_upgrade_is_idempotent_and_preserves_data(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    migrate.upgrade_sync(url)
    con = sqlite3.connect(tmp_path / "m.db")
    con.execute("insert into app_settings(key,value,updated_at) values('k','{}','2024-01-01')")
    con.commit()
    migrate.upgrade_sync(url)
    assert con.execute("select count(*) from app_settings").fetchone()[0] == 1
