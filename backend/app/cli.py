"""Operator tools, run on the host with e.g. ``docker compose exec backend python -m app.cli ...``.

* ``backup``          consistent online copy of the SQLite database (safe while running)
* ``check``           ``PRAGMA integrity_check`` on the database
* ``reset-password``  set a new administrator password (local access == trust)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.core import security
from app.core.config import get_settings


def _db_path() -> Path:
    s = get_settings()
    if not s.is_sqlite:
        sys.exit("This command only supports the SQLite backend")
    return Path(s.effective_database_url.split("///", 1)[1])


def cmd_backup(dest: str | None) -> int:
    src = _db_path()
    if not src.exists():
        sys.exit(f"Database not found: {src}")
    out_dir = Path(dest) if dest else src.parent / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"homelab-{datetime.now(UTC):%Y%m%d-%H%M%S}.db"
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(target)
        try:
            source.backup(dst)  # online backup API: consistent even with writers active
        finally:
            dst.close()
    finally:
        source.close()
    target.chmod(0o600)
    print(f"Backup written: {target}")
    return 0


def cmd_check() -> int:
    con = sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True)
    try:
        result = [r[0] for r in con.execute("PRAGMA integrity_check")]
    finally:
        con.close()
    print("\n".join(result))
    return 0 if result == ["ok"] else 1


async def _reset_password(username: str, password: str) -> int:
    from app.database.migrate import upgrade
    from app.database.session import create_engine, create_session_factory
    from app.models import RefreshToken, User

    settings = get_settings()
    await upgrade(settings.effective_database_url)
    engine = create_engine(settings.effective_database_url)
    try:
        async with create_session_factory(engine)() as session:
            user = (
                await session.execute(
                    select(User).where(func.lower(User.username) == username.lower())
                )
            ).scalar_one_or_none()
            if user is None:
                print(f"No such user: {username}", file=sys.stderr)
                return 1
            user.password_hash = security.hash_password(password)
            for tok in (
                await session.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
            ).scalars():
                tok.revoked_at = tok.revoked_at or datetime.now(UTC)  # sign out everywhere
            await session.commit()
    finally:
        await engine.dispose()
    print(f"Password updated for '{username}'; all sessions were signed out.")
    return 0


def cmd_reset_password(username: str) -> int:
    pw = getpass.getpass("New password: ")
    if pw != getpass.getpass("Repeat password: "):
        print("Passwords do not match", file=sys.stderr)
        return 1
    problem = security.validate_password_strength(pw)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    return asyncio.run(_reset_password(username, pw))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup", help="write a consistent copy of the database")
    b.add_argument("--dest", help="directory (default: <data dir>/backups)")
    sub.add_parser("check", help="run SQLite integrity check")
    r = sub.add_parser("reset-password", help="set a new administrator password")
    r.add_argument("username")
    args = parser.parse_args(argv)
    if args.cmd == "backup":
        return cmd_backup(args.dest)
    if args.cmd == "check":
        return cmd_check()
    return cmd_reset_password(args.username)


if __name__ == "__main__":
    sys.exit(main())
