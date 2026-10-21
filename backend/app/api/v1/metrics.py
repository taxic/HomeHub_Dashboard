from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, current_user, get_ctx, get_session
from app.core.context import AppContext
from app.schemas.metrics import CurrentMetrics, HistoryResponse
from app.services import metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/current", response_model=CurrentMetrics)
async def current(_: Principal = Depends(current_user), ctx: AppContext = Depends(get_ctx)):
    mon = ctx.monitor
    if mon is None or mon.host is None:
        return CurrentMetrics(available=False, host=None, sampled_at=None)
    return CurrentMetrics(
        available=True, host=mon.host, sampled_at=mon.host.sampled_at, stale=mon.is_stale()
    )


@router.get("/history", response_model=HistoryResponse)
async def history(
    range: Literal["1h", "6h", "24h", "7d", "30d"] = Query(default="1h"),  # noqa: A002
    _: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> HistoryResponse:
    return await metrics_service.history(session, range)
