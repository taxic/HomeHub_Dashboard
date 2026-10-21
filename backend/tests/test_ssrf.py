import ipaddress
import socket

import pytest

from app.monitoring import ssrf


@pytest.mark.parametrize(
    "ip",
    [
        "169.254.169.254",
        "169.254.1.1",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "224.0.0.1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "fd00:ec2::254",
        "240.0.0.1",
        "100.100.100.200",
    ],
)
def test_always_blocked(ip):
    assert ssrf.classify(ipaddress.ip_address(ip), allow_loopback=False, allow_private=True)


@pytest.mark.parametrize(
    "ip", ["192.168.1.10", "10.0.0.5", "172.16.3.4", "100.64.1.2", "fd12::1", "8.8.8.8"]
)
def test_lan_and_public_allowed_by_default(ip):
    assert ssrf.classify(ipaddress.ip_address(ip), allow_loopback=False, allow_private=True) is None


def test_private_can_be_disabled_and_loopback_enabled():
    assert ssrf.classify(
        ipaddress.ip_address("10.0.0.1"), allow_loopback=False, allow_private=False
    )
    assert (
        ssrf.classify(ipaddress.ip_address("127.0.0.1"), allow_loopback=True, allow_private=True)
        is None
    )
    # metadata stays blocked even with loopback allowed
    assert ssrf.classify(
        ipaddress.ip_address("169.254.169.254"), allow_loopback=True, allow_private=True
    )


async def test_resolve_literal_and_scheme_rules():
    t = await ssrf.resolve_target("http://192.168.1.5:8080/health")
    assert (t.ip, t.port, t.scheme) == ("192.168.1.5", 8080, "http")
    for bad in [
        "ftp://192.168.1.5",
        "file:///etc/passwd",
        "gopher://x",
        "http://user:pw@192.168.1.5/",
    ]:
        with pytest.raises(ssrf.BlockedTargetError):
            await ssrf.resolve_target(bad)


async def test_blocks_metadata_and_loopback_names(monkeypatch):
    for url in [
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/",
        "http://[::1]/",
        "http://127.1/",
        "http://2130706433/",
    ]:
        with pytest.raises((ssrf.BlockedTargetError, ssrf.ResolutionError)):
            await ssrf.resolve_target(url)


async def test_dns_rebinding_mixed_answers_blocked(monkeypatch):
    async def fake_getaddrinfo(self, host, port, **kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.9", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port)),
        ]

    import asyncio

    monkeypatch.setattr(asyncio.get_running_loop().__class__, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ssrf.BlockedTargetError):
        await ssrf.resolve_target("http://evil.example/")


async def test_dns_failure_is_resolution_error():
    with pytest.raises(ssrf.ResolutionError):
        await ssrf.resolve_target("http://definitely-not-a-real-host.invalid/")


def test_save_time_check():
    assert ssrf.check_url_syntax_blocked(
        "http://169.254.169.254/", allow_loopback=False, allow_private=True
    )
    assert (
        ssrf.check_url_syntax_blocked(
            "http://localhost-name/", allow_loopback=False, allow_private=True
        )
        is None
    )
