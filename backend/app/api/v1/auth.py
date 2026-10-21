from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__  # noqa: F401
from app.api.deps import Principal, client_ip, current_user, get_ctx, get_session
from app.core.context import AppContext
from app.core.errors import AppError, NotFoundError, UnauthorizedError
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    AuthStatus,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    SessionOut,
    SetupRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.common import Message
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE = "hlcc_refresh"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "hlcc"


def _set_cookie(response: Response, ctx: AppContext, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=ctx.settings.refresh_token_days * 86400,
        httponly=True,
        secure=ctx.settings.cookie_secure,
        samesite="strict",
        path="/api/v1/auth",
    )


def _token_response(tokens: auth_service.IssuedTokens, client: str) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token if client == "mobile" else None,
        username=tokens.username,
    )


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    ctx: AppContext = Depends(get_ctx), session: AsyncSession = Depends(get_session)
) -> AuthStatus:
    return AuthStatus(
        setup_required=await auth_service.user_count(session) == 0,
        setup_token_required=bool(ctx.settings.setup_token),
    )


@router.post("/setup", response_model=UserOut, status_code=201)
async def setup(
    body: SetupRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    ip = client_ip(request, ctx)
    wait = ctx.ip_limiter.retry_after(f"setup:{ip}")
    if wait:
        raise AppError(
            "Too many attempts",
            status_code=429,
            code="rate_limited",
            headers={"Retry-After": str(wait)},
        )
    try:
        return await auth_service.create_initial_user(
            session, ctx.settings, body.username, body.password, body.setup_token
        )
    except AppError as exc:
        if exc.code == "invalid_setup_token":
            ctx.ip_limiter.record_failure(f"setup:{ip}")
        raise


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    ip = client_ip(request, ctx)
    acct_key = f"{body.username.lower()}|{ip}"
    ip_key = f"ip:{ip}"
    wait = max(ctx.account_limiter.retry_after(acct_key), ctx.ip_limiter.retry_after(ip_key))
    if wait:
        raise AppError(
            "Too many failed login attempts. Try again later.",
            status_code=429,
            code="rate_limited",
            headers={"Retry-After": str(wait)},
        )
    try:
        tokens = await auth_service.login(
            session,
            ctx.settings,
            ctx.secret_key,
            body.username,
            body.password,
            body.client,
            request.headers.get("user-agent"),
        )
    except UnauthorizedError:
        ctx.account_limiter.record_failure(acct_key)
        ctx.ip_limiter.record_failure(ip_key)
        raise
    ctx.account_limiter.reset(acct_key)
    if body.client == "web":
        _set_cookie(response, ctx, tokens.refresh_token)
    return _token_response(tokens, body.client)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    cookie = request.cookies.get(COOKIE)
    if body and body.refresh_token:
        raw, client = body.refresh_token, "mobile"
    elif cookie:
        # Cookie-authenticated request: demand a custom header a cross-site form cannot send.
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise AppError("Missing CSRF header", status_code=403, code="csrf_failed")
        raw, client = cookie, "web"
    else:
        raise UnauthorizedError("No refresh token supplied", code="invalid_refresh_token")
    try:
        tokens = await auth_service.refresh(
            session, ctx.settings, ctx.secret_key, raw, request.headers.get("user-agent")
        )
    except UnauthorizedError as exc:
        if client == "web" and exc.code == "invalid_refresh_token":
            response.delete_cookie(COOKIE, path="/api/v1/auth")
        raise
    if client == "web":
        _set_cookie(response, ctx, tokens.refresh_token)
    return _token_response(tokens, client)


@router.post("/logout", response_model=Message)
async def logout(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    raw = (body.refresh_token if body else None) or request.cookies.get(COOKIE)
    if raw and not (body and body.refresh_token) and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise AppError("Missing CSRF header", status_code=403, code="csrf_failed")
    await auth_service.logout_by_token(session, raw)
    response.delete_cookie(COOKIE, path="/api/v1/auth")
    return Message(message="Signed out")


@router.get("/me", response_model=UserOut)
async def me(principal: Principal = Depends(current_user)):
    return principal.user


@router.get("/sessions", response_model=list[SessionOut])
async def sessions(
    principal: Principal = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    rows = await auth_service.list_sessions(session, principal.user.id)
    return [
        SessionOut(
            id=r.id,
            client=r.client,
            user_agent=r.user_agent,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            expires_at=r.expires_at,
            current=r.family == principal.family,
        )
        for r in rows
    ]


@router.delete("/sessions/{session_id}", response_model=Message)
async def revoke_session(
    session_id: int,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await auth_service.revoke_session(session, principal.user.id, session_id):
        raise NotFoundError("Session not found")
    return Message(message="Session revoked")


@router.post("/change-password", response_model=Message)
async def change_password(
    body: ChangePasswordRequest,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    await auth_service.change_password(
        session, principal.user, body.current_password, body.new_password, principal.family
    )
    return Message(message="Password changed; other sessions were signed out")


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    _: Principal = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    from sqlalchemy import select

    from app.models import ApiKey

    return list((await session.execute(select(ApiKey).order_by(ApiKey.id))).scalars())


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    key, full = await auth_service.create_api_key(session, body.name, body.scopes, principal.name)
    return ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(), key=full)


@router.delete("/api-keys/{key_id}", response_model=Message)
async def revoke_api_key(
    key_id: int,
    principal: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.database.base import utcnow
    from app.models import ApiKey
    from app.services.events import record_event

    key = await session.get(ApiKey, key_id)
    if key is None:
        raise NotFoundError("API key not found")
    key.revoked_at = key.revoked_at or utcnow()
    record_event(
        session, "auth.api_key_revoked", f"API key '{key.name}' revoked", actor=principal.name
    )
    return Message(message="API key revoked")
