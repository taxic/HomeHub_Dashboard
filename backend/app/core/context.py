"""Process-wide application context stored on ``app.state.ctx``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.ratelimit import FailureLimiter
from app.schemas.settings import AppSettings

if TYPE_CHECKING:
    from app.monitoring.docker_gateway import DockerGateway
    from app.monitoring.monitor import Monitor


@dataclass
class AppContext:
    settings: Settings
    secret_key: str
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    runtime: AppSettings = field(default_factory=AppSettings)
    account_limiter: FailureLimiter | None = None
    ip_limiter: FailureLimiter | None = None
    docker: DockerGateway | None = None
    monitor: Monitor | None = None
    extras: dict[str, Any] = field(default_factory=dict)
