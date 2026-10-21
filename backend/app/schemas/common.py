from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list | dict | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Message(BaseModel):
    message: str


class Timestamped(BaseModel):
    updated_at: datetime | None = None
