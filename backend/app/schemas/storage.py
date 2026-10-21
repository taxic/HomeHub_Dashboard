from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel

_MARKER_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def validate_path(v: str) -> str:
    # Lexical validation only; allowed roots are enforced by the service layer.
    if "\x00" in v or ".." in v.split("/") or not v.startswith("/"):
        raise ValueError("Path must be absolute and must not contain '..'")
    return v.rstrip("/") or "/"


class VolumeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=300)
    kind: Literal["data", "external"] = "external"
    required: bool = True
    require_mountpoint: bool = True
    marker_file: str | None = Field(default=None, max_length=100)
    enabled: bool = True

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        return validate_path(v)

    @field_validator("marker_file")
    @classmethod
    def _marker(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not _MARKER_RE.match(v) or v in (".", ".."):
            raise ValueError("Marker must be a plain file name (no slashes)")
        return v


class VolumePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    path: str | None = Field(default=None, min_length=1, max_length=300)
    kind: Literal["data", "external"] | None = None
    required: bool | None = None
    require_mountpoint: bool | None = None
    marker_file: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None

    @field_validator("path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        return validate_path(v) if v is not None else None

    @field_validator("marker_file")
    @classmethod
    def _marker(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not _MARKER_RE.match(v) or v in (".", ".."):
            raise ValueError("Marker must be a plain file name (no slashes)")
        return v


class VolumeOut(ORMModel):
    id: int
    name: str
    path: str
    kind: str
    required: bool
    require_mountpoint: bool
    marker_file: str | None
    enabled: bool
    created_at: datetime
