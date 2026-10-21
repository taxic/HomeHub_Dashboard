from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UTCDateTime, utcnow


class StorageVolume(Base):
    """A path whose capacity and mount state should be monitored (read-only)."""

    __tablename__ = "storage_volumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    path: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(16), default="external")  # root | data | external
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    require_mountpoint: Mapped[bool] = mapped_column(Boolean, default=True)
    marker_file: Mapped[str | None] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
