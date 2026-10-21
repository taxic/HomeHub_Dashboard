"""Metric persistence, rollup/retention and history queries.

Strategy: one *wide* row per sampling interval (not a row per metric), full-resolution
rows kept for ``retention_raw_hours``, then averaged into 5-minute rows kept for
``retention_rollup_days``. NULL means "unavailable" and is never averaged as zero.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, Event, MetricSample
from app.models.metric import METRIC_FIELDS
from app.schemas.metrics import HistoryPoint, HistoryResponse, HostMetrics, VolumeStatus
from app.schemas.settings import AppSettings

RAW = 60
ROLLUP = 300
ROLLUP_SECONDS = 300

# range -> (window, bucket seconds)
RANGES: dict[str, tuple[timedelta, int]] = {
    "1h": (timedelta(hours=1), 60),
    "6h": (timedelta(hours=6), 60),
    "24h": (timedelta(hours=24), 300),
    "7d": (timedelta(days=7), 1800),
    "30d": (timedelta(days=30), 7200),
}


def sample_from_snapshot(
    host: HostMetrics, volumes: list[VolumeStatus], root: VolumeStatus | None, ts: datetime
) -> MetricSample | None:
    ext = [v.percent for v in volumes if v.state == "ok" and v.percent is not None]
    row = MetricSample(
        ts=ts.replace(microsecond=0),
        resolution=RAW,
        cpu_percent=host.cpu_percent,
        mem_percent=host.memory.percent if host.memory else None,
        swap_percent=host.swap.percent if host.swap else None,
        load1=host.load_avg[0] if host.load_avg else None,
        disk_root_percent=root.percent if root and root.state == "ok" else None,
        storage_max_percent=max(ext) if ext else None,
        net_rx_bps=host.network.rx_bps if host.network else None,
        net_tx_bps=host.network.tx_bps if host.network else None,
        temp_c=host.temperature_c,
    )
    if all(getattr(row, f) is None for f in METRIC_FIELDS):
        return None  # nothing was measured; don't store an empty row
    return row


async def persist_sample(session: AsyncSession, sample: MetricSample) -> bool:
    exists = (
        await session.execute(
            select(MetricSample.id).where(
                MetricSample.ts == sample.ts, MetricSample.resolution == sample.resolution
            )
        )
    ).first()
    if exists:
        return False
    session.add(sample)
    return True


def _floor(ts: datetime, seconds: int) -> datetime:
    return datetime.fromtimestamp(int(ts.timestamp()) // seconds * seconds, UTC)


def _avg(values: list[float | None]) -> float | None:
    real = [v for v in values if v is not None]
    return round(sum(real) / len(real), 2) if real else None


async def rollup_and_prune(
    session: AsyncSession, cfg: AppSettings, now: datetime | None = None
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    cutoff = _floor(now - timedelta(hours=cfg.retention_raw_hours), ROLLUP_SECONDS)
    rows = (
        (
            await session.execute(
                select(MetricSample)
                .where(MetricSample.resolution == RAW, MetricSample.ts < cutoff)
                .order_by(MetricSample.ts)
            )
        )
        .scalars()
        .all()
    )
    buckets: dict[datetime, list[MetricSample]] = defaultdict(list)
    for r in rows:
        buckets[_floor(r.ts, ROLLUP_SECONDS)].append(r)
    created = 0
    for bucket_ts, group in buckets.items():
        exists = (
            await session.execute(
                select(MetricSample.id).where(
                    MetricSample.ts == bucket_ts, MetricSample.resolution == ROLLUP
                )
            )
        ).first()
        if not exists:
            session.add(
                MetricSample(
                    ts=bucket_ts,
                    resolution=ROLLUP,
                    **{f: _avg([getattr(g, f) for g in group]) for f in METRIC_FIELDS},
                )
            )
            created += 1
    deleted_raw = 0
    if rows:
        res = await session.execute(
            delete(MetricSample).where(MetricSample.resolution == RAW, MetricSample.ts < cutoff)
        )
        deleted_raw = res.rowcount or 0
    res = await session.execute(
        delete(MetricSample).where(
            MetricSample.resolution == ROLLUP,
            MetricSample.ts < now - timedelta(days=cfg.retention_rollup_days),
        )
    )
    deleted_rollup = res.rowcount or 0
    ev_cut = now - timedelta(days=cfg.retention_events_days)
    deleted_events = (await session.execute(delete(Event).where(Event.ts < ev_cut))).rowcount or 0
    deleted_alerts = (
        await session.execute(
            delete(Alert).where(Alert.status == "resolved", Alert.resolved_at < ev_cut)
        )
    ).rowcount or 0
    return {
        "rolled_up": created,
        "deleted_raw": deleted_raw,
        "deleted_rollup": deleted_rollup,
        "deleted_events": deleted_events,
        "deleted_alerts": deleted_alerts,
    }


async def history(
    session: AsyncSession, range_key: str, now: datetime | None = None
) -> HistoryResponse:
    window, bucket = RANGES[range_key]
    end = now or datetime.now(UTC)
    start = end - window
    rows = (
        (
            await session.execute(
                select(MetricSample)
                .where(MetricSample.ts >= start, MetricSample.ts <= end)
                .order_by(MetricSample.ts)
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[datetime, list[MetricSample]] = defaultdict(list)
    for r in rows:
        grouped[_floor(r.ts, bucket)].append(r)
    points = [
        HistoryPoint(ts=ts, **{f: _avg([getattr(g, f) for g in grp]) for f in METRIC_FIELDS})
        for ts, grp in sorted(grouped.items())
    ]
    return HistoryResponse(
        range=range_key, start=start, end=end, bucket_seconds=bucket, points=points
    )
