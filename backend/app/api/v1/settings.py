from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.deps import Principal, current_user, get_ctx, get_session
from app.core.context import AppContext
from app.schemas.common import Message
from app.schemas.settings import AppSettingsPatch, SettingsResponse
from app.services import settings_service
from app.services.events import record_event

router = APIRouter(prefix="/settings", tags=["settings"])


def _response(ctx: AppContext) -> SettingsResponse:
    return SettingsResponse(
        settings=ctx.runtime,
        telegram_configured=bool(ctx.settings.telegram_bot_token and ctx.settings.telegram_chat_id),
        docker_control_enabled=ctx.settings.docker_control_enabled,
        version=__version__,
        public_url=ctx.settings.public_url,
    )


@router.get("", response_model=SettingsResponse)
async def get_settings(
    _: Principal = Depends(current_user), ctx: AppContext = Depends(get_ctx)
) -> SettingsResponse:
    return _response(ctx)


@router.patch("", response_model=SettingsResponse)
async def patch_settings(
    body: AppSettingsPatch,
    principal: Principal = Depends(current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> SettingsResponse:
    new = await settings_service.update_settings(session, body)
    record_event(
        session,
        "settings.updated",
        "Settings updated",
        actor=principal.name,
        data={"fields": sorted(body.model_dump(exclude_unset=True, exclude_none=True))},
    )
    ctx.runtime = new
    return _response(ctx)


@router.post("/test-notification", response_model=Message)
async def test_notification(
    principal: Principal = Depends(current_user), ctx: AppContext = Depends(get_ctx)
) -> Message:
    """Send a test message through the configured notifier (never reveals credentials)."""
    from app.core.errors import AppError
    from app.notifications.base import Notification

    notifier = ctx.extras.get("telegram")
    if notifier is None or not notifier.configured():
        raise AppError(
            "Telegram is not configured on the server (set HOMELAB_TELEGRAM_BOT_TOKEN and "
            "HOMELAB_TELEGRAM_CHAT_ID)",
            status_code=400,
            code="notifier_not_configured",
        )
    try:
        await notifier.send(
            Notification(
                "test",
                "info",
                "Test notification",
                f"Sent by {principal.name} from HomeLab Command Centre.",
            )
        )
    except RuntimeError as exc:
        raise AppError(f"Delivery failed: {exc}", status_code=502, code="delivery_failed") from exc
    return Message(message="Test notification sent")
