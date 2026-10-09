"""Tizen WebSocket controller (API v2).

Wraps `samsungtvws` and maps its failures to the application vocabulary.
The token is stored under `~/.config/conexion_tv/tokens/` with mode 0600.
"""

from __future__ import annotations

from pathlib import Path

from conexion_tv.core.device_memory import DeviceRecord
from conexion_tv.core.errors import DeviceUnreachableError, PairingRequiredError
from conexion_tv.core.net_policy import exigir_host_local
from conexion_tv.core.paths import asegurar_directorio, token_path
from conexion_tv.core.protocols import Protocol

from .base import PowerState, TVController, TVState
from .wol import wake


class TizenWebSocketController(TVController):
    def __init__(self, registro: DeviceRecord, *, nombre_app: str = "ConexionTV") -> None:
        if not registro.ultima_ip:
            raise DeviceUnreachableError(
                "No remembered IP for this TV.",
                consejo="Run a scan with the TV powered on.",
            )
        exigir_host_local(registro.ultima_ip, que="Tizen remote control")
        self._registro = registro
        self._nombre_app = nombre_app
        self._tv = None

    @property
    def host(self) -> str:
        return self._registro.ultima_ip  # type: ignore[return-value]

    def connect(self) -> None:
        from samsungtvws import SamsungTVWS

        exigir_host_local(self.host, que="Tizen remote control")
        token = token_path(self._registro.clave)
        asegurar_directorio(token.parent)
        try:
            self._tv = SamsungTVWS(
                host=self.host,
                port=8002,
                token_file=str(token),
                name=self._nombre_app,
                timeout=10,
            )
            # rest_device_info does not require the permission dialog and confirms
            # the TV is on and reachable.
            info = self._tv.rest_device_info()
        except OSError as exc:
            raise DeviceUnreachableError(
                "The TV does not respond.",
                consejo="Power it on or scan the network again.",
            ) from exc
        except Exception as exc:
            mensaje = str(exc).lower()
            if "token" in mensaje or "denied" in mensaje or "refused" in mensaje:
                raise PairingRequiredError(
                    "The TV asks you to accept the connection.",
                    consejo="Accept the dialog that appears on the TV screen.",
                ) from exc
            raise DeviceUnreachableError(
                "Could not open the remote channel.",
                consejo="Check that the TV is on and on the same network.",
            ) from exc

        self._anotar_token(token)
        estado = (info or {}).get("device", {}).get("PowerState", "on")
        if estado != "on":
            raise DeviceUnreachableError(
                "The TV is off.",
                consejo="Turn it on with the remote or Wake-on-LAN.",
            )

    def disconnect(self) -> None:
        if self._tv is None:
            return
        try:
            self._tv.close()
        except Exception:
            pass
        self._tv = None

    def send_key(self, key: str) -> None:
        tv = self._exigir_conexion()
        try:
            tv.send_key(key)
        except Exception as exc:
            self._registro.anotar_fallo(
                Protocol.TIZEN_WEBSOCKET, f"Failed to send {key}: {exc}"
            )
            raise DeviceUnreachableError(
                f"Could not send key {key}.",
                consejo="The remote channel dropped. Connect again.",
            ) from exc

    def power_on(self) -> None:
        mac = self._mac_para_wol()
        if not mac:
            raise DeviceUnreachableError(
                "No remembered MAC for Wake-on-LAN.",
                consejo="Scan once with the TV on to learn it.",
            )
        wake(mac)
        self._registro.anotar_anuncio(Protocol.WAKE_ON_LAN, datos={"mac": mac})

    def power_off(self) -> None:
        self.send_key("KEY_POWER")

    def get_state(self) -> TVState:
        tv = self._exigir_conexion()
        try:
            info = tv.rest_device_info() or {}
        except Exception as exc:
            raise DeviceUnreachableError(
                "Could not read the TV state.",
            ) from exc
        alimentacion = info.get("device", {}).get("PowerState", "unknown")
        mapeo = {"on": PowerState.ON, "off": PowerState.OFF}
        return TVState(alimentacion=mapeo.get(alimentacion, PowerState.UNKNOWN))

    def _exigir_conexion(self):
        if self._tv is None:
            raise DeviceUnreachableError(
                "No remote channel is open.",
                consejo="Connect to the TV first.",
            )
        return self._tv

    def _mac_para_wol(self) -> str | None:
        datos = self._registro.memoria(Protocol.WAKE_ON_LAN).datos
        if datos.get("mac"):
            return datos["mac"]
        for alias in [self._registro.clave, *self._registro.alias]:
            if alias.startswith("mac:"):
                return alias.removeprefix("mac:")
        return None

    def _anotar_token(self, token: Path) -> None:
        guardado = token.exists() and token.stat().st_size > 0
        if guardado:
            try:
                token.chmod(0o600)
            except OSError:
                pass
        self._registro.anotar_exito(
            Protocol.TIZEN_WEBSOCKET,
            evidencia="Remote channel open",
            datos={"puerto": 8002, "token_guardado": guardado},
        )
