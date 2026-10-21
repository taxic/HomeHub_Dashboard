from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

VolumeState = Literal["ok", "missing", "unmounted", "unreadable", "unresponsive", "disabled"]
HostStatus = Literal["healthy", "warning", "critical", "unknown"]


class MemoryMetrics(BaseModel):
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent: float


class SwapMetrics(BaseModel):
    total_bytes: int
    used_bytes: int
    percent: float


class TemperatureReading(BaseModel):
    label: str
    current_c: float
    high_c: float | None = None
    critical_c: float | None = None


class NetworkMetrics(BaseModel):
    # rates are null for the very first sample (no previous counter to diff against)
    rx_bps: float | None
    tx_bps: float | None
    rx_total_bytes: int
    tx_total_bytes: int
    interfaces: list[str]


class DiskIOMetrics(BaseModel):
    read_bps: float | None
    write_bps: float | None


class HostMetrics(BaseModel):
    """Every optional value is ``null`` when *unavailable*; 0 means a measured zero."""

    sampled_at: datetime
    cpu_percent: float | None
    cpu_count: int | None
    load_avg: list[float] | None
    memory: MemoryMetrics | None
    swap: SwapMetrics | None
    uptime_seconds: float | None
    temperature_c: float | None
    temperatures: list[TemperatureReading]
    network: NetworkMetrics | None
    disk_io: DiskIOMetrics | None


class VolumeStatus(BaseModel):
    id: int | None  # null for the implicit root filesystem
    name: str
    path: str
    kind: Literal["root", "data", "external"]
    required: bool
    state: VolumeState
    message: str | None = None
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    percent: float | None = None
    checked_at: datetime


class StorageResponse(BaseModel):
    root: VolumeStatus | None
    volumes: list[VolumeStatus]
    disk_io: DiskIOMetrics | None
    sampled_at: datetime | None


class CurrentMetrics(BaseModel):
    available: bool  # false until the first host sample exists
    host: HostMetrics | None
    sampled_at: datetime | None
    stale: bool = False


class HistoryPoint(BaseModel):
    ts: datetime
    cpu_percent: float | None = None
    mem_percent: float | None = None
    swap_percent: float | None = None
    load1: float | None = None
    disk_root_percent: float | None = None
    storage_max_percent: float | None = None
    net_rx_bps: float | None = None
    net_tx_bps: float | None = None
    temp_c: float | None = None


class HistoryResponse(BaseModel):
    range: str
    start: datetime
    end: datetime
    bucket_seconds: int
    points: list[HistoryPoint]
