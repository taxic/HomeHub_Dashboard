from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event


def record_event(
    session: AsyncSession,
    type_: str,
    message: str,
    *,
    severity: str = "info",
    actor: str | None = None,
    subject: str | None = None,
    data: dict | None = None,
) -> Event:
    event = Event(
        type=type_,
        message=message[:2000],
        severity=severity,
        actor=actor,
        subject=subject,
        data=data,
    )
    session.add(event)
    return event
