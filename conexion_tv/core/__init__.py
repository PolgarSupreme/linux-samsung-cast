"""Núcleo: memoria de dispositivos, catálogo de protocolos y configuración."""

from .device_memory import (
    DeviceMemory,
    DeviceOption,
    DeviceRecord,
    ProtocolMemory,
    ProtocolState,
)
from .errors import ConexionError, DeviceUnreachableError, PairingRequiredError
from .protocols import CATALOGO, Protocol, ProtocolInfo, Purpose

__all__ = [
    "CATALOGO",
    "ConexionError",
    "DeviceMemory",
    "DeviceOption",
    "DeviceRecord",
    "DeviceUnreachableError",
    "PairingRequiredError",
    "Protocol",
    "ProtocolInfo",
    "ProtocolMemory",
    "ProtocolState",
    "Purpose",
]
