from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import AppSetting
from app.schemas.settings import AppSettings, AppSettingsPatch

KEY = "app"


async def load_settings(session: AsyncSession) -> AppSettings:
    row = await session.get(AppSetting, KEY)
    if row is None:
        return AppSettings()
    try:
        return AppSettings.model_validate(row.value)
    except ValidationError:
        # A stored value that no longer validates (e.g. after a downgrade) must not brick the app.
        return AppSettings()


async def update_settings(session: AsyncSession, patch: AppSettingsPatch) -> AppSettings:
    current = await load_settings(session)
    merged = {**current.model_dump(), **patch.model_dump(exclude_unset=True, exclude_none=True)}
    try:
        new = AppSettings.model_validate(merged)
    except ValidationError as exc:
        details = [
            {
                "field": ".".join(str(p) for p in e["loc"]),
                "message": e["msg"].removeprefix("Value error, "),
            }
            for e in exc.errors()
        ]
        raise AppError(
            "Invalid settings", status_code=422, code="validation_error", details=details
        ) from exc
    row = await session.get(AppSetting, KEY)
    if row is None:
        session.add(AppSetting(key=KEY, value=new.model_dump()))
    else:
        row.value = new.model_dump()
    return new
