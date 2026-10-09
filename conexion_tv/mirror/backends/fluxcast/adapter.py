"""ScreenMirroring adapter: FluxCast as a subprocess, without importing its API."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import replace

from conexion_tv.core.device_memory import DeviceRecord
from conexion_tv.core.errors import StreamFailedError
from conexion_tv.core.events import ConnectionState, StateChanged, UserMessage
from conexion_tv.core.protocols import Protocol
from conexion_tv.mirror.base import (
    BackendCapabilities,
    LinkFacts,
    ScreenMirroring,
    StreamConfig,
)
from conexion_tv.mirror.firewall import abrir_puerto, cerrar_puerto, puerto_abierto
from conexion_tv.mirror.p2p_channel import (
    aplicar_canal_operacion,
    es_canal_5,
    preparar_config_para_canal,
    requiere_fuerza_propia,
)
from conexion_tv.mirror.remote_display import RemoteDisplay, RemoteDisplayRuntime

from .cli import (
    WfdPeer,
    cerrar_enlace_p2p,
    construir_comando,
    encontrar_binario,
    escanear_pares,
    es_fallo_p2p_reintentable,
    extraer_estado_enlace,
    log_path,
    motivo_fallo_desde_log,
    pids_fluxcast_wfd,
    traducir_registro,
)


class FluxCastBackend(ScreenMirroring):
    def __init__(self) -> None:
        self._registro: DeviceRecord | None = None
        self._peer: str | None = None
        self._proceso: subprocess.Popen | None = None
        self._log: object | None = None
        self._abrimos_firewall = False
        self._gestionar_firewall = True
        self._config: StreamConfig | None = None
        self._pantalla_remota = RemoteDisplayRuntime()

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            id="fluxcast-wfd",
            nombre="Miracast (FluxCast)",
            audio=True,
            necesita_wifi_direct=True,
            latencia_ms=(150, 500),
            descripcion="Screen mirror with audio over Wi-Fi Direct.",
        )

    def is_available(self, registro: DeviceRecord) -> tuple[bool, str]:
        if encontrar_binario() is None:
            return False, "FluxCast is not installed in the environment."
        return True, ""

    def connect(self, registro: DeviceRecord, config: StreamConfig | None = None) -> None:
        binario = encontrar_binario()
        if binario is None:
            raise StreamFailedError(
                "FluxCast is missing.",
                consejo="In the project environment: pip install fluxcast",
            )
        if config is not None:
            self._config = config
            self._gestionar_firewall = config.gestionar_firewall
        self._emit(StateChanged(estado=ConnectionState.DISCOVERING))
        self._emit(UserMessage(
            texto="Put the TV on Source → Remote Access → Screen Sharing.",
            nivel="info",
        ))
        cfg = config or self._config or StreamConfig()
        # Un --wfd-scan extra agita el P2P y luego FluxCast vuelve a escanear.
        # Con la MAC P2P (o la Wi-Fi XOR 0x02) se lanza igual que el CLI.
        peer_mac = _peer_mac_del_registro(registro)
        if peer_mac is None:
            pares = escanear_pares(
                binario,
                scan_timeout_s=cfg.scan_timeout_s,
                wifi_interface=cfg.wifi_interface,
            )
            peer = _elegir_par(pares, registro)
            if peer is None:
                raise StreamFailedError(
                    "The TV does not appear as a Miracast receiver.",
                    consejo="On the TV open Source → Remote Access → Screen Sharing and wait until it searches for devices.",
                )
            peer_mac = peer.mac
        self._emit(StateChanged(estado=ConnectionState.PAIRING, detalle=peer_mac))
        puerto = cfg.rtsp_port
        if self._gestionar_firewall and not puerto_abierto(puerto):
            self._emit(UserMessage(
                texto=f"Firewall port {puerto} must be opened. Accept the password dialog.",
                nivel="aviso",
            ))
            abrir_puerto(puerto)
            self._abrimos_firewall = True
        self._registro = registro
        self._peer = peer_mac
        registro.anotar_anuncio(Protocol.MIRACAST_WFD, datos={"peer_mac": peer_mac})
        self._emit(StateChanged(estado=ConnectionState.CONNECTED, detalle=peer_mac))

    def start_stream(self, config: StreamConfig) -> None:
        if self._registro is None or self._peer is None:
            raise StreamFailedError(
                "No Miracast session is prepared.",
                consejo="Connect projection first.",
            )
        binario = encontrar_binario()
        if binario is None:
            raise StreamFailedError("FluxCast is missing.")
        if self._proceso is not None and self._proceso.poll() is None:
            self.aplicar_ruta_audio(config)
            return
        self._config = config
        self._gestionar_firewall = config.gestionar_firewall
        try:
            try:
                self._lanzar_fluxcast(config)
                return
            except StreamFailedError as exc:
                if not es_fallo_p2p_reintentable(str(exc)):
                    raise
            self._emit(UserMessage(
                texto="The TV did not join the Direct group. Waiting a moment and trying again, as when doing it by hand.",
                nivel="aviso",
            ))
            time.sleep(8)
            self._lanzar_fluxcast(config)
        except Exception:
            self._pantalla_remota.close()
            raise

    def _lanzar_fluxcast(self, config: StreamConfig) -> None:
        binario = encontrar_binario()
        if binario is None:
            raise StreamFailedError("FluxCast is missing.")
        self._matar_proceso()
        _cerrar_huerfanos_wfd()
        canal, backend, go, aviso_canal = preparar_config_para_canal(
            p2p_channel=config.p2p_channel,
            p2p_backend=config.p2p_backend,
            go_intent=config.go_intent,
            wifi_interface=config.wifi_interface,
        )
        config = replace(
            config,
            p2p_channel=canal,
            p2p_backend=backend,
            go_intent=go,
        )
        if aviso_canal:
            self._emit(UserMessage(texto=aviso_canal, nivel="aviso"))
        if canal is not None and requiere_fuerza_propia(canal):
            ok = aplicar_canal_operacion(
                canal, wifi_interface=config.wifi_interface
            )
            banda = "5 GHz" if es_canal_5(canal) else "2.4 GHz"
            if ok:
                self._emit(UserMessage(
                    texto=(
                        f"Direct channel forced to {canal} ({banda}). "
                        "wpa_supplicant backend and PC as group owner."
                    ),
                    nivel="info",
                ))
            else:
                self._emit(UserMessage(
                    texto=(
                        f"Could not set channel {canal} in wpa_supplicant "
                        "(pkexec?). Continuing; the driver may fall back to 2.4 GHz."
                    ),
                    nivel="aviso",
                ))
        remota = RemoteDisplay.from_stream_config(config)
        audio_dev = self._preparar_audio_remoto(remota)
        cmd = construir_comando(
            binario=binario,
            peer=self._peer,
            ancho=remota.ancho,
            alto=remota.alto,
            fps=remota.fps,
            bitrate_kbps=remota.bitrate_kbps,
            audio=remota.envia_audio(),
            monitor=remota.monitor or _monitor_x11(),
            captura=remota.captura,
            audio_device=audio_dev,
            entrada_remota=config.entrada_remota,
            go_intent=config.go_intent,
            rtsp_port=config.rtsp_port,
            rtp_source_port=config.rtp_source_port,
            scan_timeout_s=config.scan_timeout_s,
            p2p_backend=config.p2p_backend,
            p2p_channel=config.p2p_channel,
            media_pipeline=config.media_pipeline,
            wifi_interface=config.wifi_interface,
            test_pattern=config.test_pattern,
        )
        destino = log_path()
        fh = open(destino, "w", encoding="utf-8")
        fh.write(" ".join(cmd) + "\n")
        fh.flush()
        try:
            from .cli import _entorno

            self._proceso = subprocess.Popen(
                cmd,
                stdout=fh,
                stderr=subprocess.STDOUT,
                env=_entorno(),
                start_new_session=True,
            )
        except OSError as exc:
            fh.close()
            raise StreamFailedError("Could not start FluxCast.") from exc
        self._log = fh
        self._esperar_arranque(destino)
        self._emit(StateChanged(estado=ConnectionState.STREAMING, detalle=str(destino)))
        self._emit(UserMessage(
            texto="Projection running. Accept the connection on the TV if it asks.",
            nivel="info",
        ))

    def _esperar_arranque(self, destino, *, segundos: float = 40.0) -> None:
        """Do not declare success until PLAY, or fail with the real reason."""
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            proc = self._proceso
            if proc is not None and proc.poll() is not None:
                raise StreamFailedError(
                    self._motivo_log(destino) or "The mirror process closed on startup.",
                    consejo="Put the TV on Screen Sharing and try again.",
                )
            try:
                texto = destino.read_text(encoding="utf-8", errors="replace")
            except OSError:
                texto = ""
            if "PLAY accepted" in texto or "media stream started" in texto:
                return
            motivo = motivo_fallo_desde_log(texto)
            if motivo:
                self._matar_proceso()
                raise StreamFailedError(
                    motivo,
                    consejo="On the TV: Source → Remote Access → Screen Sharing, then retry.",
                )
            time.sleep(0.4)
        # Sigue vivo pero sin PLAY: dejarlo correr; el TV a veces tarda.
        self._emit(UserMessage(
            texto="The link is up, but the TV has not accepted the picture yet. Check its screen.",
            nivel="aviso",
        ))

    def _motivo_log(self, destino) -> str | None:
        try:
            return motivo_fallo_desde_log(
                destino.read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            return None

    def aplicar_ruta_audio(self, config: StreamConfig) -> None:
        """Ajusta sink virtual / loopback sin relanzar FluxCast si ya captura el bus."""
        remota = RemoteDisplay.from_stream_config(config)
        ok = self._pantalla_remota.apply_audio(remota.audio_route)
        if remota.envia_audio() and not ok:
            self._emit(UserMessage(
                texto=(
                    "Could not set up the TV virtual audio. "
                    "Try «Both» or check PulseAudio (pactl)."
                ),
                nivel="aviso",
            ))

        # Historical name (older GUI).
    def aplicar_silencio_local(self, config: StreamConfig) -> None:
        self.aplicar_ruta_audio(config)

    def _preparar_audio_remoto(self, remota: RemoteDisplay) -> str | None:
        ok = self._pantalla_remota.apply_audio(remota.audio_route)
        if remota.envia_audio() and not ok:
            self._emit(UserMessage(
                texto=(
                    "Could not set up virtual audio. Mirroring continues; "
                    "sound may fail on the TV or the PC."
                ),
                nivel="aviso",
            ))
        if remota.envia_audio():
            return self._pantalla_remota.pulse_capture_device(remota.audio_device)
        return remota.audio_device

    def stop_stream(self) -> None:
        self._matar_proceso()
        self._pantalla_remota.close()
        if self._registro is not None:
            self._registro.anotar_exito(
                Protocol.MIRACAST_WFD,
                evidencia="Miracast session started and stopped by the user",
                datos={"peer_mac": self._peer} if self._peer else None,
            )
        self._emit(StateChanged(estado=ConnectionState.CONNECTED))

    def disconnect(self) -> None:
        self._matar_proceso()
        self._pantalla_remota.close()
        if self._abrimos_firewall:
            try:
                puerto = (self._config.rtsp_port if self._config else 7236)
                cerrar_puerto(puerto)
            except Exception:
                pass
            self._abrimos_firewall = False
        self._registro = None
        self._peer = None
        self._emit(StateChanged(estado=ConnectionState.DISCONNECTED))

    def _matar_proceso(self) -> None:
        proc = self._proceso
        self._proceso = None
        if proc is not None:
            # SIGINT = Ctrl+C: FluxCast hace TEARDOWN RTSP y baja el P2P.
            # SIGTERM kills it without that teardown and the TV is left hanging.
            _enviar_senal(proc, signal.SIGINT)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                _enviar_senal(proc, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _enviar_senal(proc, signal.SIGKILL)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
        if self._log is not None:
            try:
                self._log.close()
            except OSError:
                pass
            self._log = None
        cerrar_enlace_p2p()

    def esta_activo(self) -> bool:
        proc = self._proceso
        return proc is not None and proc.poll() is None

    def detalle_sesion(self) -> str:
        destino = log_path()
        if not destino.is_file():
            return ""
        try:
            texto = destino.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return traducir_registro(texto)

    def resumen_enlace(self) -> LinkFacts:
        destino = log_path()
        if not destino.is_file():
            return LinkFacts()
        try:
            texto = destino.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return LinkFacts()
        return extraer_estado_enlace(texto)


def _mac_wifi_direct(mac: str) -> str:
    """La MAC P2P suele ser la Wi-Fi con el bit 'locally administered' invertido.

    Example: Wi-Fi aa:bb:... → P2P a8:bb:... (locally administered bit).
    """
    partes = mac.lower().split(":")
    if len(partes) != 6:
        return mac.lower()
    partes[0] = f"{int(partes[0], 16) ^ 0x02:02x}"
    return ":".join(partes)


def _peer_mac_del_registro(registro: DeviceRecord) -> str | None:
    """MAC Wi-Fi Direct conocida, sin un escaneo WFD previo."""
    mem = registro.protocolos.get(Protocol.MIRACAST_WFD)
    if mem is not None:
        guardada = mem.datos.get("peer_mac")
        if isinstance(guardada, str) and guardada.count(":") == 5:
            return guardada.lower()
    for ident in [registro.clave, *registro.alias]:
        if ident.startswith("mac:"):
            return _mac_wifi_direct(ident.removeprefix("mac:"))
    return None


def _elegir_par(pares: list[WfdPeer], registro: DeviceRecord) -> WfdPeer | None:
    macs = set()
    for ident in [registro.clave, *registro.alias]:
        if ident.startswith("mac:"):
            m = ident.removeprefix("mac:").lower()
            macs.add(m)
            macs.add(_mac_wifi_direct(m))
    for par in pares:
        if par.mac.lower() in macs:
            return par
        if registro.coincide(par.mac) or registro.coincide(_mac_wifi_direct(par.mac)):
            return par
    if len(pares) == 1:
        return pares[0]
    nombre = (registro.nombre or "").lower()
    for par in pares:
        if nombre and nombre in par.nombre.lower():
            return par
    return pares[0] if pares else None


def _enviar_senal(proc: subprocess.Popen, senal: int) -> None:
    try:
        os.killpg(proc.pid, senal)
    except (OSError, ProcessLookupError):
        try:
            proc.send_signal(senal)
        except (OSError, ProcessLookupError):
            pass


def _cerrar_huerfanos_wfd(*, excluir: int | None = None) -> None:
    """Cierra sesiones FluxCast previas con SIGINT para que bajen el P2P."""
    pids = pids_fluxcast_wfd(excluir=excluir)
    if pids:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGINT)
            except (OSError, ProcessLookupError):
                continue
        time.sleep(2.0)
        for pid in pids_fluxcast_wfd(excluir=excluir):
            try:
                os.kill(pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        time.sleep(0.5)
        for pid in pids_fluxcast_wfd(excluir=excluir):
            try:
                os.kill(pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
    cerrar_enlace_p2p()


def _monitor_x11() -> str | None:
    try:
        r = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for linea in (r.stdout or "").splitlines():
        if " connected primary" in linea:
            return linea.split()[0]
    for linea in (r.stdout or "").splitlines():
        if " connected" in linea:
            return linea.split()[0]
    return None
