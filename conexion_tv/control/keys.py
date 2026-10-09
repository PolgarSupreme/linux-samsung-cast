"""Tizen remote keys the UI can offer.

Not Samsung's full list: only what a virtual remote needs. Identifiers match
the API (`KEY_*`) on purpose so we do not translate in two places.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteKey:
    codigo: str
    etiqueta: str
    grupo: str


TECLAS: tuple[RemoteKey, ...] = (
    RemoteKey("KEY_POWER", "Power on / off", "alimentacion"),
    RemoteKey("KEY_VOLUP", "Volume up", "volumen"),
    RemoteKey("KEY_VOLDOWN", "Volume down", "volumen"),
    RemoteKey("KEY_MUTE", "Mute", "volumen"),
    RemoteKey("KEY_UP", "Up", "direccion"),
    RemoteKey("KEY_DOWN", "Down", "direccion"),
    RemoteKey("KEY_LEFT", "Left", "direccion"),
    RemoteKey("KEY_RIGHT", "Right", "direccion"),
    RemoteKey("KEY_ENTER", "OK", "direccion"),
    RemoteKey("KEY_RETURN", "Back", "navegacion"),
    RemoteKey("KEY_HOME", "Home", "navegacion"),
    RemoteKey("KEY_MENU", "Menu", "navegacion"),
    RemoteKey("KEY_SOURCE", "Source", "entrada"),
    RemoteKey("KEY_HDMI", "HDMI", "entrada"),
    RemoteKey("KEY_CHUP", "Channel +", "canal"),
    RemoteKey("KEY_CHDOWN", "Channel −", "canal"),
    RemoteKey("KEY_PLAY", "Play", "reproduccion"),
    RemoteKey("KEY_PAUSE", "Pause", "reproduccion"),
    RemoteKey("KEY_STOP", "Stop", "reproduccion"),
)


def por_grupo(grupo: str) -> tuple[RemoteKey, ...]:
    return tuple(t for t in TECLAS if t.grupo == grupo)
