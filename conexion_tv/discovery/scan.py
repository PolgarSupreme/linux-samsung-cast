"""Discovery of Samsung TVs on the local network.

Two independent leads that are merged:

1. Subnet sweep of port 8001 and `GET /api/v2/` to confirm Tizen.
2. SSDP for MediaRenderer (DLNA), DIAL, and Samsung itself.

Results are written to device memory: announcements, never successes.
An announcement does not claim the protocol works, only that the set publishes it.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from ipaddress import IPv4Interface, IPv4Network
from typing import Callable, Iterable

from conexion_tv.core.device_memory import DeviceMemory, DeviceRecord
from conexion_tv.core.net_policy import NonLocalNetworkError, exigir_host_local
from conexion_tv.core.protocols import Protocol

PUERTO_REST = 8001
PUERTO_DLNA = 9197
TIMEOUT_TCP = 0.6
TIMEOUT_HTTP = 2.0
TIMEOUT_SSDP = 3.0
SSDP_ADDR = ("239.255.255.250", 1900)
SSDP_ST = (
    "ssdp:all",
    "urn:schemas-upnp-org:device:MediaRenderer:1",
    "urn:dial-multiscreen-org:service:dial:1",
)


@dataclass(frozen=True)
class ScanHit:
    """Un aparato visto en un escaneo, todavía sin persistir."""

    ip: str
    identificadores: list[str]
    nombre: str = ""
    fabricante: str = ""
    modelo: str = ""
    modelo_interno: str = ""
    plataforma: str = ""
    anuncios: dict[Protocol, dict] = field(default_factory=dict)


def redes_locales() -> list[IPv4Network]:
    """Subredes IPv4 de interfaces activas, sin loopback ni docker."""
    redes: list[IPv4Network] = []
    for iface in _interfaces_ipv4():
        if iface.ip.is_loopback or iface.network.is_multicast:
            continue
        if str(iface.ip).startswith(("172.17.", "172.18.", "172.19.")):
            continue
        if iface.network.prefixlen < 16:
            continue
        if iface.network not in redes:
            redes.append(iface.network)
    return redes


def _interfaces_ipv4() -> list[IPv4Interface]:
    encontradas: list[IPv4Interface] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM):
            encontradas.append(IPv4Interface(f"{info[4][0]}/24"))
    except OSError:
        pass
    # Fuente más fiable: `ip -4 -o addr` si está disponible.
    try:
        import subprocess

        salida = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            text=True,
            timeout=2,
        )
        encontradas = []
        for linea in salida.splitlines():
            partes = linea.split()
            if "inet" in partes:
                cidr = partes[partes.index("inet") + 1]
                encontradas.append(IPv4Interface(cidr))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return encontradas


def _puerto_abierto(ip: str, puerto: int, timeout: float = TIMEOUT_TCP) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((ip, puerto)) == 0
    except OSError:
        return False
    finally:
        sock.close()


def consultar_api_v2(ip: str, *, opener: Callable[[str], bytes] | None = None) -> dict | None:
    try:
        exigir_host_local(ip, que="Tizen API probe")
    except NonLocalNetworkError:
        return None
    url = f"http://{ip}:{PUERTO_REST}/api/v2/"
    try:
        if opener is not None:
            bruto = opener(url)
        else:
            with urllib.request.urlopen(url, timeout=TIMEOUT_HTTP) as resp:
                bruto = resp.read()
        datos = json.loads(bruto.decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    dispositivo = datos.get("device") or {}
    if dispositivo.get("OS") != "Tizen" and dispositivo.get("type") != "Samsung SmartTV":
        if "Samsung" not in str(dispositivo.get("description", "")):
            return None
    return datos


def _hit_desde_api(ip: str, payload: dict) -> ScanHit:
    d = payload.get("device") or {}
    identificadores = [
        i
        for i in (
            d.get("duid") or d.get("id") or d.get("udn"),
            d.get("wifiMac"),
        )
        if i
    ]
    if not identificadores:
        identificadores = [f"ip:{ip}"]
    anuncios: dict[Protocol, dict] = {
        Protocol.TIZEN_WEBSOCKET: {
            "rest_info": f"http://{ip}:{PUERTO_REST}/api/v2/",
            "TokenAuthSupport": d.get("TokenAuthSupport"),
        }
    }
    return ScanHit(
        ip=ip,
        identificadores=identificadores,
        nombre=d.get("name") or payload.get("name") or "",
        fabricante="Samsung",
        modelo=d.get("modelName") or "",
        modelo_interno=d.get("model") or "",
        plataforma=d.get("OS") or "Tizen",
        anuncios=anuncios,
    )


def barrer_rest(
    hosts: Iterable[str],
    *,
    opener: Callable[[str], bytes] | None = None,
    workers: int = 64,
) -> list[ScanHit]:
    """Prueba el puerto 8001 y, si responde, lee la API v2."""
    encontrados: list[ScanHit] = []

    def probar(ip: str) -> ScanHit | None:
        if not _puerto_abierto(ip, PUERTO_REST):
            return None
        payload = consultar_api_v2(ip, opener=opener)
        if payload is None:
            return None
        return _hit_desde_api(ip, payload)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = {pool.submit(probar, ip): ip for ip in hosts}
        for futuro in as_completed(futuros):
            hit = futuro.result()
            if hit is not None:
                encontrados.append(hit)
    return encontrados


def _ssdp_mensaje(st: str) -> bytes:
    return (
        "\r\n".join(
            [
                "M-SEARCH * HTTP/1.1",
                f"HOST: {SSDP_ADDR[0]}:{SSDP_ADDR[1]}",
                'MAN: "ssdp:discover"',
                "MX: 2",
                f"ST: {st}",
                "",
                "",
            ]
        ).encode()
    )


def descubrir_ssdp(*, timeout: float = TIMEOUT_SSDP) -> dict[str, set[str]]:
    """IP -> conjunto de ST/Location observados."""
    vistos: dict[str, set[str]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        for st in SSDP_ST:
            sock.sendto(_ssdp_mensaje(st), SSDP_ADDR)
        import time

        fin = time.time() + timeout
        while time.time() < fin:
            try:
                data, addr = sock.recvfrom(65507)
            except socket.timeout:
                break
            except OSError:
                break
            ip = addr[0]
            texto = data.decode("utf-8", errors="replace")
            marcas = vistos.setdefault(ip, set())
            for linea in texto.splitlines():
                baja = linea.lower()
                if baja.startswith(("st:", "location:", "server:")):
                    marcas.add(linea.strip())
    finally:
        sock.close()
    return vistos


def _anuncios_desde_ssdp(marcas: set[str]) -> dict[Protocol, dict]:
    texto = "\n".join(marcas).lower()
    anuncios: dict[Protocol, dict] = {}
    if "mediarenderer" in texto or "avtransport" in texto:
        anuncios[Protocol.DLNA_AVTRANSPORT] = {}
        for linea in marcas:
            if linea.lower().startswith("location:") and ":9197" in linea:
                anuncios[Protocol.DLNA_AVTRANSPORT]["descriptor"] = linea.split(":", 1)[1].strip()
    if "dial" in texto:
        anuncios[Protocol.DIAL] = {}
    if "samsung" in texto and Protocol.TIZEN_WEBSOCKET not in anuncios:
        anuncios[Protocol.TIZEN_WEBSOCKET] = {}
    return anuncios


def escanear(
    memoria: DeviceMemory,
    *,
    red: IPv4Network | None = None,
    opener: Callable[[str], bytes] | None = None,
    incluir_ssdp: bool = True,
) -> list[DeviceRecord]:
    """Escanea, fusiona con la memoria y devuelve los registros actualizados."""
    redes = [red] if red is not None else redes_locales()
    hosts: list[str] = []
    for r in redes:
        # Evitar barridos enormes: /16 son 65k hosts y no es una LAN doméstica.
        if r.num_addresses > 512:
            continue
        hosts.extend(str(ip) for ip in r.hosts())

    hits = {h.ip: h for h in barrer_rest(hosts, opener=opener)}

    if incluir_ssdp:
        for ip, marcas in descubrir_ssdp().items():
            extra = _anuncios_desde_ssdp(marcas)
            if ip in hits:
                combinados = dict(hits[ip].anuncios)
                combinados.update(extra)
                hits[ip] = ScanHit(
                    ip=hits[ip].ip,
                    identificadores=hits[ip].identificadores,
                    nombre=hits[ip].nombre,
                    fabricante=hits[ip].fabricante,
                    modelo=hits[ip].modelo,
                    modelo_interno=hits[ip].modelo_interno,
                    plataforma=hits[ip].plataforma,
                    anuncios=combinados,
                )
            elif extra:
                hits[ip] = ScanHit(
                    ip=ip,
                    identificadores=[f"ip:{ip}"],
                    anuncios=extra,
                )

    registros: list[DeviceRecord] = []
    for hit in hits.values():
        registro = memoria.registrar(
            hit.identificadores,
            nombre=hit.nombre,
            fabricante=hit.fabricante,
            modelo=hit.modelo,
            modelo_interno=hit.modelo_interno,
            plataforma=hit.plataforma,
            ip=hit.ip,
        )
        for protocolo, datos in hit.anuncios.items():
            registro.anotar_anuncio(protocolo, datos=datos or None)
        registros.append(registro)
    memoria.guardar()
    return registros
