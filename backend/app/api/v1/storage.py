from __future__ import annotations

import posixpath

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, current_user, get_ctx, get_session
from app.core.context import AppContext
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import StorageVolume
from app.schemas.common import Message
from app.schemas.metrics import StorageResponse
from app.schemas.storage import VolumeCreate, VolumeOut, VolumePatch
from app.services.events import record_event

router = APIRouter(prefix="/storage", tags=["storage"])


def _check_allowed(ctx: AppContext, path: str) -> None:
    """Monitored paths must sit under an operator-approved root ('/' only matches itself)."""
    norm = posixpath.normpath(path)
    for root in ctx.settings.storage_allowed_roots:
        root = posixpath.normpath(root)
        if root == "/":
            if norm == "/":
                return
        elif norm == root or norm.startswith(root + "/"):
            return
    raise AppError(
        "Path is outside the directories this server is configured to monitor "
        "(HOMELAB_STORAGE_ALLOWED_ROOTS)",
        status_code=422,
        code="path_not_allowed",
        details=[{"field": "path", "message": "Path not under an allowed root"}],
    )


@router.get("", response_model=StorageResponse)
async def storage(_: Principal = Depends(current_user), ctx: AppContext = Depends(get_ctx)):
    mon = ctx.monitor
    if mon is None:
        return StorageResponse(root=None, volumes=[], disk_io=None, sampled_at=None)
    return StorageResponse(
        root=mon.root_volume,
        volumes=mon.volumes,
        disk_io=mon.host.disk_io if mon.host else None,
        sampled_at=mon.host.sampled_at if mon.host else None,
    )


@router.get("/volumes", response_model=list[VolumeOut])
async def list_volumes(
    _: Principal = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    return list(
        (await session.execute(select(StorageVolume).order_by(StorageVolume.name))).scalars()
    )


async def _refresh(ctx: AppContext) -> None:
    if ctx.monitor:
        await ctx.monitor.refresh_volumes()


@router.post("/volumes", response_model=VolumeOut, status_code=201)
async def create_volume(
    body: VolumeCreate,
    principal: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    _check_allowed(ctx, body.path)
    dup = (
        await session.execute(
            select(StorageVolume.id).where(func.lower(StorageVolume.name) == body.name.lower())
        )
    ).first()
    if dup:
        raise ConflictError("A volume with that name already exists", code="duplicate_name")
    vol = StorageVolume(**body.model_dump())
    session.add(vol)
    await session.flush()
    record_event(
        session,
        "storage.volume_created",
        f"Monitored volume '{vol.name}' added",
        actor=principal.name,
        subject=f"volume:{vol.id}",
    )
    await session.commit()
    await _refresh(ctx)
    return vol


@router.patch("/volumes/{volume_id}", response_model=VolumeOut)
async def patch_volume(
    volume_id: int,
    body: VolumePatch,
    principal: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    vol = await session.get(StorageVolume, volume_id)
    if vol is None:
        raise NotFoundError("Volume not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("path"):
        _check_allowed(ctx, changes["path"])
    for k in ("name", "path", "kind", "required", "require_mountpoint", "enabled"):
        if k in changes and changes[k] is None:
            raise AppError(f"{k} cannot be null", status_code=422, code="validation_error")
    for k, v in changes.items():
        setattr(vol, k, v)
    record_event(
        session,
        "storage.volume_updated",
        f"Monitored volume '{vol.name}' updated",
        actor=principal.name,
        subject=f"volume:{vol.id}",
    )
    await session.commit()
    await _refresh(ctx)
    return vol


@router.delete("/volumes/{volume_id}", response_model=Message)
async def delete_volume(
    volume_id: int,
    principal: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    vol = await session.get(StorageVolume, volume_id)
    if vol is None:
        raise NotFoundError("Volume not found")
    record_event(
        session,
        "storage.volume_deleted",
        f"Monitored volume '{vol.name}' removed",
        actor=principal.name,
        subject=f"volume:{vol.id}",
    )
    await session.delete(vol)
    await session.commit()
    await _refresh(ctx)
    return Message(message="Volume removed from monitoring (nothing on disk was touched)")
