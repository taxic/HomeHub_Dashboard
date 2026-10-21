"""SSRF protection for outbound health checks.

Policy: homelab services legitimately live on private networks, so RFC1918/CGNAT (Tailscale)
/ULA ranges are allowed by default, but anything that is never a legitimate monitoring
target is refused: loopback (which would hit this API itself) unless explicitly enabled,
link-local (includes the 169.254.169.254 cloud-metadata endpoint), multicast, reserved and
unspecified addresses, and IPv4-mapped forms of those.

``resolve_target`` resolves the hostname *once* and returns the validated addresses so the
caller can connect to the pinned IP (defeating DNS rebinding between check and use).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

Address = ipaddress.IPv4Address | ipaddress.IPv6Address

_METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


class BlockedTargetError(ValueError):
    pass


class ResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    scheme: str
    host: str
    port: int
    ip: str  # validated, pinned address


def classify(addr: Address, *, allow_loopback: bool, allow_private: bool) -> str | None:
    """Return a reason string if the address must be blocked, else None."""
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if addr.is_unspecified:
        return "unspecified address"
    if addr.is_multicast:
        return "multicast address"
    if addr.is_link_local:
        return "link-local address (includes cloud metadata endpoints)"
    if addr.is_loopback:
        return None if allow_loopback else "loopback address"
    if str(addr) in ("169.254.169.254", "fd00:ec2::254", "100.100.100.200"):
        return "cloud metadata address"
    if addr.is_reserved:
        return "reserved address"
    if addr.is_private or (isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT):
        return None if allow_private else "private address"
    return None  # public addresses are allowed


_CGNAT = ipaddress.ip_network("100.64.0.0/10")


async def resolve_target(
    url: str, *, allow_loopback: bool = False, allow_private: bool = True
) -> Target:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BlockedTargetError("Only http and https URLs are allowed")
    host = parts.hostname
    if not host:
        raise BlockedTargetError("URL has no host")
    if parts.username or parts.password:
        raise BlockedTargetError("Credentials in URLs are not allowed")
    if host.lower().rstrip(".") in _METADATA_HOSTS:
        raise BlockedTargetError("Blocked hostname (cloud metadata)")
    port = parts.port or (443 if parts.scheme == "https" else 80)

    try:
        literal: Address | None = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        addrs: list[Address] = [literal]
    else:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ResolutionError(f"Could not resolve host '{host}'") from exc
        addrs = []
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if ip not in addrs:
                addrs.append(ip)
        if not addrs:
            raise ResolutionError(f"Could not resolve host '{host}'")

    # Every resolved address must be acceptable (an attacker-controlled name may return a mix).
    for addr in addrs:
        reason = classify(addr, allow_loopback=allow_loopback, allow_private=allow_private)
        if reason:
            raise BlockedTargetError(f"Target is not allowed: {reason}")
    chosen = next((a for a in addrs if a.version == 4), addrs[0])
    if isinstance(chosen, ipaddress.IPv6Address) and chosen.ipv4_mapped:
        chosen = chosen.ipv4_mapped
    return Target(parts.scheme, host, port, str(chosen))


def check_url_syntax_blocked(url: str, *, allow_loopback: bool, allow_private: bool) -> str | None:
    """Fast, synchronous save-time check for literal IPs/known-bad hostnames."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if host in _METADATA_HOSTS:
        return "Blocked hostname (cloud metadata)"
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return None
    reason = classify(addr, allow_loopback=allow_loopback, allow_private=allow_private)
    return f"Target is not allowed: {reason}" if reason else None
