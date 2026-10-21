from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UTCDateTime, utcnow


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    schedule_text: Mapped[str | None] = mapped_column(String(120))  # informational only
    report_path: Mapped[str | None] = mapped_column(String(300))  # informational label only
    max_age_hours: Mapped[int] = mapped_column(Integer, default=36)
    verification_max_age_days: Mapped[int] = mapped_column(Integer, default=90)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_attempt_status: Mapped[str | None] = mapped_column(String(16))  # success | failed
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_message: Mapped[str | None] = mapped_column(String(500))
    last_restore_test_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_restore_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_restore_test_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class BackupReport(Base):
    __tablename__ = "backup_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("backup_jobs.id", ondelete="CASCADE"), index=True
    )
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(16), default="backup")  # backup | restore_test
    status: Mapped[str] = mapped_column(String(16))  # success | failed
    finished_at: Mapped[datetime] = mapped_column(UTCDateTime)
    message: Mapped[str | None] = mapped_column(String(500))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str | None] = mapped_column(String(64))
