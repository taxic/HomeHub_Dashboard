from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel

BackupState = Literal[
    "never_run",
    "failed",
    "overdue",
    "restore_failed",
    "reported_success",
    "restore_verified",
    "disabled",
]


class BackupJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    schedule_text: str | None = Field(default=None, max_length=120)
    report_path: str | None = Field(default=None, max_length=300)
    max_age_hours: int = Field(default=36, ge=1, le=24 * 365)
    verification_max_age_days: int = Field(default=90, ge=1, le=3650)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class BackupJobPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    schedule_text: str | None = Field(default=None, max_length=120)
    report_path: str | None = Field(default=None, max_length=300)
    max_age_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    verification_max_age_days: int | None = Field(default=None, ge=1, le=3650)
    enabled: bool | None = None


class BackupReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["backup", "restore_test"] = "backup"
    status: Literal["success", "failed"]
    finished_at: datetime | None = None
    message: str | None = Field(default=None, max_length=500)
    size_bytes: int | None = Field(default=None, ge=0)


class BackupJobOut(ORMModel):
    id: int
    name: str
    description: str | None
    schedule_text: str | None
    report_path: str | None
    max_age_hours: int
    verification_max_age_days: int
    enabled: bool
    created_at: datetime
    last_attempt_at: datetime | None
    last_attempt_status: str | None
    last_success_at: datetime | None
    last_message: str | None
    last_restore_test_at: datetime | None
    last_restore_test_ok: bool | None
    last_restore_test_success_at: datetime | None
    state: BackupState = "never_run"
    state_reason: str | None = None
    age_hours: float | None = None


class BackupReportOut(ORMModel):
    id: int
    job_id: int
    received_at: datetime
    kind: str
    status: str
    finished_at: datetime
    message: str | None
    size_bytes: int | None
    source: str | None
