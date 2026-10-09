"""Siembra la memoria de dispositivos con la ficha curada de `INFO/`.

La ficha es documentación escrita y revisada a mano; la memoria es el catálogo
que mantiene el programa. Sembrar una vez da a la aplicación todo lo que ya
sabemos sin tener que redescubrirlo, y a partir de ahí la memoria manda.
"""

from __future__ import annotations

import json
from pathlib import Path

from .device_memory import DeviceMemory, DeviceRecord
from .protocols import Protocol

# Nombres de protocolo en la ficha JSON -> identificadores internos.
_EQUIVALENCIAS = {
    "websocket_tizen": Protocol.TIZEN_WEBSOCKET,
    "miracast_wfd": Protocol.MIRACAST_WFD,
    "dlna_upnp": Protocol.DLNA_AVTRANSPORT,
    "wake_on_lan": Protocol.WAKE_ON_LAN,
    "dial": Protocol.DIAL,
    "airplay_2": Protocol.AIRPLAY2,
    "google_cast": Protocol.GOOGLE_CAST,
    "remote_access_rdp_vnc": Protocol.REMOTE_ACCESS_RDP,
}


def ruta_ficha_por_defecto() -> Path:
    """`INFO/tv_samsung.json`, relativo a la raíz del repositorio."""
    return Path(__file__).resolve().parents[2] / "INFO" / "tv_samsung.json"


def sembrar(memoria: DeviceMemory, ruta: Path | None = None) -> DeviceRecord | None:
    """Incorpora la ficha a la memoria. Devuelve el registro, o None si no hay ficha.

    Es idempotente: volver a sembrar no duplica el dispositivo ni falsea los
    contadores de intentos, porque solo escribe estados que la ficha declara
    como verificados.
    """
    ruta = ruta or ruta_ficha_por_defecto()
    if not ruta.exists():
        return None
    try:
        ficha = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    identidad = ficha.get("identidad", {})
    red = ficha.get("red", {})
    ids = ficha.get("identificadores", {})

    # Orden de preferencia para la clave: el UDN es más estable que una MAC,
    # porque no depende de por qué interfaz esté conectado el aparato.
    identificadores = [
        i
        for i in (
            ids.get("duid"),
            red.get("mac_wifi"),
            red.get("mac_ethernet"),
            ids.get("udn_mediarenderer"),
        )
        if i
    ]
    if not identificadores:
        return None

    registro = memoria.registrar(
        identificadores,
        nombre=identidad.get("nombre_amigable", ""),
        fabricante=identidad.get("fabricante", ""),
        modelo=identidad.get("codigo_modelo", ""),
        modelo_interno=identidad.get("modelo_interno", ""),
        plataforma=ficha.get("software", {}).get("sistema_operativo", ""),
        anio=identidad.get("anio"),
        ip=red.get("ip_actual"),
    )

    for nombre_ficha, bloque in (ficha.get("protocolos") or {}).items():
        protocolo = _EQUIVALENCIAS.get(nombre_ficha)
        if protocolo is None or not isinstance(bloque, dict):
            continue
        _sembrar_protocolo(registro, protocolo, bloque)

    return registro


def _sembrar_protocolo(registro: DeviceRecord, protocolo: Protocol, bloque: dict) -> None:
    """Traduce un bloque de la ficha al estado que le corresponde en memoria.

    Only three situations produce a state: verified working, confirmed absence,
    and advertised by the specification. Everything else stays `unknown`, which
    is honest.
    """
    mem = registro.memoria(protocolo)
    verificado = bool(bloque.get("verificado_en_dispositivo"))
    soportado = bloque.get("soportado")
    evidencia = bloque.get("_evidencia") or bloque.get("notas") or ""

    if verificado and soportado:
        if mem.exitos == 0:
            registro.anotar_exito(
                protocolo,
                evidencia=evidencia or "Verified during the initial survey",
                limitaciones=list(bloque.get("limitaciones_observadas", [])),
            )
    elif verificado and soportado is False:
        registro.marcar_no_soportado(
            protocolo, evidencia or "Confirmed absence on the device"
        )
    elif soportado:
        registro.anotar_anuncio(protocolo)

    datos = {
        clave: valor
        for clave, valor in bloque.items()
        if clave in ("servicios", "descriptor", "rest_info", "websocket", "mac_a_usar")
    }
    if datos:
        mem.datos.update(datos)
