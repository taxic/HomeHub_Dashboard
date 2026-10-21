"""Test doubles. FakeDocker never talks to a real daemon."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from app.monitoring.docker_gateway import (
    ContainerNotFoundError,
    DockerUnavailableError,
    RawContainer,
)


def make_container(
    name: str, state: str = "running", health: str = "none", cid: str | None = None, **kw
):
    cid = cid or (name.encode().hex() * 8)[:64].ljust(64, "a")
    return RawContainer(
        id=cid,
        name=name,
        image=f"{name}:latest",
        state=state,
        status_text=state,
        health=health,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        started_at=datetime(2025, 1, 2, tzinfo=UTC) if state == "running" else None,
        restart_count=0,
        **kw,
    )


class FakeDocker:
    def __init__(self, containers: list[RawContainer] | None = None) -> None:
        self.containers = {c.id: c for c in (containers or [])}
        self.calls: list[tuple[str, str]] = []
        self.down = False
        self.fail_action: Exception | None = None
        self.gone: set[str] = set()  # ids that vanish between discovery and action
        self.log_lines = ["2025-01-01T00:00:00Z hello", "2025-01-01T00:00:01Z world"]

    def _check(self):
        if self.down:
            raise DockerUnavailableError("socket refused")

    async def list_containers(self):
        self._check()
        return [copy.copy(c) for c in self.containers.values()]

    async def get_stats(self, container_id):
        self._check()
        return {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200},
                "system_cpu_usage": 2000,
                "online_cpus": 2,
            },
            "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
            "memory_stats": {"usage": 300, "limit": 1000, "stats": {"inactive_file": 100}},
        }

    async def logs(self, container_id, tail, max_bytes):
        self._check()
        self.calls.append(("logs", container_id))
        if container_id not in self.containers:
            raise ContainerNotFoundError(container_id)
        return self.log_lines[-tail:], False

    async def perform(self, container_id, action):
        self._check()
        self.calls.append((action, container_id))
        if self.fail_action:
            raise self.fail_action
        if container_id in self.gone or container_id not in self.containers:
            raise ContainerNotFoundError(container_id)
        c = self.containers[container_id]
        c.state = "exited" if action == "stop" else "running"
        c.status_text = c.state
        return copy.copy(c)

    def actions(self):
        return [c for c in self.calls if c[0] in ("start", "stop", "restart")]
