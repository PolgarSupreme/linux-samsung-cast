"""Invoke FluxCast as an external process. The package is never imported."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from conexion_tv.core.errors import StreamFailedError
from conexion_tv.mirror.base import LinkFacts
from conexion_tv.mirror.caudal import acotar_bitrate
from conexion_tv.mirror.p2p_channel import es_canal_24

MAC_RE = re.compile(r"\b([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\b")


@dataclass(frozen=True)
class WfdPeer:
    mac: str
    nombre: str = ""


def encontrar_binario() -> str | None:
    """Find the executable. It lives in its own venv so GPL does not mix with the GUI."""
    en_path = shutil.which("fluxcast")
    if en_path:
        return en_path
    raiz = Path(__file__).resolve().parents[4]
    local = raiz / ".venv-fluxcast" / "bin" / "fluxcast"
    if local.exists():
        return str(local)
    return None


_CAPTURA = {
    "x11": "x11grab",
    "x11grab": "x11grab",
    "portal": "portal",
    "auto": "auto",
    "gstreamer": "gst-x11",
    "gst-x11": "gst-x11",
}


def construir_comando(
    *,
    binario: str,
    peer: str,
    ancho: int,
    alto: int,
    fps: int,
    bitrate_kbps: int,
    audio: bool,
    monitor: str | None = None,
    captura: str = "x11",
    audio_device: str | None = None,
    entrada_remota: bool = False,
    go_intent: int | None = None,
    rtsp_port: int = 7236,
    rtp_source_port: int = 19002,
    scan_timeout_s: int = 8,
    p2p_backend: str = "nm",
    p2p_channel: int | None = None,
    media_pipeline: str = "auto",
    wifi_interface: str | None = None,
    test_pattern: bool = False,
) -> list[str]:
    backend = _CAPTURA.get(captura, "x11grab")
    cmd = [
        binario,
        "--protocol",
        "wfd",
        "--wfd-peer",
        peer,
        "--wfd-capture-backend",
        backend,
        "--wfd-no-firewall",
        "--output-res",
        f"{ancho}x{alto}",
        "--fps",
        str(fps),
        "--bitrate",
        f"{acotar_bitrate(bitrate_kbps)}k",
    ]
    if not audio:
        cmd.append("--wfd-no-audio")
    if audio and audio_device:
        cmd.extend(["--wfd-audio-device", audio_device])
    if monitor:
        cmd.extend(["--monitor", monitor])
    if entrada_remota:
        cmd.append("--wfd-uibc")
    if go_intent is not None:
        cmd.extend(["--wfd-go-intent", str(int(go_intent))])
    if rtsp_port != 7236:
        cmd.extend(["--wfd-rtsp-port", str(int(rtsp_port))])
    if rtp_source_port != 19002:
        cmd.extend(["--wfd-rtp-source-port", str(int(rtp_source_port))])
    if scan_timeout_s != 8:
        cmd.extend(["--wfd-timeout", str(int(scan_timeout_s))])
    if p2p_backend and p2p_backend != "nm":
        cmd.extend(["--wfd-p2p-backend", p2p_backend])
    # FluxCast solo acepta 1/6/11. Los 5 GHz se fijan por D-Bus antes de arrancar.
    if p2p_backend == "wpas" and p2p_channel is not None and es_canal_24(int(p2p_channel)):
        cmd.extend(["--wfd-p2p-channel", str(int(p2p_channel))])
    if media_pipeline and media_pipeline != "auto":
        cmd.extend(["--wfd-media-pipeline", media_pipeline])
    if wifi_interface:
        cmd.extend(["--wfd-interface", wifi_interface])
    if test_pattern:
        cmd.append("--wfd-test-pattern")
    return cmd


def escanear_pares(
    binario: str,
    *,
    timeout: float = 25.0,
    scan_timeout_s: int = 8,
    wifi_interface: str | None = None,
) -> list[WfdPeer]:
    cmd = [binario, "--protocol", "wfd", "--wfd-scan", "--wfd-timeout", str(int(scan_timeout_s))]
    if wifi_interface:
        cmd.extend(["--wfd-interface", wifi_interface])
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(timeout, float(scan_timeout_s) + 15),
            env=_entorno(),
        )
    except subprocess.TimeoutExpired as exc:
        raise StreamFailedError(
            "Miracast discovery did not respond in time.",
            consejo="Put the TV on Source → Remote Access → Screen Sharing.",
        ) from exc
    except OSError as exc:
        raise StreamFailedError("Could not run FluxCast.") from exc
    texto = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0 and not MAC_RE.search(texto):
        raise StreamFailedError(
            "FluxCast found no Miracast receiver.",
            consejo="On the TV: Source → Remote Access → Screen Sharing. The set only advertises in that mode.",
        )
    return _pares_desde_salida(texto)


def _pares_desde_salida(texto: str) -> list[WfdPeer]:
    pares: list[WfdPeer] = []
    vistos: set[str] = set()
    for linea in texto.splitlines():
        m = MAC_RE.search(linea)
        if not m:
            continue
        mac = m.group(1).lower()
        if mac in vistos:
            continue
        vistos.add(mac)
        resto = (linea[m.end() :] + " " + linea[: m.start()]).strip(" []-:\t")
        pares.append(WfdPeer(mac=mac, nombre=resto[:80]))
    return pares


def _entorno() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    display = env.get("DISPLAY") or ":1"
    env["DISPLAY"] = display
    # FluxCast solo detecta X11 si existe /tmp/.X<n>-lock. GDM a veces no lo crea.
    m = re.search(r":(\d+)", display)
    if m:
        lock = Path(f"/tmp/.X{m.group(1)}-lock")
        if not lock.exists():
            try:
                lock.write_text(str(os.getpid()) + "\n")
            except OSError:
                pass
    return env


def log_path() -> Path:
    return Path("/tmp/conexion-tv-fluxcast.log")


def cerrar_enlace_p2p() -> None:
    """Bring down the Wi-Fi Direct group and delete the temporary NetworkManager profile.

    Without this the TV stays joined to a group that no longer exists.
    """
    try:
        listado = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,UUID,TYPE", "connection", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        listado = None
    if listado is not None and listado.returncode == 0:
        for linea in (listado.stdout or "").splitlines():
            partes = linea.split(":")
            if len(partes) < 2:
                continue
            nombre, uuid = partes[0], partes[1]
            if "fluxcast" not in nombre.lower():
                continue
            subprocess.run(
                ["nmcli", "connection", "down", uuid],
                capture_output=True,
                timeout=8,
            )
            subprocess.run(
                ["nmcli", "connection", "delete", uuid],
                capture_output=True,
                timeout=8,
            )
    subprocess.run(
        ["nmcli", "device", "disconnect", "p2p-dev-wlp0s20f3"],
        capture_output=True,
        timeout=8,
    )


_TRADUCCION: tuple[tuple[str, str], ...] = (
    ("Connecting to", "Connecting over Wi-Fi Direct…"),
    ("P2P link is activated", "Direct link up. Waiting for the TV…"),
    ("Waiting for TV RTSP", "Waiting for RTSP negotiation (port 7236)…"),
    ("TV connected from", "TV joined the RTSP session."),
    ("Negotiated media mode:", "Agreed video mode:"),
    ("Selected video format:", "WFD format sent to the TV:"),
    ("PLAY accepted", "TV accepted the stream (PLAY)."),
    ("media stream started", "Picture and sound stream has started."),
    ("Latency probe: first RTP bytes after PLAY in", "First video data after PLAY:"),
    ("Latency probe: sender-path latency", "Time to first packet (handshake included):"),
    ("Sender health:", "Sender running:"),
    ("Using x11grab backend", "Capturing the desktop via X11."),
    ("Capturing audio", "Capturing audio:"),
    ("Scaling output", "Scaling the picture to"),
    ("RTP target", "RTP target:"),
    ("TV did not advertise AAC", "TV did not advertise AAC; sending video only."),
    ("TV did not advertise UIBC", "TV did not advertise remote input (UIBC)."),
    ("input server listening", "Remote input channel listening."),
    ("M16 keepalive", "TV keeps the session alive (keepalive)."),
    ("TV disconnected", "TV closed the session."),
    ("Stopping WFD session", "Closing the session (TEARDOWN and Wi-Fi Direct)…"),
    ("P2P device disconnect", "Direct link closed."),
    ("connection deactivate", "P2P connection deactivated."),
    ("Peer requested in connection is missing", "TV did not join the Wi-Fi Direct group."),
    ("ERROR:", "Error:"),
    ("Address already in use", "Port 7236 is busy with another session."),
    (
        "selected TV IP not found",
        "TV has no IP on the direct link; picture negotiation cannot start.",
    ),
)


def motivo_fallo_desde_log(texto: str) -> str | None:
    """Map a known process failure to a user-facing message."""
    if "Address already in use" in texto:
        return (
            "Port 7236 is busy with a previous mirror session. "
            "It will try to close it; if it still fails, press Stop sharing and retry."
        )
    if "wpa_supplicant P2P interface not found" in texto:
        return (
            "The wpa_supplicant backend cannot see the P2P interface (D-Bus denied). "
            "Set the P2P channel back to automatic or install the FluxCast "
            "policy for wpa_supplicant. NetworkManager can project without that."
        )
    if "Timed out waiting for NetworkManager" in texto:
        return (
            "NetworkManager did not activate Wi-Fi Direct in time. "
            "The TV is often still joined to the previous session."
        )
    if "selected TV IP not found" in texto:
        return (
            "Wi-Fi Direct opened, but the TV does not appear on that link "
            "and the picture does not start. Almost always it is not on "
            "Source → Remote Access → Screen Sharing, or the previous "
            "session left it hung: leave that screen and enter again."
        )
    if "Could not" in texto or "ERROR:" in texto:
        for linea in reversed(texto.splitlines()):
            if "ERROR:" in linea:
                return linea.split("ERROR:", 1)[-1].strip()
    return None


def es_fallo_p2p_reintentable(motivo: str) -> bool:
    """The first GO is often empty; a second attempt often joins."""
    return (
        "does not appear on that link" in motivo
        or "did not activate Wi-Fi Direct" in motivo
        or "selected TV IP not found" in motivo
        or "Timed out waiting for NetworkManager" in motivo
    )


def pids_fluxcast_wfd(*, excluir: int | None = None) -> list[int]:
    """FluxCast mirror processes (not --wfd-scan)."""
    encontrados: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return encontrados
    for entrada in proc.iterdir():
        if not entrada.name.isdigit():
            continue
        pid = int(entrada.name)
        if excluir is not None and pid == excluir:
            continue
        try:
            crudo = (entrada / "cmdline").read_bytes()
        except OSError:
            continue
        cmd = crudo.replace(b"\x00", b" ").decode("utf-8", errors="replace")
        if "fluxcast" not in cmd or "--protocol" not in cmd:
            continue
        if "wfd" not in cmd:
            continue
        if "--wfd-scan" in cmd:
            continue
        encontrados.append(pid)
    return encontrados


def extraer_estado_enlace(texto: str) -> LinkFacts:
    """Lee del log los hechos de capa 1–4 (IPs, modo, RTP), no los ajustes."""

    def _busca(patron: str) -> str:
        hallado = None
        for m in re.finditer(patron, texto):
            hallado = m.group(1).strip()
        return hallado or ""

    return LinkFacts(
        interface=_busca(r"(p2p-wlp[0-9a-z-]+):activated"),
        local_ip=_busca(r"local=([0-9.]+)"),
        tv_ip=_busca(r"TV connected from ([0-9.]+)") or _busca(r"TV=([0-9.]+)"),
        mode=_busca(r"Negotiated media mode:\s*(\S+)"),
        rtp=_busca(r"RTP target\s*:\s*(\S+)"),
        session_id=_busca(r"Session:\s*(\d+)"),
        advertised_video=_busca(r"wfd_video_formats:\s*(.+)"),
        advertised_audio=_busca(r"wfd_audio_codecs:\s*(.+)"),
        hdcp=_busca(r"wfd_content_protection:\s*(.+)"),
    )


def traducir_registro(texto: str, *, maximo: int = 24) -> str:
    """Turn the process log into clear user phrases, keeping only useful lines."""
    utiles: list[str] = []
    for linea in texto.splitlines():
        cruda = linea.strip()
        if not cruda or cruda.startswith("["):
            # FluxCast lines start with [FluxCast …]; we still want them.
            pass
        traducida = None
        for ingles, claro in _TRADUCCION:
            if ingles in cruda:
                resto = cruda.split(ingles, 1)[1].strip(" :")
                traducida = f"{claro} {resto}".strip() if resto else claro
                break
        if traducida:
            utiles.append(traducida)
    return "\n".join(utiles[-maximo:])
