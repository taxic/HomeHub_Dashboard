from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UTCDateTime, utcnow


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # At most one *open* alert per dedupe key.
        Index(
            "uq_alerts_open_key",
            "key",
            unique=True,
            sqlite_where=text("status = 'open'"),
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(160), index=True)
    type: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16))  # warning | critical
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | resolved
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(160))
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64))
    last_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info|warning|critical
    message: Mapped[str] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(64))
    subject: Mapped[str | None] = mapped_column(String(160))
    data: Mapped[dict | None] = mapped_column(JSON)
