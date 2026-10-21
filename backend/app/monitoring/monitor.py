"""Background monitoring: host sampling, Docker refresh, health checks, persistence.

All API reads are served from in-memory snapshots maintained here, so a slow disk, Docker
daemon or monitored service can never block an HTTP request.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.context import AppContext
from app.database.base import utcnow
from app.models import Service, StorageVolume
from app.monitoring.docker_gateway import (
    DockerGateway,
    DockerUnavailableError,
    RawContainer,
    SDKDockerGateway,
    compute_cpu_percent,
    compute_memory,
)
from app.monitoring.healthcheck import HealthChecker
from app.monitoring.host import HostCollector
from app.schemas.metrics import HostMetrics, VolumeStatus
from app.services import metrics_service
from app.services.events import record_event

log = logging.getLogger(__name__)

SCHEDULER_TICK = 3.0
VOLUME_MIN_INTERVAL = 30.0
STATS_CONCURRENCY = 4
STATS_TIMEOUT = 8.0
MAINTENANCE_INTERVAL = 3600.0


@dataclass
class DockerState:
    available: bool = False
    error: str | None = "Docker has not been queried yet"
    refreshed_at: datetime | None = None
    containers: list[RawContainer] = field(default_factory=list)
    ever_available: bool = False


class Monitor:
    def __init__(
        self,
        ctx: AppContext,
        *,
        docker: DockerGateway | None = None,
        checker: HealthChecker | None = None,
        collector: HostCollector | None = None,
    ) -> None:
        self.ctx = ctx
        s = ctx.settings
        self.collector = collector or HostCollector(s.host_proc_path, s.host_sys_path)
        self.docker: DockerGateway | None = docker
        if self.docker is None and s.docker_enabled:
            self.docker = SDKDockerGateway(s.docker_host)
        ctx.docker = self.docker
        self.checker = checker or HealthChecker(
            allow_loopback=s.healthcheck_allow_loopback, allow_private=s.healthcheck_allow_private
        )
        self.host: HostMetrics | None = None
        self.root_volume: VolumeStatus | None = None
        self.volumes: list[VolumeStatus] = []
        self.docker_state = DockerState(
            available=False, error=None if self.docker else "Docker integration is disabled"
        )
        # recent (monotonic_ts, cpu, mem) for sustained-threshold alerts
        self.recent: deque[tuple[float, float | None, float | None]] = deque(maxlen=2000)
        self._sem = asyncio.Semaphore(s.healthcheck_concurrency)
        self._inflight: set[int] = set()
        self._tasks: list[asyncio.Task] = []
        self._check_tasks: set[asyncio.Task] = set()
        self._stopping = False
        self.alert_engine = None  # set by main when alerts are enabled
        self.last_maintenance: dict[str, int] | None = None

    # ------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        self._stopping = False
        loops = [self._host_loop, self._persist_loop, self._health_loop, self._maintenance_loop]
        if self.docker:
            loops.append(self._docker_loop)
        if self.alert_engine:
            loops.append(self._alert_loop)
        for fn in loops:
            self._tasks.append(asyncio.create_task(self._guard(fn), name=fn.__name__))

    async def stop(self) -> None:
        self._stopping = True
        pending = [*self._tasks, *self._check_tasks]
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        self._tasks.clear()
        self._check_tasks.clear()

    async def _guard(self, fn) -> None:
        """Run a loop forever; a crash restarts it after a pause instead of killing monitoring."""
        while not self._stopping:
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("monitor loop %s crashed; restarting in 5s", fn.__name__)
                await asyncio.sleep(5)

    # ------------------------------------------------------------- host
    async def sample_host(self, *, volumes: bool = True) -> None:
        host = await asyncio.to_thread(self.collector.collect)
        self.host = host
        self.recent.append(
            (time.monotonic(), host.cpu_percent, host.memory.percent if host.memory else None)
        )
        if volumes:
            await self.refresh_volumes()

    async def refresh_volumes(self) -> None:
        s = self.ctx.settings
        self.root_volume = await self.collector.check_volume(
            volume_id=None,
            name="Root filesystem",
            path=s.root_path,
            kind="root",
            required=True,
            require_mountpoint=False,
            marker_file=None,
            root_path=s.root_path,
        )
        async with self.ctx.session_factory() as session:
            defs = (
                (await session.execute(select(StorageVolume).order_by(StorageVolume.name)))
                .scalars()
                .all()
            )
        results = await asyncio.gather(
            *[
                self.collector.check_volume(
                    volume_id=v.id,
                    name=v.name,
                    path=v.path,
                    kind=v.kind,
                    required=v.required,
                    require_mountpoint=v.require_mountpoint,
                    marker_file=v.marker_file,
                    root_path=s.root_path,
                    enabled=v.enabled,
                )
                for v in defs
            ]
        )
        self.volumes = list(results)

    async def _host_loop(self) -> None:
        last_vol = 0.0
        while True:
            t0 = time.monotonic()
            try:
                due = t0 - last_vol >= max(
                    VOLUME_MIN_INTERVAL, self.ctx.runtime.host_sample_seconds
                )
                await self.sample_host(volumes=due)
                if due:
                    last_vol = t0
            except Exception:
                log.exception("host sampling failed")
            await asyncio.sleep(
                max(1.0, self.ctx.runtime.host_sample_seconds - (time.monotonic() - t0))
            )

    async def _persist_loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                if self.host:
                    row = metrics_service.sample_from_snapshot(
                        self.host, self.volumes, self.root_volume, utcnow()
                    )
                    if row:
                        async with self.ctx.session_factory() as session:
                            await metrics_service.persist_sample(session, row)
                            await session.commit()
            except Exception:
                log.exception("metric persistence failed")
            await asyncio.sleep(self.ctx.runtime.metric_persist_seconds)

    async def _maintenance_loop(self) -> None:
        await asyncio.sleep(30)
        while True:
            try:
                async with self.ctx.session_factory() as session:
                    self.last_maintenance = await metrics_service.rollup_and_prune(
                        session, self.ctx.runtime
                    )
                    await session.commit()
            except Exception:
                log.exception("retention maintenance failed")
            await asyncio.sleep(MAINTENANCE_INTERVAL)

    # ------------------------------------------------------------- docker
    async def refresh_docker(self) -> None:
        if not self.docker:
            return
        st = self.docker_state
        try:
            containers = await self.docker.list_containers()
        except DockerUnavailableError as exc:
            if st.available:
                log.warning("Docker became unavailable: %s", exc)
            st.available, st.error = False, str(exc)
            st.containers = []
            return
        sem = asyncio.Semaphore(STATS_CONCURRENCY)

        async def fetch(c: RawContainer) -> None:
            if c.state != "running":
                return
            async with sem:
                try:
                    stats = await asyncio.wait_for(self.docker.get_stats(c.id), STATS_TIMEOUT)
                except Exception:
                    return  # stats are optional; leave as unavailable (None)
            if stats:
                c.cpu_percent = compute_cpu_percent(stats)
                c.memory_bytes, c.memory_limit_bytes = compute_memory(stats)

        await asyncio.gather(*[fetch(c) for c in containers])
        st.containers = containers
        st.available, st.error, st.ever_available = True, None, True
        st.refreshed_at = datetime.now(UTC)

    async def _docker_loop(self) -> None:
        while True:
            t0 = time.monotonic()
            try:
                await self.refresh_docker()
            except Exception:
                log.exception("docker refresh failed")
            await asyncio.sleep(
                max(1.0, self.ctx.runtime.docker_refresh_seconds - (time.monotonic() - t0))
            )

    def find_container(self, ref: str) -> RawContainer | None:
        """Look up by full/short id or exact name in the server-side snapshot."""
        for c in self.docker_state.containers:
            if c.id == ref or (len(ref) >= 12 and c.id.startswith(ref)) or c.name == ref:
                return c
        return None

    # ------------------------------------------------------------- health checks
    async def check_service(self, service_id: int, *, manual: bool = False) -> bool:
        """Run one check and persist the result. Returns False if skipped (already running)."""
        if service_id in self._inflight:
            return False
        self._inflight.add(service_id)
        try:
            async with self._sem:
                async with self.ctx.session_factory() as session:
                    svc = await session.get(Service, service_id)
                    if svc is None or not svc.url or (not svc.enabled and not manual):
                        return True
                    url, expected, timeout, verify = (
                        svc.url,
                        svc.expected_status,
                        svc.timeout_seconds,
                        svc.verify_tls,
                    )
                result = await self.checker.check(
                    url, expected_status=expected, timeout=timeout, verify_tls=verify
                )
                async with self.ctx.session_factory() as session:
                    svc = await session.get(Service, service_id)
                    if svc is None:
                        return True
                    self._apply_result(session, svc, result)
                    await session.commit()
        finally:
            self._inflight.discard(service_id)
        return True

    def _apply_result(self, session, svc: Service, result) -> None:
        now = utcnow()
        threshold = self.ctx.runtime.service_failure_threshold
        before = svc.health_status
        svc.last_checked_at = now
        svc.last_status_code = result.status_code
        svc.last_response_ms = result.response_ms
        if result.ok:
            svc.consecutive_failures = 0
            svc.health_status = "healthy"
            svc.last_success_at = now
            svc.last_error = None
        else:
            svc.consecutive_failures += 1
            svc.last_error = result.error
            # Debounce: only flip to unhealthy after N consecutive failures, so a single
            # blip does not flap the status or raise alerts.
            if svc.consecutive_failures >= threshold:
                svc.health_status = "unhealthy"
        if before != svc.health_status and before != "unknown":
            record_event(
                session,
                "service.recovered" if svc.health_status == "healthy" else "service.unhealthy",
                f"{svc.name} is now {svc.health_status}"
                + (f": {svc.last_error}" if svc.health_status == "unhealthy" else ""),
                severity="info" if svc.health_status == "healthy" else "warning",
                subject=f"service:{svc.id}",
            )

    async def _health_loop(self) -> None:
        while True:
            try:
                await self._schedule_due()
            except Exception:
                log.exception("health scheduling failed")
            await asyncio.sleep(SCHEDULER_TICK)

    async def _schedule_due(self) -> None:
        now = utcnow()
        async with self.ctx.session_factory() as session:
            rows = (
                await session.execute(
                    select(Service.id, Service.interval_seconds, Service.last_checked_at).where(
                        Service.enabled.is_(True), Service.url.is_not(None)
                    )
                )
            ).all()
        for sid, interval, last in rows:
            if sid in self._inflight:
                continue
            if last is None or now - last >= timedelta(seconds=interval):
                task = asyncio.create_task(self._run_check(sid))
                self._check_tasks.add(task)
                task.add_done_callback(self._check_tasks.discard)

    async def _run_check(self, sid: int) -> None:
        try:
            await self.check_service(sid)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("service check %s crashed", sid)

    async def _alert_loop(self) -> None:
        await asyncio.sleep(10)
        while True:
            try:
                await self.alert_engine.evaluate()
            except Exception:
                log.exception("alert evaluation failed")
            await asyncio.sleep(15)

    # ------------------------------------------------------------- helpers
    def sample_age_seconds(self) -> float | None:
        if not self.host:
            return None
        return (datetime.now(UTC) - self.host.sampled_at).total_seconds()

    def is_stale(self) -> bool:
        age = self.sample_age_seconds()
        return age is None or age > max(30.0, self.ctx.runtime.host_sample_seconds * 3)

    def sustained_above(self, which: str, threshold: float, minutes: int) -> bool:
        """True when every sample in the last ``minutes`` exceeded the threshold and the
        window is substantially covered (guards against alerting off one stray sample)."""
        horizon = time.monotonic() - minutes * 60
        window = [(t, c if which == "cpu" else m) for t, c, m in self.recent if t >= horizon]
        vals = [v for _, v in window if v is not None]
        if not vals or len(vals) != len(window):
            return False
        interval = max(5, self.ctx.runtime.host_sample_seconds)
        covered = window[-1][0] - window[0][0]
        return covered >= minutes * 60 - 2 * interval and all(v >= threshold for v in vals)
