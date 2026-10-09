"""Remote display: the TV as a surface with its own video, audio, and settings.

Today video is still capture of the local monitor (mirror). Audio already goes
through a virtual bus (`VirtualAudioBus`). When extended desktop exists,
the `monitor` field / a virtual output will live here without mixing with the PC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from conexion_tv.mirror.base import StreamConfig
from conexion_tv.mirror.virtual_audio import VirtualAudioBus

AudioRoute = Literal["tv", "both", "pc"]


@dataclass(frozen=True)
class RemoteDisplay:
    """What the TV should show and hear.

    Independent of the local desktop: same protocol bits, different role.
    """

    ancho: int = 1280
    alto: int = 720
    fps: int = 30
    bitrate_kbps: int = 4000
    audio_route: AudioRoute = "both"
    # Current video capture (mirror). Later: virtual output.
    monitor: str | None = None
    captura: str = "x11"
    audio_device: str | None = None  # override manual; si None, el runtime decide

    @classmethod
    def from_stream_config(cls, cfg: StreamConfig) -> RemoteDisplay:
        return cls(
            ancho=cfg.ancho,
            alto=cfg.alto,
            fps=cfg.fps,
            bitrate_kbps=cfg.bitrate_kbps,
            audio_route=ruta_desde_flags(cfg.audio, cfg.mute_local),
            monitor=cfg.monitor,
            captura=cfg.captura,
            audio_device=cfg.audio_device,
        )

    def envia_audio(self) -> bool:
        return self.audio_route != "pc"

    def altavoces_pc(self) -> bool:
        return self.audio_route == "both"


def ruta_desde_flags(audio: bool, mute_local: bool) -> AudioRoute:
    if not audio:
        return "pc"
    if mute_local:
        return "tv"
    return "both"


def flags_desde_ruta(ruta: AudioRoute) -> tuple[bool, bool]:
    """Compatibility with StreamConfig.audio / mute_local."""
    if ruta == "pc":
        return False, False
    if ruta == "tv":
        return True, True
    return True, False


# Aliases used by the GUI (formerly in audio_local).
def destino_desde_config(*, audio: bool, mute_local: bool) -> str:
    return ruta_desde_flags(audio, mute_local)


def audio_y_silencio(destino: str) -> tuple[bool, bool]:
    if destino not in ("tv", "both", "pc"):
        destino = "both"
    return flags_desde_ruta(destino)  # type: ignore[arg-type]


class RemoteDisplayRuntime:
    """Live state of the remote surface (today: virtual audio bus)."""

    def __init__(self) -> None:
        self._bus = VirtualAudioBus()
        self._ruta: AudioRoute | None = None

    @property
    def ruta(self) -> AudioRoute | None:
        return self._ruta

    def apply_audio(self, ruta: AudioRoute) -> bool:
        """Mount or tear down the bus for the route. True if coherent."""
        if ruta == "pc":
            self._bus.close()
            self._ruta = "pc"
            return True
        if not self._bus.open():
            self._ruta = None
            return False
        if not self._bus.set_speakers(ruta == "both"):
            # Null sink ok but no loopback: at least «TV only» works.
            if ruta == "both":
                self._ruta = "tv"
                return False
        self._ruta = ruta
        return True

    def pulse_capture_device(self, preferido: str | None = None) -> str | None:
        """Pulse source FluxCast should read."""
        if self._ruta in ("tv", "both"):
            return self._bus.monitor or preferido
        return preferido

    def close(self) -> None:
        self._bus.close()
        self._ruta = None
