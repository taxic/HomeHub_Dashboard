from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ContainerState = Literal[
    "running", "exited", "paused", "restarting", "created", "dead", "removing", "unknown"
]
ContainerHealth = Literal["healthy", "unhealthy", "starting", "none"]
ContainerAction = Literal["start", "stop", "restart"]


class ContainerStats(BaseModel):
    cpu_percent: float | None = None
    memory_bytes: int | None = None
    memory_limit_bytes: int | None = None
    memory_percent: float | None = None


class ContainerOut(BaseModel):
    id: str  # full id; clients may show id[:12]
    short_id: str
    name: str
    image: str
    state: ContainerState
    status_text: str
    health: ContainerHealth
    created_at: datetime | None = None
    started_at: datetime | None = None
    restart_count: int | None = None
    stats: ContainerStats | None = None  # null when unavailable (not running / stats failed)
    service_id: int | None = None
    service_name: str | None = None
    can_control: bool = False
    allowed_actions: list[ContainerAction] = []
    protected: bool = False


class ContainerListResponse(BaseModel):
    docker_available: bool
    docker_error: str | None = None
    refreshed_at: datetime | None = None
    containers: list[ContainerOut]


class ContainerLogs(BaseModel):
    id: str
    name: str
    lines: list[str]
    truncated: bool
    tail: int


class ContainerActionResult(BaseModel):
    id: str
    name: str
    action: ContainerAction
    ok: bool
    state: ContainerState
    message: str
