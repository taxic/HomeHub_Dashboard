from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AppContext
from app.models import Alert, BackupJob, Event, Service
from app.schemas.alert import AlertCounts, AlertOut, EventOut
from app.schemas.overview import BackupCounts, ContainerCounts, Overview, ServiceCounts
from app.services import backup_service, service_service


async def alert_counts(session: AsyncSession) -> AlertCounts:
    rows = (await session.execute(select(Alert).where(Alert.status == "open"))).scalars().all()
    return AlertCounts(
        open=len(rows),
        critical=sum(a.severity == "critical" for a in rows),
        warning=sum(a.severity == "warning" for a in rows),
        unacknowledged=sum(a.acknowledged_at is None for a in rows),
    )


def container_counts(ctx: AppContext) -> ContainerCounts:
    mon = ctx.monitor
    if mon is None or mon.docker is None:
        return ContainerCounts(available=False, error="Docker integration is disabled")
    st = mon.docker_state
    if not st.available:
        return ContainerCounts(available=False, error=st.error)
    running = [c for c in st.containers if c.state == "running"]
    return ContainerCounts(
        available=True,
        running=len(running),
        stopped=sum(c.state in ("exited", "created", "dead", "paused") for c in st.containers),
        unhealthy=sum(c.health == "unhealthy" or c.state == "restarting" for c in st.containers),
        total=len(st.containers),
    )


async def build(ctx: AppContext, session: AsyncSession) -> Overview:
    mon = ctx.monitor
    now = datetime.now(UTC)
    services = (await session.execute(select(Service))).scalars().all()
    sc = ServiceCounts(total=len(services))
    for s in services:
        status = service_service.build_view(s, mon).effective_status
        setattr(sc, status, getattr(sc, status) + 1)

    jobs = (
        (await session.execute(select(BackupJob).where(BackupJob.enabled.is_(True))))
        .scalars()
        .all()
    )
    bc = BackupCounts(total=len(jobs))
    for j in jobs:
        if backup_service.compute_state(j, now)[0] in backup_service.PROBLEM_STATES:
            bc.problem += 1
        else:
            bc.ok += 1

    alerts = await alert_counts(session)
    recent_alerts = (
        (await session.execute(select(Alert).order_by(Alert.last_seen_at.desc()).limit(5)))
        .scalars()
        .all()
    )
    recent_events = (
        (await session.execute(select(Event).order_by(Event.ts.desc(), Event.id.desc()).limit(8)))
        .scalars()
        .all()
    )

    host = mon.host if mon else None
    stale = True if mon is None else mon.is_stale()
    if host is None or stale:
        status, reason = (
            "unknown",
            ("No host data has been collected yet" if host is None else "Host data is stale"),
        )
    elif alerts.critical:
        status, reason = "critical", f"{alerts.critical} critical alert(s) open"
    elif alerts.warning:
        status, reason = "warning", f"{alerts.warning} warning alert(s) open"
    else:
        status, reason = "healthy", None

    return Overview(
        status=status,  # type: ignore[arg-type]
        status_reason=reason,
        generated_at=now,
        last_update=host.sampled_at if host else None,
        stale=stale,
        refresh_seconds=ctx.runtime.dashboard_refresh_seconds,
        host=host,
        root_volume=mon.root_volume if mon else None,
        volumes=mon.volumes if mon else [],
        containers=container_counts(ctx),
        services=sc,
        backups=bc,
        alerts=alerts,
        recent_alerts=[AlertOut.model_validate(a) for a in recent_alerts],
        recent_events=[EventOut.model_validate(e) for e in recent_events],
    )
