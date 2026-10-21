"""Container listing and *controlled* management.

Authorisation model for state changes (all must hold):
1. ``HOMELAB_DOCKER_CONTROL_ENABLED=true`` (server-wide master switch, default off);
2. the container is not in the protected list (the Command Centre's own containers);
3. a service definition references the container by name with ``allow_control=true``;
4. the requested action is in that service's ``allowed_actions``.
Clients only ever supply a container reference and one of three action names.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AppContext
from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError, UnavailableError
from app.models import Service
from app.monitoring.docker_gateway import (
    ContainerNotFoundError,
    DockerUnavailableError,
    RawContainer,
)
from app.schemas.container import (
    ContainerActionResult,
    ContainerListResponse,
    ContainerLogs,
    ContainerOut,
    ContainerStats,
)
from app.services.events import record_event

log = logging.getLogger(__name__)
ACTIONS = ("start", "stop", "restart")
ACTION_TIMEOUT = 60.0
_locks: dict[str, asyncio.Lock] = {}


def _to_out(raw: RawContainer, services: dict[str, Service], ctx: AppContext) -> ContainerOut:
    svc = services.get(raw.name)
    protected = raw.name in ctx.settings.protected_containers
    can_control = bool(
        ctx.settings.docker_control_enabled and svc and svc.allow_control and not protected
    )
    stats = None
    if raw.state == "running" and (raw.cpu_percent is not None or raw.memory_bytes is not None):
        mem_pct = (
            round(raw.memory_bytes / raw.memory_limit_bytes * 100, 1)
            if raw.memory_bytes is not None and raw.memory_limit_bytes
            else None
        )
        stats = ContainerStats(
            cpu_percent=raw.cpu_percent,
            memory_bytes=raw.memory_bytes,
            memory_limit_bytes=raw.memory_limit_bytes,
            memory_percent=mem_pct,
        )
    state = (
        raw.state
        if raw.state in ("running", "exited", "paused", "restarting", "created", "dead", "removing")
        else "unknown"
    )
    return ContainerOut(
        id=raw.id,
        short_id=raw.id[:12],
        name=raw.name,
        image=raw.image,
        state=state,
        status_text=raw.status_text,
        health=raw.health if raw.health in ("healthy", "unhealthy", "starting") else "none",
        created_at=raw.created_at,
        started_at=raw.started_at,
        restart_count=raw.restart_count,
        stats=stats,
        service_id=svc.id if svc else None,
        service_name=svc.name if svc else None,
        can_control=can_control,
        allowed_actions=[a for a in (svc.allowed_actions if svc else []) if a in ACTIONS]
        if can_control
        else [],
        protected=protected,
    )


async def _services_by_container(session: AsyncSession) -> dict[str, Service]:
    rows = (
        await session.execute(select(Service).where(Service.container_name.is_not(None)))
    ).scalars()
    return {s.container_name: s for s in rows}


async def list_containers(ctx: AppContext, session: AsyncSession) -> ContainerListResponse:
    mon = ctx.monitor
    if mon is None or mon.docker is None:
        return ContainerListResponse(
            docker_available=False,
            docker_error="Docker integration is disabled",
            containers=[],
        )
    st = mon.docker_state
    services = await _services_by_container(session)
    return ContainerListResponse(
        docker_available=st.available,
        docker_error=st.error,
        refreshed_at=st.refreshed_at,
        containers=[_to_out(c, services, ctx) for c in sorted(st.containers, key=lambda c: c.name)],
    )


async def _find(ctx: AppContext, ref: str) -> RawContainer:
    mon = ctx.monitor
    if mon is None or mon.docker is None:
        raise UnavailableError("Docker integration is disabled", code="docker_unavailable")
    c = mon.find_container(ref)
    if c is None and mon.docker_state.available:
        await mon.refresh_docker()  # maybe created since the last refresh
        c = mon.find_container(ref)
    if c is None:
        if not mon.docker_state.available:
            raise UnavailableError(
                mon.docker_state.error or "Docker is unavailable", code="docker_unavailable"
            )
        raise NotFoundError("Container not found (it may have been removed)")
    return c


async def get_container(ctx: AppContext, session: AsyncSession, ref: str) -> ContainerOut:
    raw = await _find(ctx, ref)
    return _to_out(raw, await _services_by_container(session), ctx)


async def get_logs(ctx: AppContext, ref: str, tail: int) -> ContainerLogs:
    raw = await _find(ctx, ref)
    tail = max(1, min(tail, ctx.settings.log_max_lines))
    try:
        lines, truncated = await asyncio.wait_for(
            ctx.monitor.docker.logs(raw.id, tail, ctx.settings.log_max_bytes), 15
        )
    except ContainerNotFoundError as exc:
        raise NotFoundError("Container no longer exists") from exc
    except (DockerUnavailableError, TimeoutError) as exc:
        raise UnavailableError(
            "Could not read logs from Docker", code="docker_unavailable"
        ) from exc
    lines = [ln.replace("\x00", "")[:2000] for ln in lines]
    return ContainerLogs(id=raw.id, name=raw.name, lines=lines, truncated=truncated, tail=tail)


async def perform_action(
    ctx: AppContext, session: AsyncSession, ref: str, action: str, actor: str
) -> ContainerActionResult:
    if action not in ACTIONS:  # defence in depth; routes only expose the three actions
        raise AppError("Unsupported action", status_code=400, code="unsupported_action")
    if not ctx.settings.docker_control_enabled:
        raise ForbiddenError(
            "Container control is disabled on this server", code="control_disabled"
        )
    raw = await _find(ctx, ref)
    if raw.name in ctx.settings.protected_containers:
        raise ForbiddenError(
            "This container is protected and cannot be controlled", code="protected"
        )
    svc = (await _services_by_container(session)).get(raw.name)
    if svc is None or not svc.allow_control:
        raise ForbiddenError(
            "This container is not permitted for remote control. Enable control on its "
            "service definition first.",
            code="not_permitted",
        )
    if action not in (svc.allowed_actions or []):
        raise ForbiddenError(
            f"Action '{action}' is not permitted for this container", code="action_not_permitted"
        )

    lock = _locks.setdefault(raw.id, asyncio.Lock())
    if lock.locked():
        raise ConflictError("Another action is already in progress for this container")
    async with lock:
        subject = f"container:{raw.name}"
        try:
            updated = await asyncio.wait_for(
                ctx.monitor.docker.perform(raw.id, action), ACTION_TIMEOUT
            )
        except ContainerNotFoundError as exc:
            record_event(
                session,
                f"container.{action}_failed",
                f"{action} {raw.name}: container no longer exists",
                severity="warning",
                actor=actor,
                subject=subject,
            )
            await session.commit()
            raise NotFoundError("Container no longer exists") from exc
        except (DockerUnavailableError, TimeoutError) as exc:
            record_event(
                session,
                f"container.{action}_failed",
                f"{action} {raw.name}: Docker error",
                severity="warning",
                actor=actor,
                subject=subject,
            )
            await session.commit()
            raise UnavailableError(
                f"Docker did not complete the {action} operation", code="docker_unavailable"
            ) from exc
        except Exception as exc:
            log.exception("unexpected docker error during %s", action)
            record_event(
                session,
                f"container.{action}_failed",
                f"{action} {raw.name}: unexpected error",
                severity="warning",
                actor=actor,
                subject=subject,
            )
            await session.commit()
            raise AppError(
                "Container operation failed", status_code=502, code="docker_error"
            ) from exc

        svc.expected_state = "stopped" if action == "stop" else "running"
        # Keep the cached snapshot truthful immediately rather than waiting for the next poll.
        snap = ctx.monitor.docker_state.containers
        for i, c in enumerate(snap):
            if c.id == raw.id:
                updated.cpu_percent = updated.memory_bytes = updated.memory_limit_bytes = None
                snap[i] = updated
        record_event(
            session,
            f"container.{action}",
            f"{actor} requested {action} on {raw.name}",
            actor=actor,
            subject=subject,
            data={"container_id": raw.id[:12], "result": updated.state},
        )
        return ContainerActionResult(
            id=raw.id,
            name=raw.name,
            action=action,
            ok=True,  # type: ignore[arg-type]
            state=updated.state
            if updated.state
            in ("running", "exited", "paused", "restarting", "created", "dead", "removing")
            else "unknown",  # type: ignore[arg-type]
            message=f"{action.capitalize()} completed; container is now {updated.state}",
        )
