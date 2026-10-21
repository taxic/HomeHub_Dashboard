"""In-process sliding-window failure counter used to throttle login attempts.

State is per-process and resets on restart; adequate for a single-instance homelab
deployment (documented limitation).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class FailureLimiter:
    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._events[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if not q:
            self._events.pop(key, None)
            return deque()
        return q

    def retry_after(self, *keys: str) -> int:
        """Seconds until the caller may retry (0 when allowed)."""
        now = time.monotonic()
        worst = 0.0
        for key in keys:
            q = self._prune(key, now)
            if len(q) >= self.max_failures:
                worst = max(worst, self.window - (now - q[0]))
        return int(worst) + 1 if worst > 0 else 0

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        for key in keys:
            self._prune(key, now)
            self._events[key].append(now)
        # Bound memory: drop stale keys occasionally.
        if len(self._events) > 10_000:
            for k in list(self._events):
                self._prune(k, now)

    def reset(self, *keys: str) -> None:
        for key in keys:
            self._events.pop(key, None)
