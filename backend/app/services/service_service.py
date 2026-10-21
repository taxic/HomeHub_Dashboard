from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import Service
from app.monitoring.monitor import Monitor
from app.monitoring.ssrf import check_url_syntax_blocked
from app.schemas.service import ServiceCreate, ServicePatch, ServiceView
from app.services.events import record_event


def _validate_target(settings: Settings, url: str | None) -> None:
    if not url:
        return
    reason = check_url_syntax_blocked(
        url,
        allow_loopback=settings.healthcheck_allow_loopback,
        allow_private=settings.healthcheck_allow_private,
    )
    if reason:
        raise AppError(
            reason,
            status_code=422,
            code="blocked_url",
            details=[{"field": "url", "message": reason}],
        )


async def _ensure_unique_name(
    session: AsyncSession, name: str, exclude_id: int | None = None
) -> None:
    q = select(Service.id).where(func.lower(Service.name) == name.lower())
    if exclude_id is not None:
        q = q.where(Service.id != exclude_id)
    if (await session.execute(q)).first():
        raise ConflictError(f"A service named '{name}' already exists", code="duplicate_name")


def _check_consistency(data: dict) -> None:
    if data.get("allow_control") and not data.get("container_name"):
        raise AppError(
            "Container control requires an associated container name",
            status_code=422,
            code="validation_error",
            details=[{"field": "allow_control", "message": "Set container_name first"}],
        )
    if data.get("allow_control") and not data.get("allowed_actions"):
        raise AppError(
            "Choose at least one permitted action when control is enabled",
            status_code=422,
            code="validation_error",
            details=[{"field": "allowed_actions", "message": "Select start, stop and/or restart"}],
        )
    if not data.get("url") and not data.get("container_name"):
        raise AppError(
            "A service needs a health-check URL, a Docker container, or both",
            status_code=422,
            code="validation_error",
            details=[{"field": "url", "message": "Provide a URL or a container name"}],
        )


async def create_service(
    session: AsyncSession, settings: Settings, body: ServiceCreate, actor: str
) -> Service:
    data = body.model_dump()
    _check_consistency(data)
    _validate_target(settings, data["url"])
    await _ensure_unique_name(session, data["name"])
    svc = Service(**data)
    session.add(svc)
    await session.flush()
    record_event(
        session,
        "service.created",
        f"Service '{svc.name}' created",
        actor=actor,
        subject=f"service:{svc.id}",
    )
    return svc


async def get_or_404(session: AsyncSession, service_id: int) -> Service:
    svc = await session.get(Service, service_id)
    if svc is None:
        raise NotFoundError("Service not found")
    return svc


async def update_service(
    session: AsyncSession, settings: Settings, svc: Service, body: ServicePatch, actor: str
) -> Service:
    changes = body.model_dump(exclude_unset=True)
    # url / container_name may be explicitly cleared with null/"".
    merged = {
        c: getattr(svc, c) for c in ("url", "container_name", "allow_control", "allowed_actions")
    } | changes
    for non_nullable in (
        "name",
        "category",
        "expected_status",
        "verify_tls",
        "interval_seconds",
        "timeout_seconds",
        "enabled",
        "allow_control",
        "allowed_actions",
    ):
        if non_nullable in changes and changes[non_nullable] is None:
            raise AppError(
                f"{non_nullable} cannot be null", status_code=422, code="validation_error"
            )
    if "allow_control" not in changes and merged["allow_control"] and not merged["container_name"]:
        merged["allow_control"] = False
        changes["allow_control"] = False  # clearing the container revokes control
    _check_consistency(merged)
    if "url" in changes:
        _validate_target(settings, changes["url"])
        changes["last_checked_at"] = None  # re-check promptly with the new target
        changes["health_status"] = "unknown"
        changes["consecutive_failures"] = 0
    if "name" in changes:
        await _ensure_unique_name(session, changes["name"], svc.id)
    for k, v in changes.items():
        setattr(svc, k, v)
    record_event(
        session,
        "service.updated",
        f"Service '{svc.name}' updated",
        actor=actor,
        subject=f"service:{svc.id}",
        data={"fields": sorted(body.model_dump(exclude_unset=True))},
    )
    return svc


def build_view(svc: Service, monitor: Monitor | None) -> ServiceView:
    view = ServiceView.model_validate(svc)
    container = None
    docker_ok = bool(monitor and monitor.docker_state.available)
    if svc.container_name and monitor and docker_ok:
        container = monitor.find_container(svc.container_name)
        view.container_state = container.state if container else "missing"
        view.container_health = container.health if container else None

    if not svc.enabled:
        view.effective_status, view.effective_reason = "disabled", "Monitoring disabled"
        return view

    problems: list[str] = []
    unknowns: list[str] = []
    degraded: list[str] = []

    if svc.container_name:
        if not monitor or not docker_ok:
            unknowns.append("Docker is unavailable")
        elif container is None:
            problems.append("Container not found")
        elif container.state != "running":
            if svc.expected_state == "stopped":
                unknowns.append("Stopped intentionally via Command Centre")
            else:
                problems.append(f"Container is {container.state}")
        elif container.health == "unhealthy":
            problems.append("Container health check failing")
        elif container.health == "starting":
            degraded.append("Container health check starting")
    if svc.url:
        if svc.health_status == "unhealthy":
            problems.append(svc.last_error or "Health check failing")
        elif svc.health_status == "unknown":
            unknowns.append("Not checked yet")

    if problems:
        view.effective_status, view.effective_reason = "unhealthy", "; ".join(problems)
    elif degraded:
        view.effective_status, view.effective_reason = "degraded", "; ".join(degraded)
    elif unknowns:
        view.effective_status, view.effective_reason = "unknown", "; ".join(unknowns)
    else:
        view.effective_status = "healthy"
    return view
