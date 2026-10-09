"""Local-network-only policy: never talk to the public Internet.

Allowed destinations are private, link-local, loopback, or shared (CGNAT)
addresses, plus local multicast used by SSDP. Everything else is rejected.
"""

from __future__ import annotations

import ipaddress
import socket


class NonLocalNetworkError(RuntimeError):
    """Raised when code would contact a non-local address."""


def es_host_local(host: str) -> bool:
    """True if *host* resolves only to local/private addresses."""
    host = (host or "").strip().strip("[]")
    if not host:
        return False
    if host in {"localhost", "255.255.255.255"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return _ip_local(ip)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError):
            return False
        if not _ip_local(ip):
            return False
    return True


def _ip_local(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_link_local or ip.is_loopback:
        return True
    # RFC 6598 CGNAT (100.64/10) — sometimes used on home gateways.
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
        return True
    # Local-use multicast (SSDP 239.255.255.250, etc.).
    if isinstance(ip, ipaddress.IPv4Address) and ip.is_multicast:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.is_multicast:
        # Link-local scope ff02::/16
        return (int(ip) >> 112) & 0xF == 0x2
    return False


def exigir_host_local(host: str, *, que: str = "network call") -> None:
    if not es_host_local(host):
        raise NonLocalNetworkError(
            f"Refusing {que} to non-local host {host!r}. "
            "This application only uses the LAN / Wi-Fi Direct."
        )
