from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.context import AppContext
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.ratelimit import FailureLimiter
from app.database import migrate
from app.database.session import create_engine, create_session_factory
from app.services import settings_service

log = logging.getLogger("homelab")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        secret = settings.resolve_secret_key()
        await migrate.upgrade(settings.effective_database_url)
        engine = create_engine(settings.effective_database_url)
        factory = create_session_factory(engine)
        ctx = AppContext(
            settings=settings,
            secret_key=secret,
            engine=engine,
            session_factory=factory,
            account_limiter=FailureLimiter(
                settings.login_max_failures, settings.login_window_seconds
            ),
            ip_limiter=FailureLimiter(
                settings.login_max_failures * 4, settings.login_window_seconds
            ),
        )
        async with factory() as session:
            ctx.runtime = await settings_service.load_settings(session)
        app.state.ctx = ctx

        monitor = None
        if settings.monitor_enabled:
            from app.monitoring.monitor import Monitor

            monitor = Monitor(ctx)
            ctx.monitor = monitor
            await monitor.start()
        log.info(
            "started version=%s db=%s", __version__, "sqlite" if settings.is_sqlite else "other"
        )
        try:
            yield
        finally:
            if monitor:
                await monitor.stop()
            await engine.dispose()
            log.info("stopped")

    app = FastAPI(
        title="HomeLab Command Centre API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    install_error_handlers(app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        )
    app.add_middleware(RequestContextMiddleware, max_body=settings.max_request_bytes)
    app.include_router(api_router)
    return app


def get_app() -> FastAPI:  # uvicorn --factory app.main:get_app
    return create_app()
