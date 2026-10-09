"""Projection contract. Independent of TV control.

Defined *before* any adapter so FluxCast does not pollute the vocabulary.
A second backend (DLNA) has a radically different operating model: if this
interface only fits Miracast, it is wrong.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from collections.abc import Callable

from conexion_tv.core.device_memory import DeviceRecord
from conexion_tv.core.events import AppEvent


@dataclass(frozen=True)
class LinkFacts:
    """Facts about the live session. The GUI shows them; they are not settings."""

    interface: str = ""
    local_ip: str = ""
    tv_ip: str = ""
    mode: str = ""
    rtp: str = ""
    session_id: str = ""
    advertised_video: str = ""
    advertised_audio: str = ""
    hdcp: str = ""


@dataclass(frozen=True)
class StreamConfig:
    """Quality request. The backend may lower it if the sink cannot keep up.

    Names belong to the application vocabulary, not a backend.
    `captura`: x11 | portal | auto | gstreamer.
    `p2p_backend`: nm | wpas.
    `media_pipeline`: auto | ffmpeg | gst.
    `go_intent`: None does not force the flag; 0 = TV is GO; 15 = PC is GO.
    `p2p_channel`: None = driver; 1/6/11 = 2.4 GHz; 36/40/44/48 = 5 GHz;
    -1 = prefer the associated AP's 5 GHz channel (see `p2p_channel.MATCH_AP_5GHZ`).
    """

    ancho: int = 1280
    alto: int = 720
    fps: int = 30
    bitrate_kbps: int = 4000  # video bitrate; practical cap 16000 (20000 did not connect)
    audio: bool = True
    mute_local: bool = False  # True → audio_route "tv" (virtual bus, no loopback)
    audio_device: str | None = None
    monitor: str | None = None
    captura: str = "x11"
    gestionar_firewall: bool = True
    entrada_remota: bool = False
    go_intent: int | None = None
    rtsp_port: int = 7236
    rtp_source_port: int = 19002
    scan_timeout_s: int = 8
    p2p_backend: str = "nm"
    p2p_channel: int | None = None
    media_pipeline: str = "auto"
    wifi_interface: str | None = None
    test_pattern: bool = False


@dataclass(frozen=True)
class BackendCapabilities:
    id: str
    nombre: str
    audio: bool
    necesita_wifi_direct: bool
    latencia_ms: tuple[int, int] | None
    descripcion: str


class ScreenMirroring(ABC):
    """Swappable projection backend."""

    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        """What this backend offers, independent of the device."""

    @abstractmethod
    def is_available(self, registro: DeviceRecord) -> tuple[bool, str]:
        """Whether it can work now, on this machine and with this set.

        The second value is the discard reason, empty if available.
        """

    @abstractmethod
    def connect(self, registro: DeviceRecord, config: StreamConfig | None = None) -> None:
        """Establish the transport link without streaming yet."""

    @abstractmethod
    def start_stream(self, config: StreamConfig) -> None:
        """Start emission."""

    @abstractmethod
    def stop_stream(self) -> None:
        """Stop emission while leaving the link up."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the link and free child processes, P2P interfaces, and firewall rules."""

    def set_event_handler(self, handler: Callable[[AppEvent], None] | None) -> None:
        self._event_handler = handler

    def esta_activo(self) -> bool:
        """True if a streaming process is alive."""
        return False

    def detalle_sesion(self) -> str:
        """Recent progress in application language, for the GUI."""
        return ""

    def _emit(self, evento: AppEvent) -> None:
        handler = getattr(self, "_event_handler", None)
        if handler is not None:
            handler(evento)
