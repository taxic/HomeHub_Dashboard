from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, ForbiddenError, UnauthorizedError
from app.database.base import utcnow
from app.models import ApiKey, RefreshToken, User
from app.services.events import record_event

REFRESH_REUSE_GRACE_SECONDS = 15


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    username: str


async def user_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(User))).scalar_one()


async def create_initial_user(
    session: AsyncSession, settings: Settings, username: str, password: str, setup_token: str | None
) -> User:
    if await user_count(session) > 0:
        raise ConflictError("Setup has already been completed", code="setup_complete")
    if settings.setup_token and not (
        setup_token and security.constant_time_equals(setup_token, settings.setup_token)
    ):
        raise ForbiddenError("Invalid setup token", code="invalid_setup_token")
    problem = security.validate_password_strength(password)
    if problem:
        raise AppError(problem, status_code=422, code="weak_password")
    user = User(username=username, password_hash=security.hash_password(password))
    session.add(user)
    await session.flush()
    record_event(session, "auth.setup", f"Administrator '{username}' created", actor=username)
    return user


async def _issue(
    session: AsyncSession,
    settings: Settings,
    secret: str,
    user: User,
    *,
    family: str,
    client: str,
    user_agent: str | None,
) -> IssuedTokens:
    raw = security.new_opaque_token()
    row = RefreshToken(
        user_id=user.id,
        family=family,
        token_hash=security.hash_token(raw),
        client=client,
        user_agent=(user_agent or "")[:200] or None,
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
    )
    session.add(row)
    await session.flush()
    access = security.create_access_token(secret, user.id, settings.access_token_minutes, family)
    return IssuedTokens(access, raw, settings.access_token_minutes * 60, user.username)


async def login(
    session: AsyncSession,
    settings: Settings,
    secret: str,
    username: str,
    password: str,
    client: str,
    user_agent: str | None,
) -> IssuedTokens:
    user = (
        await session.execute(select(User).where(func.lower(User.username) == username.lower()))
    ).scalar_one_or_none()
    ok = security.verify_password(password, user.password_hash if user else None)
    if not ok or user is None:
        record_event(session, "auth.login_failed", "Failed login attempt", severity="warning")
        await session.commit()
        raise UnauthorizedError("Invalid username or password", code="invalid_credentials")
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    user.last_login_at = utcnow()
    record_event(
        session, "auth.login", f"'{user.username}' signed in ({client})", actor=user.username
    )
    return await _issue(
        session,
        settings,
        secret,
        user,
        family=secrets.token_hex(8),
        client=client,
        user_agent=user_agent,
    )


async def refresh(
    session: AsyncSession, settings: Settings, secret: str, raw_token: str, user_agent: str | None
) -> IssuedTokens:
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(raw_token))
        )
    ).scalar_one_or_none()
    now = utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise UnauthorizedError("Invalid refresh token", code="invalid_refresh_token")
    if row.rotated_at is not None:
        if (now - row.rotated_at).total_seconds() <= REFRESH_REUSE_GRACE_SECONDS:
            # Two concurrent refreshes (e.g. two browser tabs); do not punish, ask to retry.
            raise UnauthorizedError("Refresh token already used; retry", code="refresh_conflict")
        await revoke_family(session, row.family)
        record_event(
            session,
            "auth.refresh_reuse",
            "Refresh token reuse detected; session revoked",
            severity="warning",
        )
        await session.commit()
        raise UnauthorizedError("Invalid refresh token", code="invalid_refresh_token")
    user = await session.get(User, row.user_id)
    if user is None:
        raise UnauthorizedError("Invalid refresh token", code="invalid_refresh_token")
    row.rotated_at = now
    row.last_used_at = now
    return await _issue(
        session,
        settings,
        secret,
        user,
        family=row.family,
        client=row.client,
        user_agent=user_agent or row.user_agent,
    )


async def revoke_family(session: AsyncSession, family: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family == family, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def logout_by_token(session: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(raw_token))
        )
    ).scalar_one_or_none()
    if row:
        await revoke_family(session, row.family)


async def family_active(session: AsyncSession, family: str) -> bool:
    q = (
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.family == family,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
    )
    return (await session.execute(q)).scalar_one() > 0


async def list_sessions(session: AsyncSession, user_id: int) -> list[RefreshToken]:
    """Latest live token row for each active family."""
    rows = (
        await session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.rotated_at.is_(None),
                RefreshToken.expires_at > utcnow(),
            )
            .order_by(RefreshToken.created_at.desc())
        )
    ).scalars()
    return list(rows)


async def revoke_session(session: AsyncSession, user_id: int, session_id: int) -> bool:
    row = await session.get(RefreshToken, session_id)
    if row is None or row.user_id != user_id:
        return False
    await revoke_family(session, row.family)
    return True


async def change_password(
    session: AsyncSession, user: User, current: str, new: str, keep_family: str | None
) -> None:
    if not security.verify_password(current, user.password_hash):
        raise AppError("Current password is incorrect", status_code=400, code="invalid_credentials")
    problem = security.validate_password_strength(new)
    if problem:
        raise AppError(problem, status_code=422, code="weak_password")
    user.password_hash = security.hash_password(new)
    # Sign out every other session.
    others = (
        await session.execute(
            select(RefreshToken.family).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        )
    ).scalars()
    for fam in set(others):
        if fam != keep_family:
            await revoke_family(session, fam)
    record_event(session, "auth.password_changed", "Password changed", actor=user.username)


async def create_api_key(
    session: AsyncSession, name: str, scopes: list[str], actor: str
) -> tuple[ApiKey, str]:
    existing = (
        await session.execute(select(ApiKey).where(ApiKey.name == name))
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("An API key with that name already exists")
    full, prefix = security.new_api_key()
    key = ApiKey(
        name=name, prefix=prefix, key_hash=security.hash_token(full), scopes=",".join(scopes)
    )
    session.add(key)
    await session.flush()
    record_event(session, "auth.api_key_created", f"API key '{name}' created", actor=actor)
    return key, full


async def find_api_key(session: AsyncSession, raw: str) -> ApiKey | None:
    key = (
        await session.execute(select(ApiKey).where(ApiKey.key_hash == security.hash_token(raw)))
    ).scalar_one_or_none()
    if key is None or key.revoked_at is not None:
        return None
    key.last_used_at = utcnow()
    return key
