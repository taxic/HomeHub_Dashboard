"""Backup *status tracking* only. This module never reads backup destinations, runs backups,
or deletes anything. "Verified" is reachable solely through a recorded successful restore test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import BackupJob, BackupReport
from app.schemas.backup import (
    BackupJobCreate,
    BackupJobOut,
    BackupJobPatch,
    BackupReportIn,
)
from app.services.events import record_event

PROBLEM_STATES = {"never_run", "failed", "overdue", "restore_failed"}
MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_PAST = timedelta(days=366)


def compute_state(job: BackupJob, now: datetime | None = None) -> tuple[str, str | None]:
    now = now or datetime.now(UTC)
    if not job.enabled:
        return "disabled", "Monitoring disabled"
    if job.last_attempt_at is None and job.last_success_at is None:
        return "never_run", "No backup has been reported yet"
    if job.last_attempt_status == "failed" and (
        job.last_success_at is None or job.last_attempt_at > job.last_success_at
    ):
        return "failed", job.last_message or "Last backup attempt failed"
    if job.last_success_at is None:
        return "never_run", "No successful backup has been reported"
    age = now - job.last_success_at
    if age > timedelta(hours=job.max_age_hours):
        hours = int(age.total_seconds() // 3600)
        return "overdue", f"Last success {hours}h ago (limit {job.max_age_hours}h)"
    if job.last_restore_test_ok is False and (
        job.last_restore_test_at
        and job.last_restore_test_at >= job.last_success_at - timedelta(days=1)
    ):
        return "restore_failed", "Most recent restore test failed"
    if job.last_restore_test_success_at and now - job.last_restore_test_success_at <= timedelta(
        days=job.verification_max_age_days
    ):
        return "restore_verified", "A restore test succeeded recently"
    return "reported_success", "Success was reported by the backup script; no restore test recorded"


def to_out(job: BackupJob, now: datetime | None = None) -> BackupJobOut:
    now = now or datetime.now(UTC)
    out = BackupJobOut.model_validate(job)
    out.state, out.state_reason = compute_state(job, now)  # type: ignore[assignment]
    if job.last_success_at:
        out.age_hours = round((now - job.last_success_at).total_seconds() / 3600, 1)
    return out


async def _unique(session: AsyncSession, name: str, exclude: int | None = None) -> None:
    q = select(BackupJob.id).where(func.lower(BackupJob.name) == name.lower())
    if exclude is not None:
        q = q.where(BackupJob.id != exclude)
    if (await session.execute(q)).first():
        raise ConflictError(f"A backup job named '{name}' already exists", code="duplicate_name")


async def create_job(session: AsyncSession, body: BackupJobCreate, actor: str) -> BackupJob:
    await _unique(session, body.name)
    job = BackupJob(**body.model_dump())
    session.add(job)
    await session.flush()
    record_event(
        session,
        "backup.job_created",
        f"Backup job '{job.name}' created",
        actor=actor,
        subject=f"backup:{job.id}",
    )
    return job


async def get_or_404(session: AsyncSession, job_id: int) -> BackupJob:
    job = await session.get(BackupJob, job_id)
    if job is None:
        raise NotFoundError("Backup job not found")
    return job


async def update_job(
    session: AsyncSession, job: BackupJob, body: BackupJobPatch, actor: str
) -> BackupJob:
    changes = body.model_dump(exclude_unset=True)
    for k in ("name", "max_age_hours", "verification_max_age_days", "enabled"):
        if k in changes and changes[k] is None:
            raise AppError(f"{k} cannot be null", status_code=422, code="validation_error")
    if "name" in changes:
        await _unique(session, changes["name"], job.id)
    for k, v in changes.items():
        setattr(job, k, v)
    record_event(
        session,
        "backup.job_updated",
        f"Backup job '{job.name}' updated",
        actor=actor,
        subject=f"backup:{job.id}",
    )
    return job


async def record_report(
    session: AsyncSession, job: BackupJob, body: BackupReportIn, source: str
) -> BackupReport:
    now = datetime.now(UTC)
    finished = body.finished_at or now
    if finished.tzinfo is None:
        raise AppError(
            "finished_at must include a timezone", status_code=422, code="validation_error"
        )
    finished = finished.astimezone(UTC)
    if finished - now > MAX_FUTURE_SKEW:
        raise AppError("finished_at is in the future", status_code=422, code="validation_error")
    if now - finished > MAX_PAST:
        raise AppError("finished_at is too old", status_code=422, code="validation_error")

    report = BackupReport(
        job_id=job.id,
        kind=body.kind,
        status=body.status,
        finished_at=finished,
        message=body.message,
        size_bytes=body.size_bytes,
        source=source[:64],
    )
    session.add(report)
    if body.kind == "backup":
        # Out-of-order reports are stored but must not roll the job's state backwards.
        if job.last_attempt_at is None or finished >= job.last_attempt_at:
            job.last_attempt_at = finished
            job.last_attempt_status = body.status
            job.last_message = body.message
        if body.status == "success" and (
            job.last_success_at is None or finished > job.last_success_at
        ):
            job.last_success_at = finished
    else:
        if job.last_restore_test_at is None or finished >= job.last_restore_test_at:
            job.last_restore_test_at = finished
            job.last_restore_test_ok = body.status == "success"
        if body.status == "success" and (
            job.last_restore_test_success_at is None or finished > job.last_restore_test_success_at
        ):
            job.last_restore_test_success_at = finished
    sev = "info" if body.status == "success" else "warning"
    record_event(
        session,
        f"backup.{body.kind}_{body.status}",
        f"Backup '{job.name}': {body.kind.replace('_', ' ')} {body.status}"
        + (f" - {body.message}" if body.message else ""),
        severity=sev,
        actor=source,
        subject=f"backup:{job.id}",
    )
    return report
