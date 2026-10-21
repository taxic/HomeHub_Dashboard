from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.context import AppContext
from app.core.errors import ForbiddenError, UnauthorizedError
from app.models import User
from app.services import auth_service

PAGE_MAX = 200


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_session(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[AsyncSession]:
    async with ctx.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def client_ip(request: Request, ctx: AppContext) -> str:
    """Peer address; honours X-Forwarded-For only when the peer is a trusted proxy."""
    peer = request.client.host if request.client else "unknown"
    nets = []
    for entry in ctx.settings.trusted_proxies:
        try:
            nets.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue

    def trusted(addr: str) -> bool:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        return any(ip in n for n in nets)

    if not trusted(peer):
        return peer
    xff = request.headers.get("x-forwarded-for", "")
    for hop in reversed([h.strip() for h in xff.split(",") if h.strip()]):
        if not trusted(hop):
            return hop
    return peer


@dataclass
class Principal:
    kind: str  # "user" | "apikey"
    name: str
    user: User | None = None
    family: str | None = None
    scopes: tuple[str, ...] = ()


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


async def current_user(
    authorization: str | None = Header(default=None),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    token = _bearer(authorization)
    if not token:
        raise UnauthorizedError("Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = security.decode_access_token(ctx.secret_key, token)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError(
            "Invalid or expired token", code="invalid_token", headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    family = payload.get("sid")
    if not family or not await auth_service.family_active(session, family):
        raise UnauthorizedError("Session has been revoked", code="session_revoked")
    user = await session.get(User, int(payload["sub"]))
    if user is None:
        raise UnauthorizedError("Unknown user", code="invalid_token")
    return Principal("user", user.username, user=user, family=family, scopes=("*",))


def require_scope(scope: str):
    """Accept an interactive user session or an API key carrying ``scope``."""

    async def dep(
        authorization: str | None = Header(default=None),
        ctx: AppContext = Depends(get_ctx),
        session: AsyncSession = Depends(get_session),
    ) -> Principal:
        token = _bearer(authorization)
        if token and token.startswith("hlcc_"):
            key = await auth_service.find_api_key(session, token)
            if key is None:
                raise UnauthorizedError("Invalid API key", code="invalid_token")
            if scope not in key.scopes.split(","):
                raise ForbiddenError("API key lacks the required scope", code="insufficient_scope")
            return Principal("apikey", f"apikey:{key.name}", scopes=tuple(key.scopes.split(",")))
        return await current_user(authorization, ctx, session)

    return dep


@dataclass
class PageParams:
    limit: int
    offset: int


def pagination(
    limit: int = Query(default=50, ge=1, le=PAGE_MAX), offset: int = Query(default=0, ge=0)
) -> PageParams:
    return PageParams(limit, offset)
