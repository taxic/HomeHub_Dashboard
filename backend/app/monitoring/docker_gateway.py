"""Restricted Docker integration.

Only the operations the product needs are exposed: list, inspect, stats, bounded logs,
and start/stop/restart. There is deliberately no exec, create, remove, prune, volume,
image or network operation, and callers never pass free-form Docker arguments.

The Docker SDK is synchronous, so every call is dispatched with ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

log = logging.getLogger(__name__)

CONTAINER_ID_RE = re.compile(r"^[a-f0-9]{12,64}$")


class DockerUnavailableError(Exception):
    """Docker daemon/proxy unreachable or refused the request."""


class ContainerNotFoundError(Exception):
    pass


@dataclass
class RawContainer:
    id: str
    name: str
    image: str
    state: str
    status_text: str
    health: str = "none"
    created_at: datetime | None = None
    started_at: datetime | None = None
    restart_count: int | None = None
    cpu_percent: float | None = None
    memory_bytes: int | None = None
    memory_limit_bytes: int | None = None
    labels: dict[str, str] = field(default_factory=dict)


class DockerGateway(Protocol):
    async def list_containers(self) -> list[RawContainer]: ...
    async def get_stats(self, container_id: str) -> dict | None: ...
    async def logs(
        self, container_id: str, tail: int, max_bytes: int
    ) -> tuple[list[str], bool]: ...
    async def perform(self, container_id: str, action: str) -> RawContainer: ...


def _parse_ts(value: str | None) -> datetime | None:
    if not value or value.startswith("0001-01-01"):
        return None
    try:
        # Docker emits nanosecond precision; trim to microseconds.
        value = re.sub(r"(\.\d{6})\d*", r"\1", value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        return None


def parse_health(status_text: str, inspect_health: str | None) -> str:
    if inspect_health in ("healthy", "unhealthy", "starting"):
        return inspect_health
    low = status_text.lower()
    if "(unhealthy)" in low:
        return "unhealthy"
    if "(healthy)" in low:
        return "healthy"
    if "health: starting" in low:
        return "starting"
    return "none"


def compute_cpu_percent(stats: dict) -> float | None:
    try:
        cpu = stats["cpu_stats"]
        pre = stats["precpu_stats"]
        cpu_delta = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
        sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
        online = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage") or []) or 1
        if sys_delta > 0 and cpu_delta >= 0:
            return round(cpu_delta / sys_delta * online * 100.0, 1)
    except (KeyError, TypeError):
        pass
    return None


def compute_memory(stats: dict) -> tuple[int | None, int | None]:
    try:
        mem = stats["memory_stats"]
        usage = mem["usage"]
        s = mem.get("stats", {})
        usage -= s.get("inactive_file", s.get("total_inactive_file", s.get("cache", 0)))
        return max(0, usage), mem.get("limit")
    except (KeyError, TypeError):
        return None, None


class SDKDockerGateway:
    def __init__(self, host: str | None = None, timeout: int = 10) -> None:
        self._host = host
        self._timeout = timeout
        self._client = None

    def _get(self):
        import docker

        if self._client is None:
            kwargs = {"timeout": self._timeout}
            self._client = (
                docker.DockerClient(base_url=self._host, **kwargs)
                if self._host
                else docker.from_env(**kwargs)
            )
        return self._client

    def _wrap(self, fn, *args):
        import docker.errors as de

        try:
            return fn(*args)
        except de.NotFound as exc:
            raise ContainerNotFoundError(str(exc)) from exc
        except (de.DockerException, OSError) as exc:
            self._client = None  # force reconnect next time
            raise DockerUnavailableError(f"{type(exc).__name__}: {str(exc)[:200]}") from exc

    # ---- blocking implementations ----
    def _raw(self, c) -> RawContainer:
        attrs = c.attrs
        state = attrs.get("State", {}) or {}
        health = (state.get("Health") or {}).get("Status")
        cfg = attrs.get("Config", {}) or {}
        status_text = state.get("Status", "unknown")
        if state.get("Running") and health:
            status_text = f"{status_text} ({health})"
        return RawContainer(
            id=attrs.get("Id", c.id),
            name=(attrs.get("Name") or c.name or "").lstrip("/"),
            image=cfg.get("Image") or str(c.image.tags[0] if c.image and c.image.tags else ""),
            state=state.get("Status", "unknown"),
            status_text=status_text,
            health=parse_health(status_text, health),
            created_at=_parse_ts(attrs.get("Created")),
            started_at=_parse_ts(state.get("StartedAt")) if state.get("Running") else None,
            restart_count=attrs.get("RestartCount"),
            labels=cfg.get("Labels") or {},
        )

    def _list(self) -> list[RawContainer]:
        client = self._get()
        out = []
        for c in client.containers.list(all=True, limit=200):
            try:
                c.reload()  # full inspect: health, start time, restart count
            except Exception:
                log.debug("inspect failed for a container", exc_info=True)
            out.append(self._raw(c))
        return out

    def _stats(self, container_id: str) -> dict | None:
        return self._get().containers.get(container_id).stats(stream=False)

    def _logs(self, container_id: str, tail: int, max_bytes: int) -> tuple[list[str], bool]:
        raw = self._get().containers.get(container_id).logs(tail=tail, timestamps=True)
        truncated = len(raw) > max_bytes
        if truncated:
            raw = raw[-max_bytes:]
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if truncated and lines:
            lines = lines[1:]  # first line may be cut mid-way
        return lines, truncated

    def _perform(self, container_id: str, action: str) -> RawContainer:
        c = self._get().containers.get(container_id)
        if action == "start":
            c.start()
        elif action == "stop":
            c.stop(timeout=15)
        elif action == "restart":
            c.restart(timeout=15)
        else:  # pragma: no cover - guarded by callers
            raise ValueError("unsupported action")
        c.reload()
        return self._raw(c)

    # ---- async facade ----
    async def list_containers(self) -> list[RawContainer]:
        return await asyncio.to_thread(self._wrap, self._list)

    async def get_stats(self, container_id: str) -> dict | None:
        return await asyncio.to_thread(self._wrap, self._stats, container_id)

    async def logs(self, container_id: str, tail: int, max_bytes: int) -> tuple[list[str], bool]:
        return await asyncio.to_thread(self._wrap, self._logs, container_id, tail, max_bytes)

    async def perform(self, container_id: str, action: str) -> RawContainer:
        return await asyncio.to_thread(self._wrap, self._perform, container_id, action)
