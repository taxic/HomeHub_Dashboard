from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AppSettings(BaseModel):
    """User-managed settings persisted in the database. Every field has safe bounds."""

    model_config = ConfigDict(extra="forbid")

    # dashboard / intervals
    dashboard_refresh_seconds: int = Field(default=10, ge=5, le=300)
    default_theme: Literal["dark", "light", "system"] = "dark"
    host_sample_seconds: int = Field(default=10, ge=5, le=60)
    docker_refresh_seconds: int = Field(default=15, ge=5, le=120)
    metric_persist_seconds: int = Field(default=60, ge=30, le=600)

    # retention
    retention_raw_hours: int = Field(default=48, ge=6, le=168)
    retention_rollup_days: int = Field(default=30, ge=7, le=365)
    retention_events_days: int = Field(default=90, ge=7, le=730)

    # alert thresholds (percent)
    cpu_warn_percent: float = Field(default=85, ge=1, le=100)
    cpu_crit_percent: float = Field(default=95, ge=1, le=100)
    cpu_duration_minutes: int = Field(default=5, ge=1, le=120)
    mem_warn_percent: float = Field(default=85, ge=1, le=100)
    mem_crit_percent: float = Field(default=95, ge=1, le=100)
    mem_duration_minutes: int = Field(default=5, ge=1, le=120)
    storage_warn_percent: float = Field(default=85, ge=1, le=100)
    storage_crit_percent: float = Field(default=95, ge=1, le=100)
    alert_renotify_minutes: int = Field(default=240, ge=5, le=10080)
    service_failure_threshold: int = Field(default=2, ge=1, le=20)

    # notifications (credentials come from the environment, never from here)
    telegram_enabled: bool = False
    notify_min_severity: Literal["warning", "critical"] = "warning"
    notify_on_resolve: bool = True

    @model_validator(mode="after")
    def _warn_below_crit(self) -> AppSettings:
        for prefix in ("cpu", "mem", "storage"):
            warn = getattr(self, f"{prefix}_warn_percent")
            crit = getattr(self, f"{prefix}_crit_percent")
            if warn >= crit:
                raise ValueError(f"{prefix}_warn_percent must be lower than {prefix}_crit_percent")
        return self


class AppSettingsPatch(BaseModel):
    """Partial update; merged over the stored settings then validated as a whole."""

    model_config = ConfigDict(extra="forbid")

    dashboard_refresh_seconds: int | None = None
    default_theme: str | None = None
    host_sample_seconds: int | None = None
    docker_refresh_seconds: int | None = None
    metric_persist_seconds: int | None = None
    retention_raw_hours: int | None = None
    retention_rollup_days: int | None = None
    retention_events_days: int | None = None
    cpu_warn_percent: float | None = None
    cpu_crit_percent: float | None = None
    cpu_duration_minutes: int | None = None
    mem_warn_percent: float | None = None
    mem_crit_percent: float | None = None
    mem_duration_minutes: int | None = None
    storage_warn_percent: float | None = None
    storage_crit_percent: float | None = None
    alert_renotify_minutes: int | None = None
    service_failure_threshold: int | None = None
    telegram_enabled: bool | None = None
    notify_min_severity: str | None = None
    notify_on_resolve: bool | None = None


class SettingsResponse(BaseModel):
    settings: AppSettings
    telegram_configured: bool  # whether bot token + chat id exist in the environment
    docker_control_enabled: bool
    version: str
    public_url: str | None
