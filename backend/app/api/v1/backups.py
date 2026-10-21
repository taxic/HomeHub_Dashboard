from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, current_user, get_session, require_scope
from app.models import BackupJob, BackupReport
from app.schemas.backup import (
    BackupJobCreate,
    BackupJobOut,
    BackupJobPatch,
    BackupReportIn,
    BackupReportOut,
)
from app.schemas.common import Message
from app.services import backup_service
from app.services.events import record_event

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get("", response_model=list[BackupJobOut])
async def list_backups(
    _: Principal = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    jobs = (await session.execute(select(BackupJob).order_by(BackupJob.name))).scalars().all()
    return [backup_service.to_out(j) for j in jobs]


@router.post("", response_model=BackupJobOut, status_code=201)
async def create_backup(
    body: BackupJobCreate,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    return backup_service.to_out(await backup_service.create_job(session, body, principal.name))


@router.get("/{job_id}", response_model=BackupJobOut)
async def get_backup(
    job_id: int, _: Principal = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    return backup_service.to_out(await backup_service.get_or_404(session, job_id))


@router.patch("/{job_id}", response_model=BackupJobOut)
async def patch_backup(
    job_id: int,
    body: BackupJobPatch,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    job = await backup_service.get_or_404(session, job_id)
    await backup_service.update_job(session, job, body, principal.name)
    return backup_service.to_out(job)


@router.delete("/{job_id}", response_model=Message)
async def delete_backup(
    job_id: int,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    job = await backup_service.get_or_404(session, job_id)
    record_event(
        session,
        "backup.job_deleted",
        f"Backup job '{job.name}' deleted (status record only)",
        actor=principal.name,
        subject=f"backup:{job.id}",
    )
    await session.delete(job)
    return Message(message="Backup job removed from monitoring; no backup data was touched")


@router.post("/{job_id}/report", response_model=BackupJobOut)
async def report_backup(
    job_id: int,
    body: BackupReportIn,
    principal: Principal = Depends(require_scope("backup:report")),
    session: AsyncSession = Depends(get_session),
):
    """Called by a trusted local script (API key with ``backup:report``) or an admin session."""
    job = await backup_service.get_or_404(session, job_id)
    await backup_service.record_report(session, job, body, principal.name)
    return backup_service.to_out(job)


@router.get("/{job_id}/reports", response_model=list[BackupReportOut])
async def list_reports(
    job_id: int, _: Principal = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    await backup_service.get_or_404(session, job_id)
    q = (
        select(BackupReport)
        .where(BackupReport.job_id == job_id)
        .order_by(BackupReport.id.desc())
        .limit(50)
    )
    return list((await session.execute(q)).scalars())
