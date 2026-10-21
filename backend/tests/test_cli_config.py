import sqlite3

import pytest

from app import cli
from app.core.config import Settings
from app.database import migrate


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMELAB_DATA_DIR", str(tmp_path))
    from app.core import config

    config.get_settings.cache_clear()
    migrate.upgrade_sync(f"sqlite+aiosqlite:///{tmp_path / 'homelab.db'}")
    yield tmp_path
    config.get_settings.cache_clear()


def test_backup_is_consistent_and_private(env):
    con = sqlite3.connect(env / "homelab.db")
    con.execute("insert into app_settings(key,value,updated_at) values('k','{}','2024-01-01')")
    con.commit()
    assert cli.main(["backup"]) == 0
    (f,) = list((env / "backups").glob("homelab-*.db"))
    assert oct(f.stat().st_mode & 0o777) == "0o600"
    assert sqlite3.connect(f).execute("select count(*) from app_settings").fetchone()[0] == 1
    assert cli.main(["check"]) == 0


def test_check_detects_corruption(env):
    (env / "homelab.db").write_bytes(b"not a database" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        cli.main(["check"])


async def test_reset_password_revokes_sessions(env):
    from sqlalchemy import select

    from app.core import security
    from app.database.session import create_engine, create_session_factory
    from app.models import RefreshToken, User

    url = f"sqlite+aiosqlite:///{env / 'homelab.db'}"
    engine = create_engine(url)
    async with create_session_factory(engine)() as s:
        u = User(username="admin", password_hash=security.hash_password("old-password-123"))
        s.add(u)
        await s.flush()
        from datetime import UTC, datetime, timedelta

        s.add(
            RefreshToken(
                user_id=u.id,
                family="f",
                token_hash="h",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await s.commit()
    await engine.dispose()
    assert await cli._reset_password("ADMIN", "brand-new-password-456") == 0
    engine = create_engine(url)
    async with create_session_factory(engine)() as s:
        u = (await s.execute(select(User))).scalar_one()
        assert security.verify_password("brand-new-password-456", u.password_hash)
        assert (await s.execute(select(RefreshToken))).scalar_one().revoked_at is not None
    await engine.dispose()
    assert await cli._reset_password("ghost", "whatever-long-password") == 1


def test_empty_env_strings_mean_unset(monkeypatch):
    monkeypatch.setenv("HOMELAB_SECRET_KEY", "")
    monkeypatch.setenv("HOMELAB_PUBLIC_URL", "")
    monkeypatch.setenv("HOMELAB_TELEGRAM_BOT_TOKEN", "  ")
    s = Settings()
    assert s.secret_key is None and s.public_url is None and s.telegram_bot_token is None


def test_short_secret_rejected_and_generated_secret_persisted(tmp_path):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, secret_key="short").resolve_secret_key()
    s = Settings(data_dir=tmp_path)
    k1 = s.resolve_secret_key()
    assert len(k1) >= 32 and s.resolve_secret_key() == k1
    assert oct((tmp_path / "secret_key").stat().st_mode & 0o777) == "0o600"


def test_csv_env_lists(monkeypatch):
    monkeypatch.setenv("HOMELAB_CORS_ORIGINS", "https://a.example, https://b.example")
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]
