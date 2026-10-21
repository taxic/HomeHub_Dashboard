from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, current_user, get_ctx, get_session
from app.core.context import AppContext
from app.schemas.overview import Overview
from app.services import overview_service

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=Overview)
async def overview(
    _: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> Overview:
    return await overview_service.build(ctx, session)
