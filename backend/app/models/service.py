from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UTCDateTime, utcnow


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="other")
    icon: Mapped[str | None] = mapped_column(String(40))
    container_name: Mapped[str | None] = mapped_column(String(128), index=True)
    url: Mapped[str | None] = mapped_column(String(500))
    expected_status: Mapped[str] = mapped_column(String(64), default="200-399")
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # container control (explicit opt-in)
    allow_control: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_state: Mapped[str] = mapped_column(String(16), default="running")

    # latest check result
    health_status: Mapped[str] = mapped_column(String(16), default="unknown")
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_response_ms: Mapped[float | None] = mapped_column(Float)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(300))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
