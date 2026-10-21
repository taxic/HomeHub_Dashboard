"""Deployment configuration, read from environment variables (prefix ``HOMELAB_``).

User-managed runtime settings (thresholds, intervals, retention) live in the database;
see :mod:`app.schemas.settings`. Secrets only ever come from the environment.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HOMELAB_", env_file=None, extra="ignore")

    environment: str = "production"  # production | development | test
    data_dir: Path = Path("./data")
    database_url: str | None = None  # default: sqlite in data_dir
    secret_key: str | None = Field(default=None, repr=False)
    setup_token: str | None = Field(default=None, repr=False)

    public_url: str | None = None  # externally reachable API URL, shown to clients
    cors_origins: Annotated[list[str], NoDecode] = []
    trusted_proxies: Annotated[list[str], NoDecode] = [
        "127.0.0.1",
        "::1",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
    ]
    docs_enabled: bool = True
    max_request_bytes: int = 256 * 1024

    # auth
    access_token_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_days: int = Field(default=30, ge=1, le=180)
    cookie_secure: bool = True
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_window_seconds: int = Field(default=900, ge=10)

    # docker
    docker_host: str | None = None  # e.g. tcp://docker-socket-proxy:2375
    docker_enabled: bool = True
    docker_control_enabled: bool = False  # master switch for start/stop/restart
    protected_containers: Annotated[list[str], NoDecode] = [
        "homelab-backend",
        "homelab-web",
        "homelab-docker-proxy",
    ]
    log_max_lines: int = Field(default=500, ge=10, le=5000)
    log_max_bytes: int = 256 * 1024

    # host monitoring
    host_proc_path: str | None = None  # e.g. /host/proc when the host /proc is mounted
    host_sys_path: str | None = None  # e.g. /host/sys when the host /sys is mounted (read-only)
    root_path: str = "/"
    storage_allowed_roots: Annotated[list[str], NoDecode] = [
        "/",
        "/host",
        "/mnt",
        "/media",
        "/srv",
        "/data",
    ]
    monitor_enabled: bool = True

    # health checks
    healthcheck_concurrency: int = Field(default=5, ge=1, le=50)
    healthcheck_allow_loopback: bool = False
    healthcheck_allow_private: bool = True

    # notifications (secrets: env only)
    telegram_bot_token: str | None = Field(default=None, repr=False)
    telegram_chat_id: str | None = None

    @field_validator(
        "secret_key",
        "setup_token",
        "public_url",
        "docker_host",
        "host_proc_path",
        "host_sys_path",
        "telegram_bot_token",
        "telegram_chat_id",
        "database_url",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        # docker-compose passes unset variables as empty strings
        return None if isinstance(v, str) and not v.strip() else v

    _split = field_validator(
        "cors_origins",
        "trusted_proxies",
        "protected_containers",
        "storage_allowed_roots",
        mode="before",
    )(_split_csv)

    @property
    def effective_database_url(self) -> str:
        return (
            self.database_url or f"sqlite+aiosqlite:///{(self.data_dir / 'homelab.db').resolve()}"
        )

    @property
    def is_sqlite(self) -> bool:
        return self.effective_database_url.startswith("sqlite")

    def resolve_secret_key(self) -> str:
        """Return the JWT signing key; generate and persist one (mode 0600) if unset."""
        if self.secret_key:
            if len(self.secret_key) < 32:
                raise ValueError("HOMELAB_SECRET_KEY must be at least 32 characters")
            return self.secret_key
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / "secret_key"
        if path.exists():
            return path.read_text().strip()
        key = secrets.token_urlsafe(48)
        path.touch(mode=0o600)
        path.write_text(key)
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
