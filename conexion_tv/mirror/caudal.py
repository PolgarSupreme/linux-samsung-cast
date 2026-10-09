"""Video bitrate as a lever for wait time and radio load.

FluxCast only accepts `--bitrate`: it becomes b:v = maxrate and, on Samsung,
VBV = 2× that bitrate. Raising Mb/s does not cut those ~2 s of buffer; it does
send more bits per frame, so the encoder compresses less and motion usually
looks sharper. Lowering Mb/s eases Wi-Fi Direct.

At 20 000 kb/s this TV never created a session. The UI ceiling stays below that
failure.
"""

from __future__ import annotations

from dataclasses import dataclass


BITRATE_MIN_KBPS = 2000
BITRATE_MAX_KBPS = 16000


@dataclass(frozen=True)
class CaudalPreset:
    id: str
    kbps: int
    etiqueta: str
    explicacion: str


CAUDALES: tuple[CaudalPreset, ...] = (
    CaudalPreset(
        id="bajo",
        kbps=4000,
        etiqueta="Lower bitrate · more wait possible",
        explicacion=(
            "4 Mb/s. Less data per second: Direct radio breathes and the "
            "encoder compresses more. Verified at 720p30."
        ),
    ),
    CaudalPreset(
        id="medio",
        kbps=8000,
        etiqueta="Balance",
        explicacion=(
            "8 Mb/s. Middle ground if 4 Mb/s looks soft and 14 Mb/s saturates. "
            "Glass-to-glass not measured yet."
        ),
    ),
    CaudalPreset(
        id="alto",
        kbps=14000,
        etiqueta="Higher bitrate · less wait",
        explicacion=(
            "14 Mb/s. More bits per frame: the encoder does not have to crush "
            "each picture as hard. Verified at 1080p60."
        ),
    ),
)

CAUDAL_PERSONALIZADO = "custom"


def acotar_bitrate(kbps: int) -> int:
    return max(BITRATE_MIN_KBPS, min(BITRATE_MAX_KBPS, int(kbps)))


def kbit_por_fotograma(kbps: int, fps: int) -> int:
    return max(1, round(int(kbps) / max(1, int(fps))))


def caudal_por_id(ident: str) -> CaudalPreset | None:
    for preset in CAUDALES:
        if preset.id == ident:
            return preset
    return None


def caudal_por_kbps(kbps: int) -> CaudalPreset | None:
    for preset in CAUDALES:
        if preset.kbps == kbps:
            return preset
    return None


def pista_caudal(kbps: int, fps: int) -> str:
    kpf = kbit_por_fotograma(kbps, fps)
    preset = caudal_por_kbps(kbps)
    cabeza = preset.explicacion if preset else (
        f"{kbps} kb/s custom. Higher bitrate = more data per frame and "
        "usually less wait; lower bitrate = less radio."
    )
    return (
        f"{cabeza} Now ≈ {kpf} kbit/frame at {fps} fps. Cap "
        f"{BITRATE_MAX_KBPS // 1000} Mb/s: at 20 Mb/s this TV did not connect. "
        "If you see dropouts, lower the bitrate or mode: FluxCast VBV on "
        "Samsung is 2× the bitrate (no separate buffer dial) and a high "
        "bitrate saturates Wi-Fi Direct sooner."
    )
