from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Notification:
    kind: str  # "opened" | "escalated" | "reminder" | "resolved" | "test"
    severity: str  # warning | critical | info
    title: str
    message: str


class Notifier(Protocol):
    name: str

    def configured(self) -> bool: ...
    async def send(self, notification: Notification) -> None: ...
