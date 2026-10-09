"""Virtual audio bus for the remote display (the TV).

Apps play into a `module-null-sink`. FluxCast captures its `.monitor`
and sends it over Miracast. PC speakers, when needed, get a
`module-loopback` from that same monitor — so «TV only» and «both» share
the same capture and HDMI need not be muted (which left the monitor at 0).
"""

from __future__ import annotations

import subprocess

NULL_SINK = "conexion_tv_cast"
NULL_MONITOR = f"{NULL_SINK}.monitor"
_NULL_ARGS = (
    f"sink_name={NULL_SINK}",
    "sink_properties=device.description=ConexionTV_cast",
)


class VirtualAudioBus:
    """Lifecycle of the null sink + optional loopback to speakers."""

    def __init__(self) -> None:
        self._abierto = False
        self._null_module: str | None = None
        self._loop_module: str | None = None
        self._default_sink: str | None = None
        self._speakers: str | None = None
        self._moved: list[tuple[str, str]] = []

    @property
    def abierto(self) -> bool:
        return self._abierto

    @property
    def monitor(self) -> str | None:
        return NULL_MONITOR if self._abierto else None

    def open(self) -> bool:
        """Create the null sink and move system playback there."""
        if self._abierto:
            return True
        if not self._asegurar_null():
            return False
        self._default_sink = _pactl_texto("get-default-sink") or None
        self._speakers = (
            self._default_sink
            if self._default_sink and self._default_sink != NULL_SINK
            else None
        )
        self._moved = []
        for entrada, sink in _sink_inputs():
            if sink == NULL_SINK:
                continue
            if _pactl_ok("move-sink-input", entrada, NULL_SINK):
                self._moved.append((entrada, sink))
        if self._speakers:
            _pactl_ok("set-default-sink", NULL_SINK)
        self._abierto = True
        return True

    def set_speakers(self, encendidos: bool) -> bool:
        """Loopback from virtual monitor → real speakers («both» mode)."""
        if not self._abierto:
            return not encendidos
        if encendidos:
            return self._activar_loopback()
        self._quitar_loopback()
        return True

    def close(self) -> None:
        self._quitar_loopback()
        if not self._abierto and self._null_module is None:
            return
        destino = self._speakers or self._default_sink
        for entrada, sink in reversed(self._moved):
            _pactl_ok("move-sink-input", entrada, sink)
        self._moved = []
        if destino and destino != NULL_SINK:
            _pactl_ok("set-default-sink", destino)
            _pactl_ok("set-sink-mute", destino, "0")
        self._default_sink = None
        self._speakers = None
        self._abierto = False
        self._descargar_null()

    def _asegurar_null(self) -> bool:
        if _sink_existe(NULL_SINK):
            mid = _module_id_con(NULL_SINK, "module-null-sink")
            if mid:
                self._null_module = mid
            return True
        r = _pactl("load-module", "module-null-sink", *_NULL_ARGS)
        if r is None or r.returncode != 0:
            return False
        mid = (r.stdout or "").strip()
        if mid.isdigit():
            self._null_module = mid
        return _sink_existe(NULL_SINK)

    def _activar_loopback(self) -> bool:
        if self._loop_module:
            return True
        speakers = self._speakers
        if not speakers:
            return False
        r = _pactl(
            "load-module",
            "module-loopback",
            f"source={NULL_MONITOR}",
            f"sink={speakers}",
            "latency_msec=30",
            "sink_dont_move=true",
            "source_dont_move=true",
        )
        if r is None or r.returncode != 0:
            return False
        mid = (r.stdout or "").strip()
        if mid.isdigit():
            self._loop_module = mid
            return True
        # Some versions do not print the id; look up the module.
        mid = _module_id_con(NULL_MONITOR, "module-loopback")
        self._loop_module = mid
        return mid is not None

    def _quitar_loopback(self) -> None:
        mid = self._loop_module or _module_id_con(NULL_MONITOR, "module-loopback")
        self._loop_module = None
        if mid:
            _pactl_ok("unload-module", mid)

    def _descargar_null(self) -> None:
        mid = self._null_module or _module_id_con(NULL_SINK, "module-null-sink")
        self._null_module = None
        if mid:
            _pactl_ok("unload-module", mid)


def _sink_inputs() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for linea in _pactl_texto("list", "short", "sink-inputs").splitlines():
        cols = linea.split()
        if len(cols) < 2:
            continue
        nombre = _sink_name_from_ref(cols[1])
        if nombre:
            out.append((cols[0], nombre))
    return out


def _sink_name_from_ref(ref: str) -> str | None:
    if not ref.isdigit():
        return ref or None
    for linea in _pactl_texto("list", "short", "sinks").splitlines():
        cols = linea.split()
        if len(cols) >= 2 and cols[0] == ref:
            return cols[1]
    return None


def _sink_existe(nombre: str) -> bool:
    for linea in _pactl_texto("list", "short", "sinks").splitlines():
        cols = linea.split()
        if len(cols) >= 2 and cols[1] == nombre:
            return True
    return False


def _module_id_con(token: str, tipo: str) -> str | None:
    for linea in _pactl_texto("list", "short", "modules").splitlines():
        if tipo not in linea or token not in linea:
            continue
        cols = linea.split()
        if cols:
            return cols[0]
    return None


def _pactl(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["pactl", *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _pactl_texto(*args: str) -> str:
    r = _pactl(*args)
    if r is None:
        return ""
    return (r.stdout or "").strip()


def _pactl_ok(*args: str) -> bool:
    r = _pactl(*args)
    return r is not None and r.returncode == 0
