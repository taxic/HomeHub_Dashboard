from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    auth,
    backups,
    containers,
    health,
    metrics,
    overview,
    services,
    settings,
    storage,
)

api_router = APIRouter(prefix="/api/v1")
for module in (
    health,
    auth,
    overview,
    metrics,
    containers,
    services,
    storage,
    alerts,
    backups,
    settings,
):
    api_router.include_router(module.router)
