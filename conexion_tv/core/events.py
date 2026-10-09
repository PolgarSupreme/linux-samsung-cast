"""Eventos que cruzan del núcleo hacia la interfaz.

Son dataclasses inmutables a propósito: la GUI solo las observa. Los nombres
son del vocabulario de la aplicación, nunca del backend que los originó.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class ConnectionState(str, Enum):
    DISCONNECTED = "desconectado"
    DISCOVERING = "descubriendo"
    PAIRING = "emparejando"
    CONNECTED = "conectado"
    STREAMING = "proyectando"
    ERROR = "error"


@dataclass(frozen=True)
class AppEvent:
    instante: datetime = field(default_factory=_ahora)


@dataclass(frozen=True)
class StateChanged(AppEvent):
    estado: ConnectionState = ConnectionState.DISCONNECTED
    detalle: str = ""


@dataclass(frozen=True)
class DeviceFound(AppEvent):
    clave: str = ""
    nombre: str = ""
    modelo: str = ""
    ip: str | None = None


@dataclass(frozen=True)
class StreamMetrics(AppEvent):
    bitrate_kbps: float | None = None
    fps: float | None = None
    latencia_ms: float | None = None
    fotogramas_perdidos: int = 0


@dataclass(frozen=True)
class UserMessage(AppEvent):
    """Texto pensado para mostrarse tal cual en la interfaz."""

    texto: str = ""
    nivel: str = "info"  # info | aviso | error
