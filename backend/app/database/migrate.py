"""Programmatic Alembic runner used at startup and by tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade_sync(url: str, revision: str = "head") -> None:
    command.upgrade(_config(url), revision)


async def upgrade(url: str, revision: str = "head") -> None:
    # env.py drives its own event loop, so run it off the main loop.
    await asyncio.to_thread(upgrade_sync, url, revision)
