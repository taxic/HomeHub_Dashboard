"""Host metric collection. Everything optional degrades to ``None`` rather than failing."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psutil

from app.schemas.metrics import (
    DiskIOMetrics,
    HostMetrics,
    MemoryMetrics,
    NetworkMetrics,
    SwapMetrics,
    TemperatureReading,
    VolumeStatus,
)

log = logging.getLogger(__name__)

VIRTUAL_IFACE_PREFIXES = ("lo", "veth", "docker", "br-", "virbr", "tailscale", "tun", "tap", "wg")
VOLUME_TIMEOUT_SECONDS = 4.0


def _is_physical_iface(name: str) -> bool:
    return not name.startswith(VIRTUAL_IFACE_PREFIXES)


def parse_net_dev(text: str) -> dict[str, tuple[int, int]]:
    """Parse /proc/net/dev into ``{iface: (rx_bytes, tx_bytes)}``."""
    out: dict[str, tuple[int, int]] = {}
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        fields = rest.split()
        if len(fields) >= 9:
            out[name.strip()] = (int(fields[0]), int(fields[8]))
    return out


@dataclass
class _Prev:
    t: float
    rx: int
    tx: int
    read: int | None
    write: int | None


class HostCollector:
    def __init__(self, proc_path: str | None = None, sys_path: str | None = None) -> None:
        self.proc_path = proc_path
        self.sys_path = sys_path
        self._net_warned = False
        if proc_path:
            psutil.PROCFS_PATH = proc_path
        self._prev: _Prev | None = None
        psutil.cpu_percent(interval=None)  # prime; first call always returns 0.0
        self._hung: dict[str, float] = {}

    # ----- readers (each isolated so one failure cannot sink the sample) -----
    def _net_counters(self) -> dict[str, tuple[int, int]] | None:
        """Host NIC byte counters, or None when they cannot be read *for the host*.

        Inside a bridge-networked container ``/proc/net/dev`` describes the container's own
        namespace, which would be presented as host traffic. So when running containerised
        (``proc_path`` set) only host-scoped sources are accepted: a bind-mounted host
        ``/sys`` (privilege-free) or ``/proc/1/net/dev`` (needs ptrace rights).
        """
        if self.sys_path:
            base = Path(self.sys_path) / "class" / "net"
            try:
                out = {}
                for iface in base.iterdir():
                    stats = iface / "statistics"
                    out[iface.name] = (
                        int((stats / "rx_bytes").read_text()),
                        int((stats / "tx_bytes").read_text()),
                    )
                if out:
                    return out
            except (OSError, ValueError):
                log.debug("host sysfs network counters unreadable", exc_info=True)
        if self.proc_path:
            try:
                return parse_net_dev((Path(self.proc_path) / "1" / "net" / "dev").read_text())
            except OSError:
                if not self._net_warned:
                    self._net_warned = True
                    log.warning(
                        "Host network counters unavailable: mount the host /sys (read-only) and "
                        "set HOMELAB_HOST_SYS_PATH, or run the backend with host networking"
                    )
                return None
        try:
            return parse_net_dev(Path("/proc/net/dev").read_text())
        except OSError:
            pass
        try:
            return {
                k: (v.bytes_recv, v.bytes_sent)
                for k, v in psutil.net_io_counters(pernic=True).items()
            }
        except Exception:
            return None

    def _loadavg(self) -> list[float] | None:
        try:
            path = Path(self.proc_path or "/proc") / "loadavg"
            parts = path.read_text().split()
            return [float(parts[0]), float(parts[1]), float(parts[2])]
        except (OSError, ValueError, IndexError):
            try:
                return [round(x, 2) for x in os.getloadavg()]
            except OSError:
                return None

    def _temperatures(self) -> list[TemperatureReading]:
        readings: list[TemperatureReading] = []
        try:
            sensors = psutil.sensors_temperatures()  # missing on some platforms
        except (AttributeError, OSError):
            sensors = {}
        for chip, entries in sensors.items():
            for e in entries:
                if e.current is None or not (-50 < e.current < 200):
                    continue
                readings.append(
                    TemperatureReading(
                        label=f"{chip}:{e.label or 'temp'}",
                        current_c=round(e.current, 1),
                        high_c=e.high,
                        critical_c=e.critical,
                    )
                )
        if not readings:
            for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
                try:
                    val = int((zone / "temp").read_text().strip()) / 1000
                    kind = (zone / "type").read_text().strip()
                except (OSError, ValueError):
                    continue
                if -50 < val < 200:
                    readings.append(TemperatureReading(label=f"{kind}", current_c=round(val, 1)))
        return readings

    @staticmethod
    def pick_cpu_temperature(readings: list[TemperatureReading]) -> float | None:
        if not readings:
            return None
        preferred = ("coretemp", "k10temp", "cpu_thermal", "cpu", "x86_pkg_temp", "acpitz")
        for key in preferred:
            matches = [r for r in readings if key in r.label.lower()]
            if matches:
                package = [r for r in matches if "package" in r.label.lower()]
                return max((package or matches), key=lambda r: r.current_c).current_c
        return None  # don't guess: an unrelated sensor (NVMe, GPU) is not "CPU temperature"

    # ----- public API -----
    def collect(self) -> HostMetrics:
        now = time.monotonic()
        cpu = None
        try:
            cpu = psutil.cpu_percent(interval=None)
        except Exception:
            log.debug("cpu_percent failed", exc_info=True)

        memory = swap = None
        try:
            vm = psutil.virtual_memory()
            memory = MemoryMetrics(
                total_bytes=vm.total,
                used_bytes=vm.total - vm.available,
                available_bytes=vm.available,
                percent=round(vm.percent, 1),
            )
            sm = psutil.swap_memory()
            if sm.total > 0:
                swap = SwapMetrics(
                    total_bytes=sm.total, used_bytes=sm.used, percent=round(sm.percent, 1)
                )
        except Exception:
            log.debug("memory read failed", exc_info=True)

        uptime = None
        try:
            uptime = max(0.0, time.time() - psutil.boot_time())
        except Exception:
            log.debug("boot_time failed", exc_info=True)

        counters = self._net_counters()
        rx_tot = tx_tot = 0
        ifaces: list[str] = []
        if counters:
            for name, (rx, tx) in counters.items():
                if _is_physical_iface(name):
                    ifaces.append(name)
                    rx_tot += rx
                    tx_tot += tx
        io_read = io_write = None
        try:
            io = psutil.disk_io_counters()
            if io:
                io_read, io_write = io.read_bytes, io.write_bytes
        except Exception:
            log.debug("disk_io_counters failed", exc_info=True)

        rx_bps = tx_bps = r_bps = w_bps = None
        prev = self._prev
        if prev and now > prev.t:
            dt = now - prev.t
            if counters is not None and rx_tot >= prev.rx and tx_tot >= prev.tx:
                rx_bps, tx_bps = (rx_tot - prev.rx) / dt, (tx_tot - prev.tx) / dt
            if io_read is not None and prev.read is not None and io_read >= prev.read:
                r_bps = (io_read - prev.read) / dt
                w_bps = (io_write - prev.write) / dt  # type: ignore[operator]
        self._prev = _Prev(now, rx_tot, tx_tot, io_read, io_write)

        temps = self._temperatures()
        return HostMetrics(
            sampled_at=datetime.now(UTC),
            cpu_percent=cpu,
            cpu_count=psutil.cpu_count(logical=True),
            load_avg=self._loadavg(),
            memory=memory,
            swap=swap,
            uptime_seconds=uptime,
            temperature_c=self.pick_cpu_temperature(temps),
            temperatures=temps,
            network=(
                NetworkMetrics(
                    rx_bps=rx_bps,
                    tx_bps=tx_bps,
                    rx_total_bytes=rx_tot,
                    tx_total_bytes=tx_tot,
                    interfaces=sorted(ifaces),
                )
                if counters is not None
                else None
            ),
            disk_io=(
                DiskIOMetrics(read_bps=r_bps, write_bps=w_bps) if io_read is not None else None
            ),
        )

    # ----- storage -----
    async def check_volume(
        self,
        *,
        volume_id: int | None,
        name: str,
        path: str,
        kind: str,
        required: bool,
        require_mountpoint: bool,
        marker_file: str | None,
        root_path: str,
        enabled: bool = True,
    ) -> VolumeStatus:
        """Read-only inspection of a path. Never creates, mounts or writes anything.

        ``stat``/``statvfs`` on a dead USB-SATA bridge can block indefinitely in the kernel,
        so the work runs in a thread under a timeout; a path whose previous probe is still
        hung is reported as ``unresponsive`` without piling up more threads.
        """
        base = dict(id=volume_id, name=name, path=path, kind=kind, required=required)
        checked_at = datetime.now(UTC)
        if not enabled:
            return VolumeStatus(**base, state="disabled", checked_at=checked_at)
        hung_since = self._hung.get(path)
        if hung_since is not None:
            return VolumeStatus(
                **base,
                state="unresponsive",
                message="Filesystem is not responding (a previous probe is still blocked)",
                checked_at=checked_at,
            )
        loop = asyncio.get_running_loop()
        fut = loop.run_in_executor(
            None, probe_path, path, kind, require_mountpoint, marker_file, root_path
        )
        self._hung[path] = time.monotonic()
        try:
            res = await asyncio.wait_for(asyncio.shield(fut), VOLUME_TIMEOUT_SECONDS)
        except TimeoutError:
            fut.add_done_callback(lambda _f: self._hung.pop(path, None))
            return VolumeStatus(
                **base,
                state="unresponsive",
                message=f"No response within {VOLUME_TIMEOUT_SECONDS:.0f}s",
                checked_at=checked_at,
            )
        except Exception as exc:  # unexpected
            self._hung.pop(path, None)
            return VolumeStatus(
                **base, state="unreadable", message=type(exc).__name__, checked_at=checked_at
            )
        self._hung.pop(path, None)
        return VolumeStatus(**base, checked_at=checked_at, **res)


def probe_path(
    path: str, kind: str, require_mountpoint: bool, marker_file: str | None, root_path: str
) -> dict:
    """Blocking probe. Returns VolumeStatus keyword fields."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return {"state": "missing", "message": "Path does not exist"}
    except PermissionError:
        return {"state": "unreadable", "message": "Permission denied"}
    except OSError as exc:
        return {"state": "unreadable", "message": f"I/O error: {exc.strerror or exc.errno}"}
    if not os.path.isdir(path):
        return {"state": "missing", "message": "Path is not a directory"}

    problem = None
    if kind != "root":
        if require_mountpoint and not os.path.ismount(path):
            problem = "Path is not a mount point (disk may be unmounted)"
        elif kind == "external":
            try:
                if os.stat(root_path).st_dev == st.st_dev:
                    problem = (
                        "Path is on the same filesystem as the root (disk is probably not mounted)"
                    )
            except OSError:
                pass
        if marker_file and problem is None:
            try:
                if not os.path.exists(os.path.join(path, marker_file)):
                    problem = f"Marker file '{marker_file}' not found (wrong or missing disk)"
            except OSError:
                problem = "Could not check marker file"
    if problem:
        return {"state": "unmounted", "message": problem}
    try:
        u = os.statvfs(path)
    except OSError as exc:
        return {"state": "unreadable", "message": f"I/O error: {exc.strerror or exc.errno}"}
    total = u.f_blocks * u.f_frsize
    free = u.f_bavail * u.f_frsize
    used = (u.f_blocks - u.f_bfree) * u.f_frsize
    pct = round(used / (used + free) * 100, 1) if (used + free) > 0 else None
    return {
        "state": "ok",
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "percent": pct,
    }
