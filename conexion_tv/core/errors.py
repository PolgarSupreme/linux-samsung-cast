"""Application vocabulary for errors.

Backends map their failures to these classes at the boundary. The core and UI
never import exceptions from FluxCast, samsungtvws, or UPnP.
"""

from __future__ import annotations


class ConexionError(Exception):
    """Base for all application errors."""

    def __init__(self, mensaje: str, *, consejo: str | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.consejo = consejo

    def __str__(self) -> str:
        if self.consejo:
            return f"{self.mensaje} {self.consejo}"
        return self.mensaje


class DeviceNotFoundError(ConexionError):
    """No reachable TV on the network."""


class PairingRequiredError(ConexionError):
    """The TV asks to accept a permission dialog."""


class DeviceUnreachableError(ConexionError):
    """The device is remembered but does not respond now."""


class ProtocolUnsupportedError(ConexionError):
    """The protocol is missing on this set, or there is no way to use it from Linux."""


class StreamFailedError(ConexionError):
    """Failed to establish or keep a projection session."""


class FirewallError(ConexionError):
    """Could not open or close the firewall port."""