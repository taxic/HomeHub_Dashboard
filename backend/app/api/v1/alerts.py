from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PageParams, Principal, current_user, get_session, pagination
from app.core.errors import NotFoundError
from app.database.base import utcnow
from app.models import Alert, Event
from app.schemas.alert import AlertOut, EventOut
from app.schemas.common import Page
from app.services.events import record_event

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=Page[AlertOut])
async def list_alerts(
    status: Literal["open", "resolved", "all"] = "open",
    severity: Literal["warning", "critical"] | None = None,
    page: PageParams = Depends(pagination),
    _: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Alert)
    if status != "all":
        q = q.where(Alert.status == status)
    if severity:
        q = q.where(Alert.severity == severity)
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                q.order_by(Alert.last_seen_at.desc(), Alert.id.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page(items=rows, total=total, limit=page.limit, offset=page.offset)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge(
    alert_id: int,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert not found")
    if alert.acknowledged_at is None:
        alert.acknowledged_at = utcnow()
        alert.acknowledged_by = principal.name
        record_event(
            session,
            "alert.acknowledged",
            f"Alert '{alert.title}' acknowledged",
            actor=principal.name,
            subject=f"alert:{alert.id}",
        )
    return alert


@router.get("/events", response_model=Page[EventOut])
async def list_events(
    type: str | None = Query(default=None, max_length=48),  # noqa: A002
    severity: Literal["info", "warning", "critical"] | None = None,
    page: PageParams = Depends(pagination),
    _: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Event)
    if type:
        q = q.where(Event.type.like(f"{type.replace('%', '').replace('_', '')}%"))
    if severity:
        q = q.where(Event.severity == severity)
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                q.order_by(Event.ts.desc(), Event.id.desc()).limit(page.limit).offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page(items=rows, total=total, limit=page.limit, offset=page.offset)
