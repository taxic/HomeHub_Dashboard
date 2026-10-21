from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PageParams, Principal, current_user, get_ctx, get_session, pagination
from app.core.context import AppContext
from app.core.errors import AppError, UnavailableError
from app.models import Service
from app.schemas.common import Message, Page
from app.schemas.service import ServiceCreate, ServicePatch, ServiceView
from app.services import service_service
from app.services.events import record_event

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=Page[ServiceView])
async def list_services(
    category: str | None = Query(default=None, max_length=40),
    page: PageParams = Depends(pagination),
    _: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    base = select(Service)
    if category:
        base = base.where(Service.category == category)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(Service.category, Service.name).limit(page.limit).offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page(
        items=[service_service.build_view(s, ctx.monitor) for s in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=ServiceView, status_code=201)
async def create_service(
    body: ServiceCreate,
    principal: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    svc = await service_service.create_service(session, ctx.settings, body, principal.name)
    return service_service.build_view(svc, ctx.monitor)


@router.get("/{service_id}", response_model=ServiceView)
async def get_service(
    service_id: int,
    _: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    return service_service.build_view(
        await service_service.get_or_404(session, service_id), ctx.monitor
    )


@router.patch("/{service_id}", response_model=ServiceView)
async def patch_service(
    service_id: int,
    body: ServicePatch,
    principal: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    svc = await service_service.get_or_404(session, service_id)
    await service_service.update_service(session, ctx.settings, svc, body, principal.name)
    return service_service.build_view(svc, ctx.monitor)


@router.delete("/{service_id}", response_model=Message)
async def delete_service(
    service_id: int,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = await service_service.get_or_404(session, service_id)
    record_event(
        session,
        "service.deleted",
        f"Service '{svc.name}' deleted",
        actor=principal.name,
        subject=f"service:{svc.id}",
    )
    await session.delete(svc)
    return Message(message="Service deleted")


@router.post("/{service_id}/check", response_model=ServiceView)
async def check_service_now(
    service_id: int,
    _: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    svc = await service_service.get_or_404(session, service_id)
    if not svc.url:
        raise AppError("This service has no health-check URL", status_code=400, code="no_url")
    if ctx.monitor is None:
        raise UnavailableError("Monitoring is not running", code="monitor_disabled")
    await session.commit()  # release before the check opens its own sessions
    ran = await ctx.monitor.check_service(service_id, manual=True)
    if not ran:
        raise AppError("A check is already in progress", status_code=409, code="check_in_progress")
    await session.refresh(svc)
    return service_service.build_view(svc, ctx.monitor)
