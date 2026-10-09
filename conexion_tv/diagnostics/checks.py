"""Sender-side checks. Each failure suggests the command that fixes it."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    id: str
    titulo: str
    ok: bool
    detalle: str
    arreglo: str | None = None


def _cual(*nombres: str) -> str | None:
    for n in nombres:
        encontrado = shutil.which(n)
        if encontrado:
            return encontrado
    return None


def _activo(unidad: str) -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "--quiet", unidad],
            timeout=2,
            check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def comprobar_sistema() -> list[Check]:
    return [
        _binario("ffmpeg", "ffmpeg", "Capture and encode for projection", "sudo apt install -y ffmpeg"),
        _binario("iw", "iw", "Diagnose Wi-Fi adapter P2P modes", "sudo apt install -y iw"),
        _binario("gst-launch-1.0", "GStreamer", "Mux and capture elements", "sudo apt install -y gstreamer1.0-tools"),
        _vaapi(),
        _wpa(),
        _p2p(),
        _pkexec(),
        _portal(),
        _fluxcast(),
    ]


def _binario(comando: str, titulo: str, para_que: str, arreglo: str) -> Check:
    ruta = _cual(comando)
    if ruta:
        return Check(comando, titulo, True, f"{para_que}. Found at {ruta}")
    return Check(comando, titulo, False, f"Not installed. {para_que}.", arreglo)


def _vaapi() -> Check:
    render = Path("/dev/dri/renderD128")
    if not render.exists():
        return Check(
            "vaapi",
            "VAAPI encoder",
            False,
            "No /dev/dri/renderD128. Projection will fall back to software x264.",
            None,
        )
    vainfo = _cual("vainfo")
    if vainfo is None:
        return Check(
            "vaapi",
            "VAAPI encoder",
            True,
            f"GPU present at {render}, but vainfo is not installed to list H.264 profiles.",
            "sudo apt install -y vainfo",
        )
    try:
        salida = subprocess.check_output([vainfo], text=True, timeout=4, stderr=subprocess.STDOUT)
    except (OSError, subprocess.SubprocessError):
        return Check("vaapi", "VAAPI encoder", True, f"GPU present at {render}.")
    h264 = "H264" in salida.upper() or "h264" in salida
    return Check(
        "vaapi",
        "VAAPI encoder",
        True,
        "H.264 profile advertised by vainfo." if h264 else f"GPU present at {render}; vainfo did not advertise H.264.",
    )


def _wpa() -> Check:
    wpa = _activo("wpa_supplicant")
    iwd = _activo("iwd")
    if wpa and not iwd:
        return Check("wifi-backend", "Wi-Fi backend", True, "wpa_supplicant active, iwd inactive. Correct for Miracast.")
    if iwd:
        return Check(
            "wifi-backend",
            "Wi-Fi backend",
            False,
            "iwd is active. With iwd, Miracast discovery returns no devices.",
            "sudo systemctl disable --now iwd && sudo systemctl enable --now wpa_supplicant",
        )
    return Check(
        "wifi-backend",
        "Wi-Fi backend",
        False,
        "Could not confirm that wpa_supplicant is active.",
        "sudo systemctl status wpa_supplicant",
    )


def _p2p() -> Check:
    nmcli = _cual("nmcli")
    if nmcli is None:
        return Check("p2p", "Wi-Fi Direct", False, "nmcli is not installed.", "sudo apt install -y network-manager")
    try:
        salida = subprocess.check_output(
            [nmcli, "-t", "-f", "DEVICE,TYPE,STATE", "dev"],
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return Check("p2p", "Wi-Fi Direct", False, "Could not query NetworkManager.")
    for linea in salida.splitlines():
        if ":wifi-p2p:" in linea:
            return Check("p2p", "Wi-Fi Direct", True, f"P2P interface present: {linea.split(':', 1)[0]}")
    return Check(
        "p2p",
        "Wi-Fi Direct",
        False,
        "NetworkManager shows no wifi-p2p interface. The adapter may not support Wi-Fi Direct.",
        None,
    )


def _pkexec() -> Check:
    if _cual("pkexec"):
        return Check("pkexec", "Privilege elevation", True, "pkexec available to open port 7236 from the app.")
    return Check(
        "pkexec",
        "Privilege elevation",
        False,
        "Without pkexec the UI cannot open port 7236.",
        "sudo apt install -y policykit-1",
    )


def _fluxcast() -> Check:
    from conexion_tv.mirror.backends.fluxcast.cli import encontrar_binario

    ruta = encontrar_binario()
    if ruta:
        return Check("fluxcast", "FluxCast (Miracast)", True, f"Projection engine found at {ruta}.")
    return Check(
        "fluxcast",
        "FluxCast (Miracast)",
        False,
        "Without FluxCast you cannot share the screen over Miracast.",
        "python3 -m venv .venv-fluxcast && .venv-fluxcast/bin/pip install fluxcast --no-deps",
    )


def _portal() -> Check:
    if os.environ.get("XDG_SESSION_TYPE") == "x11":
        return Check(
            "captura",
            "Screen capture",
            True,
            "X11 session: x11grab is the most direct capture path.",
        )
    return Check(
        "captura",
        "Screen capture",
        True,
        "Wayland session: the ScreenCast portal (xdg-desktop-portal) will be needed.",
    )
