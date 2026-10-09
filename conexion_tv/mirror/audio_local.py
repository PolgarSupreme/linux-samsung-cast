"""Compatibilidad: la lógica vive en virtual_audio + remote_display."""

from __future__ import annotations

from conexion_tv.mirror.remote_display import (
    audio_y_silencio,
    destino_desde_config,
)
from conexion_tv.mirror.virtual_audio import (
    NULL_MONITOR,
    NULL_SINK,
    VirtualAudioBus,
)

# Nombre histórico: la GUI/tests antiguos hablaban de «silencio local».
SilencioLocal = VirtualAudioBus


def sink_de_fuente(audio_device: str | None) -> str | None:
    if audio_device:
        nombre = audio_device.strip()
        if nombre.endswith(".monitor"):
            return nombre.removesuffix(".monitor")
        return nombre
    from conexion_tv.mirror.virtual_audio import _pactl_texto

    return _pactl_texto("get-default-sink") or None


__all__ = [
    "NULL_MONITOR",
    "NULL_SINK",
    "SilencioLocal",
    "VirtualAudioBus",
    "audio_y_silencio",
    "destino_desde_config",
    "sink_de_fuente",
]
