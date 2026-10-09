"""Miracast video modes the UI can request.

These are CEA / Wi-Fi Display 1.0 protocol knowledge, not device-specific.
The backend may negotiate a lower mode if the TV cannot reach the request.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoMode:
    id: str
    etiqueta: str
    ancho: int
    alto: int
    fps: int
    bitrate_sugerido_kbps: int
    explicacion: str


# The four HD modes Samsung Tizen 5.5 sets usually advertise, plus a VGA
# rescue. Order is from most conservative to most demanding.
MODOS_VIDEO: tuple[VideoMode, ...] = (
    VideoMode(
        id="720p30",
        etiqueta="1280 × 720 at 30 fps",
        ancho=1280,
        alto=720,
        fps=30,
        bitrate_sugerido_kbps=4000,
        explicacion=(
            "Working mode: less Wi-Fi Direct and CPU load. On a 4K TV it looks "
            "softer, but it is the one already proven end to end."
        ),
    ),
    VideoMode(
        id="720p60",
        etiqueta="1280 × 720 at 60 fps",
        ancho=1280,
        alto=720,
        fps=60,
        bitrate_sugerido_kbps=7000,
        explicacion=(
            "Same sharpness as 720p30, twice the frames. Cursor and scrolling "
            "look smoother. The TV advertises it; not yet verified in our "
            "session."
        ),
    ),
    VideoMode(
        id="1080p30",
        etiqueta="1920 × 1080 at 30 fps",
        ancho=1920,
        alto=1080,
        fps=30,
        bitrate_sugerido_kbps=8000,
        explicacion=(
            "Full HD at 30 fps. Better text and windows than 720p, without "
            "demanding as much as 60 fps. The TV advertises it."
        ),
    ),
    VideoMode(
        id="1080p60",
        etiqueta="1920 × 1080 at 60 fps",
        ancho=1920,
        alto=1080,
        fps=60,
        bitrate_sugerido_kbps=14000,
        explicacion=(
            "Native Miracast receiver mode (not 4K: the protocol tops out at "
            "Full HD). Picture at 1080p60 has been seen against this TV. More "
            "sharpness and fluidity, more radio and CPU."
        ),
    ),
    VideoMode(
        id="480p60",
        etiqueta="640 × 480 at 60 fps",
        ancho=640,
        alto=480,
        fps=60,
        bitrate_sugerido_kbps=2000,
        explicacion=(
            "Rescue mode. Only if HD modes leave a black screen or the link "
            "drops. The picture will look small or heavily scaled."
        ),
    ),
)

MODO_POR_DEFECTO = "720p30"


def modo_por_id(ident: str) -> VideoMode:
    for modo in MODOS_VIDEO:
        if modo.id == ident:
            return modo
    return modo_por_id(MODO_POR_DEFECTO)


def modo_desde_tamano(ancho: int, alto: int, fps: int) -> VideoMode | None:
    for modo in MODOS_VIDEO:
        if modo.ancho == ancho and modo.alto == alto and modo.fps == fps:
            return modo
    return None
