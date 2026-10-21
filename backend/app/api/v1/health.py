from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.deps import get_ctx, get_session
from app.core.context import AppContext
from app.core.errors import UnavailableError

router = APIRouter(prefix="/health", tags=["health"])


class HealthOut(BaseModel):
    status: str
    version: str
    time: datetime
    public_url: str | None = None


@router.get("", response_model=HealthOut)
async def health(ctx: AppContext = Depends(get_ctx)) -> HealthOut:
    """Public, minimal liveness information (safe to expose to clients before login)."""
    return HealthOut(
        status="ok", version=__version__, time=datetime.now(UTC), public_url=ctx.settings.public_url
    )


@router.get("/live", response_model=HealthOut)
async def live(ctx: AppContext = Depends(get_ctx)) -> HealthOut:
    return await health(ctx)


@router.get("/ready", response_model=HealthOut)
async def ready(
    ctx: AppContext = Depends(get_ctx), session: AsyncSession = Depends(get_session)
) -> HealthOut:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise UnavailableError("Database is not ready", code="not_ready") from exc
    return await health(ctx)
