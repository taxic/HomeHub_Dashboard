from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, current_user, get_ctx, get_session
from app.core.context import AppContext
from app.schemas.container import (
    ContainerActionResult,
    ContainerListResponse,
    ContainerLogs,
    ContainerOut,
)
from app.services import container_service

router = APIRouter(prefix="/containers", tags=["containers"])

# Id or name; validated and then looked up only in the server's own container snapshot.
Ref = Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", description="Container id or name")


@router.get("", response_model=ContainerListResponse)
async def list_containers(
    _: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    return await container_service.list_containers(ctx, session)


@router.get("/{container_id}", response_model=ContainerOut)
async def get_container(
    container_id: str = Ref,
    _: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    return await container_service.get_container(ctx, session, container_id)


@router.get("/{container_id}/logs", response_model=ContainerLogs)
async def container_logs(
    container_id: str = Ref,
    tail: int = Query(default=100, ge=1, le=5000),
    _: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
):
    return await container_service.get_logs(ctx, container_id, tail)


def _action_route(action: str):
    async def handler(
        container_id: str = Ref,
        principal: Principal = Depends(current_user),
        ctx: AppContext = Depends(get_ctx),
        session: AsyncSession = Depends(get_session),
    ) -> ContainerActionResult:
        return await container_service.perform_action(
            ctx, session, container_id, action, principal.name
        )

    handler.__name__ = f"container_{action}"
    return handler


for _a in container_service.ACTIONS:
    router.add_api_route(
        f"/{{container_id}}/{_a}",
        _action_route(_a),
        methods=["POST"],
        response_model=ContainerActionResult,
        summary=f"{_a.capitalize()} a permitted container",
    )
