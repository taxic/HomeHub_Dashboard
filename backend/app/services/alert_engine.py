"""Rules-based alert engine.

Every cycle the engine computes the set of *currently true* conditions, then reconciles them
with the persisted alerts:

* new condition (confirmed for ``CONFIRM_CYCLES`` consecutive cycles) -> open alert + event;
* condition still true -> same alert is updated (deduplicated), never duplicated;
* condition gone -> alert resolved automatically + event;
* notifications are limited by a per-key cooldown and are never sent for acknowledged alerts,
  except escalations (warning -> critical) which always notify.

Rule groups are only allowed to *resolve* alerts whose subject they actually evaluated this
cycle: if Docker is unreachable we cannot claim a stopped container has recovered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AppContext
from app.models import Alert, BackupJob, Service
from app.notifications.base import Notification, Notifier
from app.services import backup_service
from app.services.events import record_event

log = logging.getLogger(__name__)

CONFIRM_CYCLES = 2
SEV_RANK = {"warning": 1, "critical": 2}


@dataclass
class Condition:
    key: str
    type: str
    severity: str
    title: str
    message: str
    subject: str | None = None


class AlertEngine:
    def __init__(self, ctx: AppContext, monitor, notifiers: list[Notifier] | None = None) -> None:
        self.ctx = ctx
        self.monitor = monitor
        self.notifiers = notifiers or []
        self._streak: dict[str, int] = {}

    # ------------------------------------------------------------ rule groups
    def _host_rules(self, out: list[Condition], evaluated: list[str]) -> None:
        cfg, mon = self.ctx.runtime, self.monitor
        if mon.host is None:
            return
        if mon.is_stale():
            evaluated.append("monitor:host")
            out.append(
                Condition(
                    "monitor:host_stale",
                    "monitor_stale",
                    "warning",
                    "Host monitoring is not updating",
                    "No fresh host metrics have been collected recently.",
                    "host",
                )
            )
            return
        evaluated.append("monitor:host")
        for which, label in (("cpu", "CPU"), ("mem", "Memory")):
            warn, crit = (
                getattr(cfg, f"{which}_warn_percent"),
                getattr(cfg, f"{which}_crit_percent"),
            )
            mins = getattr(cfg, f"{which}_duration_minutes")
            evaluated.append(f"host:{which}")
            sev = (
                "critical"
                if mon.sustained_above(which, crit, mins)
                else "warning"
                if mon.sustained_above(which, warn, mins)
                else None
            )
            if sev:
                now_val = (
                    mon.host.cpu_percent
                    if which == "cpu"
                    else (mon.host.memory.percent if mon.host.memory else None)
                )
                limit = crit if sev == "critical" else warn
                out.append(
                    Condition(
                        f"host:{which}",
                        f"{which}_high",
                        sev,
                        f"{label} usage is high",
                        f"{label} has stayed above {limit:g}% for at least {mins} minute(s) "
                        f"(now {now_val:.0f}%)."
                        if now_val is not None
                        else f"{label} above {limit:g}%.",
                        "host",
                    )
                )

    def _storage_rules(self, out: list[Condition], evaluated: list[str]) -> None:
        cfg, mon = self.ctx.runtime, self.monitor
        vols = ([mon.root_volume] if mon.root_volume else []) + list(mon.volumes)
        for v in vols:
            sid = "root" if v.id is None else str(v.id)
            evaluated += [f"storage:{sid}:"]
            if v.state == "disabled":
                continue
            if v.state != "ok":
                if v.required:
                    out.append(
                        Condition(
                            f"storage:{sid}:mount",
                            "mount_unavailable",
                            "critical",
                            f"Storage '{v.name}' is unavailable",
                            f"{v.path}: {v.message or v.state}. Nothing was modified.",
                            f"volume:{sid}",
                        )
                    )
                continue
            if v.percent is None:
                continue
            sev = (
                "critical"
                if v.percent >= cfg.storage_crit_percent
                else "warning"
                if v.percent >= cfg.storage_warn_percent
                else None
            )
            if sev:
                limit = cfg.storage_crit_percent if sev == "critical" else cfg.storage_warn_percent
                out.append(
                    Condition(
                        f"storage:{sid}:usage",
                        "storage_high",
                        sev,
                        f"Storage '{v.name}' is filling up",
                        f"{v.path} is {v.percent:.0f}% full (threshold {limit:g}%).",
                        f"volume:{sid}",
                    )
                )

    def _service_rules(
        self, services: list[Service], out: list[Condition], evaluated: list[str]
    ) -> None:
        st = self.monitor.docker_state
        docker_on = self.monitor.docker is not None
        if docker_on:
            evaluated.append("docker:")
            if not st.available and st.ever_available:
                out.append(
                    Condition(
                        "docker:unavailable",
                        "docker_unavailable",
                        "warning",
                        "Docker is unreachable",
                        f"Monitoring lost contact with Docker: {st.error}",
                        "docker",
                    )
                )
        for s in services:
            if not s.enabled:
                continue
            if s.url:
                evaluated.append(f"service:{s.id}:")
                if s.health_status == "unhealthy":
                    out.append(
                        Condition(
                            f"service:{s.id}:down",
                            "service_down",
                            "critical",
                            f"{s.name} is unavailable",
                            s.last_error or "Health check failing",
                            f"service:{s.id}",
                        )
                    )
            if s.container_name and docker_on and st.available:
                evaluated.append(f"container:{s.id}:")
                c = self.monitor.find_container(s.container_name)
                if s.expected_state == "running":
                    if c is None or c.state not in ("running",):
                        reason = "not found" if c is None else c.state
                        sev = "warning" if (c and c.state == "restarting") else "critical"
                        out.append(
                            Condition(
                                f"container:{s.id}:down",
                                "container_down",
                                sev,
                                f"Container for {s.name} is not running",
                                f"Container '{s.container_name}' is {reason} but was expected to be running.",
                                f"service:{s.id}",
                            )
                        )
                    elif c.health == "unhealthy":
                        out.append(
                            Condition(
                                f"container:{s.id}:unhealthy",
                                "container_unhealthy",
                                "warning",
                                f"Container for {s.name} reports unhealthy",
                                f"Docker health check for '{s.container_name}' is failing.",
                                f"service:{s.id}",
                            )
                        )

    def _backup_rules(
        self, jobs: list[BackupJob], now: datetime, out: list[Condition], evaluated: list[str]
    ) -> None:
        for j in jobs:
            evaluated.append(f"backup:{j.id}:")
            if not j.enabled:
                continue
            state, reason = backup_service.compute_state(j, now)
            if state == "never_run" and now - j.created_at < timedelta(hours=j.max_age_hours):
                continue  # grace period for newly defined jobs
            if state in ("never_run", "overdue"):
                very = (
                    state == "overdue"
                    and j.last_success_at
                    and (now - j.last_success_at > timedelta(hours=j.max_age_hours * 2))
                )
                out.append(
                    Condition(
                        f"backup:{j.id}:state",
                        "backup_overdue",
                        "critical" if very else "warning",
                        f"Backup '{j.name}' is overdue",
                        reason or "",
                        f"backup:{j.id}",
                    )
                )
            elif state == "failed":
                out.append(
                    Condition(
                        f"backup:{j.id}:state",
                        "backup_failed",
                        "critical",
                        f"Backup '{j.name}' failed",
                        reason or "",
                        f"backup:{j.id}",
                    )
                )
            elif state == "restore_failed":
                out.append(
                    Condition(
                        f"backup:{j.id}:state",
                        "backup_restore_failed",
                        "warning",
                        f"Restore test for '{j.name}' failed",
                        reason or "",
                        f"backup:{j.id}",
                    )
                )

    # ------------------------------------------------------------ reconciliation
    async def evaluate(self, now: datetime | None = None) -> list[Alert]:
        now = now or datetime.now(UTC)
        out: list[Condition] = []
        evaluated: list[str] = []
        async with self.ctx.session_factory() as session:
            services = list((await session.execute(select(Service))).scalars())
            jobs = list((await session.execute(select(BackupJob))).scalars())
            self._host_rules(out, evaluated)
            self._storage_rules(out, evaluated)
            self._service_rules(services, out, evaluated)
            self._backup_rules(jobs, now, out, evaluated)
            # deleted/disabled things must not leave alerts open forever
            evaluated += [f"service:{s.id}:" for s in services if not s.enabled]
            evaluated += [f"container:{s.id}:" for s in services if not s.enabled]
            live_ids = {s.id for s in services}
            open_alerts = list(
                (await session.execute(select(Alert).where(Alert.status == "open"))).scalars()
            )
            for a in open_alerts:
                if a.key.startswith(("service:", "container:")):
                    sid = int(a.key.split(":")[1])
                    if sid not in live_ids:
                        evaluated.append(a.key)
                if a.key.startswith("backup:") and int(a.key.split(":")[1]) not in {
                    j.id for j in jobs
                }:
                    evaluated.append(a.key)

            pending: list[Notification] = []
            active_keys = {c.key for c in out}
            # confirmation streaks
            for key in list(self._streak):
                if key not in active_keys:
                    del self._streak[key]
            for c in out:
                self._streak[c.key] = self._streak.get(c.key, 0) + 1

            by_key = {a.key: a for a in open_alerts}
            touched: list[Alert] = []
            for c in out:
                existing = by_key.get(c.key)
                if existing is None and self._streak[c.key] < CONFIRM_CYCLES:
                    continue
                touched.append(await self._raise(session, c, existing, now, pending))
            for a in open_alerts:
                if a.key in active_keys:
                    continue
                if any(a.key.startswith(p) or a.key == p for p in evaluated):
                    self._resolve(session, a, now, pending)
            await session.commit()
        await self._deliver(pending)
        return touched

    async def _raise(
        self,
        session: AsyncSession,
        c: Condition,
        existing: Alert | None,
        now: datetime,
        pending: list[Notification],
    ) -> Alert:
        cfg = self.ctx.runtime
        min_rank = SEV_RANK[cfg.notify_min_severity]
        if existing is None:
            prev = (
                await session.execute(
                    select(Alert).where(Alert.key == c.key).order_by(Alert.id.desc()).limit(1)
                )
            ).scalar_one_or_none()
            alert = Alert(
                key=c.key,
                type=c.type,
                severity=c.severity,
                title=c.title,
                message=c.message,
                subject=c.subject,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(alert)
            await session.flush()
            record_event(
                session,
                "alert.opened",
                f"{c.title}: {c.message}",
                severity=c.severity,
                subject=f"alert:{alert.id}",
                data={"key": c.key},
            )
            # Flap damping: if this key notified recently, open silently and keep the cooldown clock.
            recently = (
                prev
                and prev.last_notified_at
                and (now - prev.last_notified_at < timedelta(minutes=cfg.alert_renotify_minutes))
            )
            if recently:
                alert.last_notified_at = prev.last_notified_at
            elif SEV_RANK[c.severity] >= min_rank:
                alert.last_notified_at = now
                pending.append(Notification("opened", c.severity, c.title, c.message))
            return alert

        existing.last_seen_at = now
        existing.occurrences += 1
        existing.message = c.message
        if SEV_RANK[c.severity] > SEV_RANK[existing.severity]:
            existing.severity = c.severity
            existing.acknowledged_at = None  # an escalation needs fresh attention
            existing.acknowledged_by = None
            record_event(
                session,
                "alert.escalated",
                f"{c.title}: now {c.severity}",
                severity=c.severity,
                subject=f"alert:{existing.id}",
            )
            existing.last_notified_at = now
            pending.append(Notification("escalated", c.severity, c.title, c.message))
        elif SEV_RANK[c.severity] < SEV_RANK[existing.severity]:
            existing.severity = c.severity
        elif (
            existing.acknowledged_at is None
            and SEV_RANK[existing.severity] >= min_rank
            and existing.last_notified_at is not None
            and now - existing.last_notified_at >= timedelta(minutes=cfg.alert_renotify_minutes)
        ):
            existing.last_notified_at = now
            pending.append(Notification("reminder", existing.severity, c.title, c.message))
        return existing

    def _resolve(
        self, session: AsyncSession, alert: Alert, now: datetime, pending: list[Notification]
    ) -> None:
        alert.status = "resolved"
        alert.resolved_at = now
        record_event(
            session,
            "alert.resolved",
            f"{alert.title}: resolved",
            severity="info",
            subject=f"alert:{alert.id}",
        )
        # Only tell the user it resolved if they were told it opened during *this* alert's life
        # (a flap-damped silent re-open copies an older timestamp).
        notified_this_life = (
            alert.last_notified_at is not None and alert.last_notified_at >= alert.first_seen_at
        )
        if self.ctx.runtime.notify_on_resolve and notified_this_life:
            pending.append(
                Notification("resolved", alert.severity, alert.title, "The condition has cleared.")
            )

    async def _deliver(self, pending: list[Notification]) -> None:
        cfg = self.ctx.runtime
        if not pending or not cfg.telegram_enabled:
            return
        for n in pending:
            for notifier in self.notifiers:
                if not notifier.configured():
                    continue
                try:
                    await notifier.send(n)
                except Exception as exc:
                    log.warning("notifier %s failed: %s", notifier.name, exc)
