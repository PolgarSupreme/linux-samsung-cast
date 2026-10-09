"""Control subsystem contract. Independent of projection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class PowerState(str, Enum):
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TVState:
    alimentacion: PowerState
    volumen: int | None = None
    silenciado: bool | None = None
    aplicacion: str | None = None


class TVController(ABC):
    """TV remote: keys, volume, power, apps.

    Must work even when no projection backend is available.
    """

    @abstractmethod
    def connect(self) -> None:
        """Open the remote channel. May require accepting a dialog on the TV."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the channel without powering off the TV."""

    @abstractmethod
    def send_key(self, key: str) -> None:
        """Send a remote key. See `control.keys`."""

    @abstractmethod
    def power_on(self) -> None:
        """Try to power on the TV (Wake-on-LAN)."""

    @abstractmethod
    def power_off(self) -> None:
        """Power off the TV via the remote channel."""

    @abstractmethod
    def get_state(self) -> TVState:
        """Observable state without blocking too long."""

    def set_volume(self, steps: int) -> None:
        """Raise or lower volume `steps` times. Positive up, negative down."""
        tecla = "KEY_VOLUP" if steps > 0 else "KEY_VOLDOWN"
        for _ in range(abs(steps)):
            self.send_key(tecla)
