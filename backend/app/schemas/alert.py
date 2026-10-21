from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import ORMModel


class AlertOut(ORMModel):
    id: int
    key: str
    type: str
    severity: Literal["warning", "critical"]
    status: Literal["open", "resolved"]
    title: str
    message: str
    subject: str | None
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: str | None


class EventOut(ORMModel):
    id: int
    ts: datetime
    type: str
    severity: Literal["info", "warning", "critical"]
    message: str
    actor: str | None
    subject: str | None


class AlertCounts(BaseModel):
    open: int
    critical: int
    warning: int
    unacknowledged: int
