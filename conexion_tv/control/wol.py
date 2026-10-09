"""Wake-on-LAN. Powering on the TV is the only path when the WebSocket does not answer.

Magic packets stay on the LAN broadcast; never targeted at a public host.
"""

from __future__ import annotations

from wakeonlan import send_magic_packet

from conexion_tv.core.net_policy import exigir_host_local


def wake(mac: str, *, broadcast: str = "255.255.255.255") -> None:
    """Send a magic packet. There is no reply: poll afterwards."""
    exigir_host_local(broadcast, que="Wake-on-LAN broadcast")
    send_magic_packet(mac, ip_address=broadcast)
