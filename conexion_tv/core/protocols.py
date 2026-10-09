"""Static protocol catalog: what each one provides and what is needed to use it.

This is general knowledge, not observations of a specific device. What has been
verified against a real device lives in `device_memory`.

The separation matters: tips like "put the TV in Screen Mirroring mode" are the
same for any Samsung, and should not be duplicated in each device memory entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Protocol(str, Enum):
    """Protocol identifiers. The value is what gets persisted."""

    TIZEN_WEBSOCKET = "tizen_websocket"
    WAKE_ON_LAN = "wake_on_lan"
    DIAL = "dial"
    MIRACAST_WFD = "miracast_wfd"
    DLNA_AVTRANSPORT = "dlna_avtransport"
    AIRPLAY2 = "airplay2"
    GOOGLE_CAST = "google_cast"
    REMOTE_ACCESS_RDP = "remote_access_rdp"


class Purpose(str, Enum):
    """What a protocol is for. Determines which panel offers it."""

    PROJECTION = "projection"
    CONTROL = "control"
    POWER = "power"
    APP_LAUNCH = "app_launch"


@dataclass(frozen=True)
class ProtocolInfo:
    """Card for a protocol.

    `lleva_audio` and `latencia_ms` only apply to projection protocols; elsewhere
    they are None. `latencia_ms` is an expected (min, max) range.
    """

    id: Protocol
    nombre: str
    proposito: Purpose
    descripcion: str
    requisitos_dispositivo: tuple[str, ...] = ()
    requisitos_equipo: tuple[str, ...] = ()
    consejos_si_falla: tuple[str, ...] = ()
    lleva_audio: bool | None = None
    latencia_ms: tuple[int, int] | None = None
    disponible_en_linux: bool = True
    """Whether there is a way to use it from Linux, regardless of device support.
    AirPlay 2 is the case that forces the distinction: the TV supports it fine,
    but there is no Linux sender, so it should not be offered. That is our
    limitation, not the device's, which is why it lives here and not in device
    memory."""

    @property
    def es_proyeccion(self) -> bool:
        return self.proposito is Purpose.PROJECTION


CATALOGO: dict[Protocol, ProtocolInfo] = {
    Protocol.MIRACAST_WFD: ProtocolInfo(
        id=Protocol.MIRACAST_WFD,
        nombre="Miracast (Wi-Fi Display)",
        proposito=Purpose.PROJECTION,
        descripcion=(
            "True screen mirror with audio included, over a direct Wi-Fi link "
            "that does not go through the router."
        ),
        lleva_audio=True,
        latencia_ms=(150, 500),
        requisitos_dispositivo=(
            "On 2020 Samsung TU sets: Source → Remote Access → Screen Sharing. "
            "Do not pick Remote PC: that is RDP, not mirroring.",
            "Leave the TV on that screen, searching for devices, then press "
            "Share screen on the computer.",
            "Accept the connection request on the TV when it appears.",
        ),
        requisitos_equipo=(
            "The Wi-Fi adapter must support Wi-Fi Direct (P2P-GO and P2P-client "
            "modes).",
            "The network backend must be wpa_supplicant. With iwd, discovery "
            "returns nothing.",
            "Port 7236/tcp must be open in the firewall.",
            "ffmpeg and GStreamer plugins are needed to encode H.264.",
        ),
        consejos_si_falla=(
            "Check that the TV is on Screen Sharing (not Remote PC or Knox). "
            "Outside that mode it does not listen for Miracast.",
            "If no device appears, verify that iwd is stopped and "
            "wpa_supplicant is active.",
            "With a single antenna, the radio time-shares between the normal "
            "network and the direct link. Slower network traffic is expected.",
            "If it connects but the screen stays black, it is usually the H.264 "
            "profile negotiation: lower the resolution or framerate. This model "
            "accepted Constrained Baseline 720p30 and native 1080p60.",
            "If there is picture but no sound, pick in Screen the source that "
            "actually plays audio. On this model the HDMI monitor was heard.",
            "System audio goes through a virtual sink (remote display). "
            "«TV only» does not loop back to speakers; «Both» does.",
            "The ~7 s until the first frame is the RTSP handshake, not mirror "
            "latency. Steady-state delay is different (glass-to-glass not yet "
            "measured).",
        ),
    ),
    Protocol.DLNA_AVTRANSPORT: ProtocolInfo(
        id=Protocol.DLNA_AVTRANSPORT,
        nombre="DLNA / UPnP AVTransport",
        proposito=Purpose.PROJECTION,
        descripcion=(
            "The computer serves an HTTP stream and tells the TV to open it in "
            "its native player. It goes through the router, not Wi-Fi Direct, "
            "but latency is high."
        ),
        lleva_audio=True,
        latencia_ms=(5000, 20000),
        requisitos_dispositivo=(
            "The TV must advertise a MediaRenderer with the AVTransport "
            "service. Samsungs after 2020 often dropped it.",
        ),
        requisitos_equipo=(
            "The computer must be able to serve HTTP on the local network.",
            "The firewall must allow the streaming server port.",
        ),
        consejos_si_falla=(
            "If the TV accepts the command but does not play, try HLS transport "
            "instead of progressive MPEG-TS: on several Samsung models "
            "progressive freezes.",
            "The 5–20 second latency is inherent to the TV player's buffering. "
            "It is not suitable for interacting with the computer, only for "
            "watching content.",
            "Check that the computer and TV are on the same subnet: UPnP does "
            "not cross networks or VLANs.",
        ),
    ),
    Protocol.TIZEN_WEBSOCKET: ProtocolInfo(
        id=Protocol.TIZEN_WEBSOCKET,
        nombre="Tizen control over WebSocket",
        proposito=Purpose.CONTROL,
        descripcion=(
            "Samsung Tizen remote channel: keys, volume, inputs, and apps."
        ),
        requisitos_dispositivo=(
            "The TV must be on: when off it does not answer the channel.",
            "The first time it shows a permission dialog that must be accepted.",
        ),
        requisitos_equipo=(
            "Store the token the TV issues, or it will ask permission every time.",
            "Accept its self-signed TLS certificate.",
        ),
        consejos_si_falla=(
            "If the permission dialog does not appear, check on the TV: "
            "Settings > General > External Device Manager > Device Connection "
            "Manager > Access Notification.",
            "If it worked before and now does not, the TV may have revoked the "
            "token. Delete the saved token and pair again.",
            "Samsungs do not accept WebSocket connections from another subnet "
            "or VLAN. They must be on the same network.",
        ),
    ),
    Protocol.WAKE_ON_LAN: ProtocolInfo(
        id=Protocol.WAKE_ON_LAN,
        nombre="Wake-on-LAN",
        proposito=Purpose.POWER,
        descripcion=(
            "Turns the TV on with a magic packet. It is the only way to power "
            "it on, because the control channel only answers when it is on."
        ),
        requisitos_dispositivo=(
            "Enable on the TV: Settings > General > Network > Expert Settings > "
            "Power On with Mobile.",
            "On some models the option is called 'Power On with Mobile Device' "
            "or 'Wake on LAN / Wake on WLAN'.",
        ),
        requisitos_equipo=(
            "Know the TV MAC. Wi-Fi and Ethernet MACs differ: use the one for "
            "the interface it is connected on.",
        ),
        consejos_si_falla=(
            "The magic packet gives no reply: the only way to know it worked is "
            "to poll the TV after a few seconds.",
            "Over Wi-Fi it only works if the model supports WoWLAN and "
            "'Power On with Mobile' is enabled.",
            "If the TV is unplugged or in deep sleep, no packet will wake it.",
        ),
    ),
    Protocol.DIAL: ProtocolInfo(
        id=Protocol.DIAL,
        nombre="DIAL (launch apps)",
        proposito=Purpose.APP_LAUNCH,
        descripcion=(
            "Discovery and launch of TV apps by their identifier."
        ),
        requisitos_dispositivo=(
            "The app you want to launch must be installed.",
        ),
        consejos_si_falla=(
            "On 2020 Samsung TU sets the WebSocket app list does not respond. "
            "DIAL is the alternative, but you need to know the app identifiers.",
        ),
    ),
    Protocol.AIRPLAY2: ProtocolInfo(
        id=Protocol.AIRPLAY2,
        nombre="AirPlay 2",
        proposito=Purpose.PROJECTION,
        descripcion=(
            "Samsungs from 2019 onward are AirPlay 2 receivers, but there is "
            "no working AirPlay sender for Linux."
        ),
        lleva_audio=True,
        disponible_en_linux=False,
        requisitos_equipo=(
            "An AirPlay sender for Linux, which does not exist today.",
        ),
        consejos_si_falla=(
            "This is not a configuration problem: the Linux sender is missing. "
            "uxplay does the opposite — it turns Linux into a receiver.",
        ),
    ),
    Protocol.GOOGLE_CAST: ProtocolInfo(
        id=Protocol.GOOGLE_CAST,
        nombre="Google Cast",
        proposito=Purpose.PROJECTION,
        descripcion=(
            "Chromecast protocol. Tizen Samsungs do not ship it built-in."
        ),
        lleva_audio=True,
        consejos_si_falla=(
            "On a Tizen Samsung there is nothing to configure: support does not "
            "exist on the device and will never appear in the list.",
        ),
    ),
    Protocol.REMOTE_ACCESS_RDP: ProtocolInfo(
        id=Protocol.REMOTE_ACCESS_RDP,
        nombre="Samsung Remote Access (RDP)",
        proposito=Purpose.PROJECTION,
        descripcion=(
            "The TV acts as an RDP client and connects to the computer. It is "
            "not mirroring but a remote session, and the TV initiates the "
            "connection."
        ),
        lleva_audio=None,
        requisitos_dispositivo=(
            "On the TV go to Source > Remote Access > Remote PC and enter the "
            "computer IP, username, and password by hand.",
            "A keyboard and mouse connected to the TV are required.",
        ),
        requisitos_equipo=(
            "An RDP server on the computer, for example xrdp.",
            "Disable system sleep.",
        ),
        consejos_si_falla=(
            "Samsung only documents Windows and macOS, and explicitly says "
            "Linux is unsupported. Working against xrdp is not guaranteed.",
            "You will see a new desktop, not the one in front of you on the "
            "monitor.",
            "Audio depends on the TV client negotiating the rdpsnd channel, "
            "which is unverified.",
        ),
    ),
}


def info(protocolo: Protocol) -> ProtocolInfo:
    """Card for a protocol."""
    return CATALOGO[protocolo]


def por_proposito(proposito: Purpose) -> list[ProtocolInfo]:
    """Protocols that serve a purpose, in catalog order."""
    return [p for p in CATALOGO.values() if p.proposito is proposito]
