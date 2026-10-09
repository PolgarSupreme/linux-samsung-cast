"""Sender displays and audio sources, to fill the GUI."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class OpcionFuente:
    id: str
    etiqueta: str


def pantallas() -> list[OpcionFuente]:
    """Connected monitors per xrandr. Empty id means «primary»."""
    opciones = [OpcionFuente("", "Primary display (automatic)")]
    try:
        r = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return opciones
    for linea in (r.stdout or "").splitlines():
        if " connected" not in linea or "disconnected" in linea:
            continue
        nombre = linea.split()[0]
        extra = "primary" if "primary" in linea else ""
        geometria = ""
        partes = linea.split()
        for p in partes:
            if "x" in p and "+" in p:
                geometria = p.split("+", 1)[0]
                break
        etiqueta = nombre
        if geometria:
            etiqueta += f" · {geometria}"
        if extra:
            etiqueta += f" · {extra}"
        opciones.append(OpcionFuente(nombre, etiqueta))
    return opciones


def fuentes_audio() -> list[OpcionFuente]:
    """Pulse/PipeWire sources. Empty id lets the backend choose."""
    opciones = [OpcionFuente("", "System default output")]
    try:
        r = subprocess.run(
            ["pactl", "list", "short", "sources"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return opciones
    for linea in (r.stdout or "").splitlines():
        cols = linea.split()
        if len(cols) < 2:
            continue
        nombre = cols[1]
        if nombre.endswith(".monitor"):
            corto = nombre.removesuffix(".monitor")
            etiqueta = f"What plays through {corto}"
        else:
            etiqueta = nombre
        opciones.append(OpcionFuente(nombre, etiqueta))
    return opciones


def interfaces_wifi() -> list[OpcionFuente]:
    """Wi-Fi radios NetworkManager can use for Direct."""
    opciones = [OpcionFuente("", "Automatic (radio linked to the router)")]
    try:
        r = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return opciones
    vistos: set[str] = set()
    for linea in (r.stdout or "").splitlines():
        partes = linea.split(":")
        if len(partes) < 2 or partes[1] != "wifi":
            continue
        nombre = partes[0]
        if nombre in vistos or nombre.startswith("p2p-"):
            continue
        vistos.add(nombre)
        estado = partes[2] if len(partes) > 2 else ""
        etiqueta = nombre
        if estado:
            etiqueta += f" · {estado}"
        opciones.append(OpcionFuente(nombre, etiqueta))
    return opciones
