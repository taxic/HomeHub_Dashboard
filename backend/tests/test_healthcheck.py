import httpx
import pytest

from app.monitoring import healthcheck
from app.monitoring.healthcheck import HealthChecker, status_ok


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr(healthcheck, "BACKOFF_SECONDS", 0)


def checker(handler):
    return HealthChecker(transport=httpx.MockTransport(handler))


async def test_success_records_status_and_latency():
    r = await checker(lambda req: httpx.Response(200)).check("http://192.168.1.5:32400/web")
    assert r.ok and r.status_code == 200 and r.response_ms is not None and r.error is None


async def test_unexpected_status_fails_with_reason():
    r = await checker(lambda req: httpx.Response(503)).check("http://192.168.1.5/", attempts=1)
    assert not r.ok and r.status_code == 503 and "503" in r.error


async def test_custom_expected_status():
    r = await checker(lambda req: httpx.Response(401)).check(
        "http://192.168.1.5/", expected_status="200,401"
    )
    assert r.ok


async def test_timeout_reported_and_retried_once():
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=req)

    r = await checker(handler).check("http://192.168.1.5/", timeout=1)
    assert not r.ok and "Timed out" in r.error and len(calls) == 2


async def test_retry_recovers_from_transient_failure():
    seq = iter([httpx.ConnectError("boom"), httpx.Response(200)])

    def handler(req):
        item = next(seq)
        if isinstance(item, Exception):
            raise item
        return item

    assert (await checker(handler).check("http://192.168.1.5/")).ok


async def test_blocked_target_never_requested_or_retried():
    calls = []
    c = checker(lambda req: calls.append(1) or httpx.Response(200))
    r = await c.check("http://169.254.169.254/latest/meta-data/")
    assert not r.ok and r.error.startswith("Blocked") and calls == []


async def test_redirects_are_not_followed():
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    r = await checker(handler).check("http://192.168.1.5/", expected_status="200", attempts=1)
    assert not r.ok and len(seen) == 1


async def test_connects_to_pinned_ip_and_keeps_host_header(monkeypatch):
    import asyncio
    import socket

    async def fake(self, host, port, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.77", port))]

    monkeypatch.setattr(asyncio.get_running_loop().__class__, "getaddrinfo", fake)
    seen = {}

    def handler(req):
        seen["url"], seen["host"] = str(req.url), req.headers["host"]
        return httpx.Response(200)

    await checker(handler).check("http://plex.lan:32400/web")
    assert seen["url"].startswith("http://192.168.1.77:32400") and seen["host"] == "plex.lan:32400"


@pytest.mark.parametrize(
    "code,spec,ok",
    [
        (200, "200-399", True),
        (404, "200-399", False),
        (301, "200,301", True),
        (500, "200-299,500", True),
    ],
)
def test_status_ok(code, spec, ok):
    assert status_ok(code, spec) is ok
