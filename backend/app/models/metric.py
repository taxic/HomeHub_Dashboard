from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UTCDateTime


class MetricSample(Base):
    """One wide row per sampling interval. ``resolution`` is bucket size in seconds
    (60 = raw, 300 = rolled-up). NULL means the metric was unavailable, not zero."""

    __tablename__ = "metric_samples"
    __table_args__ = (Index("uq_metric_samples_ts_res", "ts", "resolution", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime)
    resolution: Mapped[int] = mapped_column(Integer, default=60)
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    mem_percent: Mapped[float | None] = mapped_column(Float)
    swap_percent: Mapped[float | None] = mapped_column(Float)
    load1: Mapped[float | None] = mapped_column(Float)
    disk_root_percent: Mapped[float | None] = mapped_column(Float)
    storage_max_percent: Mapped[float | None] = mapped_column(Float)
    net_rx_bps: Mapped[float | None] = mapped_column(Float)
    net_tx_bps: Mapped[float | None] = mapped_column(Float)
    temp_c: Mapped[float | None] = mapped_column(Float)


METRIC_FIELDS = (
    "cpu_percent",
    "mem_percent",
    "swap_percent",
    "load1",
    "disk_root_percent",
    "storage_max_percent",
    "net_rx_bps",
    "net_tx_bps",
    "temp_c",
)
