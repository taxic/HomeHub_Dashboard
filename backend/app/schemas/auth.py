from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

Client = Literal["web", "mobile"]


class AuthStatus(BaseModel):
    setup_required: bool
    setup_token_required: bool = False


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)
    setup_token: str | None = Field(default=None, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    client: Client = "web"


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    # Returned only to mobile clients; web clients receive an HttpOnly cookie instead.
    refresh_token: str | None = None
    username: str


class UserOut(ORMModel):
    id: int
    username: str
    created_at: datetime
    last_login_at: datetime | None = None


class SessionOut(BaseModel):
    id: int
    client: str
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    current: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scopes: list[Literal["backup:report"]] = ["backup:report"]

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ApiKeyOut(ORMModel):
    id: int
    name: str
    prefix: str
    scopes: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str  # shown exactly once
