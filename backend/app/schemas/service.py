from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel

ALLOWED_ACTIONS = ("start", "stop", "restart")
_STATUS_RE = re.compile(r"^\d{3}(-\d{3})?(,\s*\d{3}(-\d{3})?)*$")
CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

HealthStatus = Literal["unknown", "healthy", "unhealthy", "disabled"]


def validate_check_url(value: str | None) -> str | None:
    """Syntactic validation only; resolution-time SSRF checks live in monitoring.ssrf."""
    if value is None or value == "":
        return None
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not parts.hostname:
        raise ValueError("URL must include a host")
    if parts.username or parts.password:
        raise ValueError("Credentials in URLs are not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid port") from exc
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("Invalid port")
    return value


def parse_status_spec(spec: str) -> list[tuple[int, int]]:
    ranges = []
    for part in spec.replace(" ", "").split(","):
        lo, _, hi = part.partition("-")
        lo_i, hi_i = int(lo), int(hi or lo)
        if not (100 <= lo_i <= hi_i <= 599):
            raise ValueError("Status codes must be between 100 and 599 and ranges ascending")
        ranges.append((lo_i, hi_i))
    return ranges


def validate_container_name(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    if not CONTAINER_NAME_RE.match(v):
        raise ValueError("Invalid container name")
    return v


def validate_status_spec(v: str | None) -> str | None:
    if v is None:
        return None
    if not _STATUS_RE.match(v.strip()):
        raise ValueError("Use codes or ranges such as '200', '200-299,301'")
    parse_status_spec(v)
    return v.replace(" ", "")


class ServiceBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    category: str = Field(default="other", min_length=1, max_length=40)
    icon: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    container_name: str | None = Field(default=None, max_length=128)
    url: str | None = Field(default=None, max_length=500)
    expected_status: str = Field(default="200-399", max_length=64)
    verify_tls: bool = True
    interval_seconds: int = Field(default=60, ge=10, le=86400)
    timeout_seconds: float = Field(default=5.0, ge=1, le=30)
    enabled: bool = True
    allow_control: bool = False
    allowed_actions: list[Literal["start", "stop", "restart"]] = []

    @field_validator("name", "category")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return validate_check_url(v)

    @field_validator("container_name")
    @classmethod
    def _container(cls, v: str | None) -> str | None:
        return validate_container_name(v)

    @field_validator("expected_status")
    @classmethod
    def _status(cls, v: str) -> str:
        return validate_status_spec(v) or v

    @field_validator("allowed_actions")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return sorted(set(v))


class ServiceCreate(ServiceBase):
    pass


class ServicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    icon: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    container_name: str | None = Field(default=None, max_length=128)
    url: str | None = Field(default=None, max_length=500)
    expected_status: str | None = Field(default=None, max_length=64)
    verify_tls: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=10, le=86400)
    timeout_seconds: float | None = Field(default=None, ge=1, le=30)
    enabled: bool | None = None
    allow_control: bool | None = None
    allowed_actions: list[Literal["start", "stop", "restart"]] | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return validate_check_url(v)

    @field_validator("container_name")
    @classmethod
    def _container(cls, v: str | None) -> str | None:
        return validate_container_name(v)

    @field_validator("expected_status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        return validate_status_spec(v)

    @field_validator("allowed_actions")
    @classmethod
    def _dedupe(cls, v: list[str] | None) -> list[str] | None:
        return sorted(set(v)) if v is not None else None


class ServiceOut(ORMModel):
    id: int
    name: str
    description: str | None
    category: str
    icon: str | None
    container_name: str | None
    url: str | None
    expected_status: str
    verify_tls: bool
    interval_seconds: int
    timeout_seconds: float
    enabled: bool
    allow_control: bool
    allowed_actions: list[str]
    expected_state: str
    health_status: HealthStatus
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_response_ms: float | None
    last_status_code: int | None
    last_error: str | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


class ServiceView(ServiceOut):
    """Service plus live Docker state (when associated and Docker is reachable)."""

    container_state: str | None = None  # running/exited/... or None when unknown
    container_health: str | None = None
    effective_status: Literal["healthy", "degraded", "unhealthy", "unknown", "disabled"] = "unknown"
    effective_reason: str | None = None
