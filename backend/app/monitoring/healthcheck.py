"""HTTP(S) health checks with SSRF-pinned connections, timeouts and bounded retries."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.monitoring.ssrf import BlockedTargetError, ResolutionError, resolve_target
from app.schemas.service import parse_status_spec

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # one retry
BACKOFF_SECONDS = 0.5


@dataclass
class CheckResult:
    ok: bool
    status_code: int | None
    response_ms: float | None
    error: str | None


def status_ok(code: int, spec: str) -> bool:
    return any(lo <= code <= hi for lo, hi in parse_status_spec(spec))


class HealthChecker:
    def __init__(
        self,
        *,
        allow_loopback: bool = False,
        allow_private: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.allow_loopback = allow_loopback
        self.allow_private = allow_private
        self._transport = transport  # injected in tests

    async def check(
        self,
        url: str,
        *,
        expected_status: str = "200-399",
        timeout: float = 5.0,
        verify_tls: bool = True,
        attempts: int = MAX_ATTEMPTS,
    ) -> CheckResult:
        last = CheckResult(False, None, None, "not checked")
        for attempt in range(attempts):
            last = await self._once(url, expected_status, timeout, verify_tls)
            # Never retry policy failures; a blocked target will not become allowed.
            if last.ok or (last.error or "").startswith("Blocked"):
                return last
            if attempt + 1 < attempts:
                await asyncio.sleep(BACKOFF_SECONDS * (2**attempt))
        return last

    async def _once(self, url: str, expected: str, timeout: float, verify: bool) -> CheckResult:
        started = time.perf_counter()
        try:
            target = await resolve_target(
                url, allow_loopback=self.allow_loopback, allow_private=self.allow_private
            )
        except BlockedTargetError as exc:
            return CheckResult(False, None, None, f"Blocked: {exc}")
        except ResolutionError as exc:
            return CheckResult(False, None, None, str(exc))

        parts = urlsplit(url)
        # Connect to the pinned, validated IP; keep Host/SNI as the original name.
        ip_host = f"[{target.ip}]" if ":" in target.ip else target.ip
        netloc = f"{ip_host}:{target.port}"
        pinned = parts._replace(netloc=netloc).geturl()
        headers = {
            "Host": parts.netloc.rsplit("@", 1)[-1],
            "User-Agent": "HomeLab-Command-Centre/1.0",
        }
        extensions = {"sni_hostname": target.host} if parts.scheme == "https" else {}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=False,  # a redirect could point at a forbidden address
                verify=verify,
                transport=self._transport,
            ) as client:
                resp = await client.get(pinned, headers=headers, extensions=extensions)
        except httpx.TimeoutException:
            return CheckResult(False, None, None, f"Timed out after {timeout:g}s")
        except httpx.ConnectError as exc:
            return CheckResult(False, None, None, _short(f"Connection failed: {exc}"))
        except httpx.HTTPError as exc:
            return CheckResult(False, None, None, _short(f"{type(exc).__name__}: {exc}"))
        except Exception as exc:  # never let a check crash the scheduler
            log.warning("health check crashed: %s", type(exc).__name__)
            return CheckResult(False, None, None, f"Check error: {type(exc).__name__}")
        elapsed = (time.perf_counter() - started) * 1000
        if status_ok(resp.status_code, expected):
            return CheckResult(True, resp.status_code, round(elapsed, 1), None)
        return CheckResult(
            False, resp.status_code, round(elapsed, 1), f"Unexpected HTTP status {resp.status_code}"
        )


def _short(msg: str) -> str:
    return msg.replace("\n", " ")[:300]
