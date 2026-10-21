from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.alert import AlertCounts, AlertOut, EventOut
from app.schemas.metrics import HostMetrics, HostStatus, VolumeStatus


class ContainerCounts(BaseModel):
    available: bool  # false => Docker unreachable; counts below are not meaningful
    running: int = 0
    stopped: int = 0
    unhealthy: int = 0
    total: int = 0
    error: str | None = None


class ServiceCounts(BaseModel):
    healthy: int = 0
    unhealthy: int = 0
    unknown: int = 0
    degraded: int = 0
    disabled: int = 0
    total: int = 0


class BackupCounts(BaseModel):
    total: int = 0
    ok: int = 0
    problem: int = 0


class Overview(BaseModel):
    status: HostStatus
    status_reason: str | None
    generated_at: datetime
    last_update: datetime | None  # last successful host sample
    stale: bool
    refresh_seconds: int
    host: HostMetrics | None
    root_volume: VolumeStatus | None
    volumes: list[VolumeStatus]
    containers: ContainerCounts
    services: ServiceCounts
    backups: BackupCounts
    alerts: AlertCounts
    recent_alerts: list[AlertOut]
    recent_events: list[EventOut]
