"""Last projection settings chosen by the user."""

from __future__ import annotations

import json
from dataclasses import asdict, replace

from conexion_tv.core.paths import asegurar_directorio, config_dir
from conexion_tv.mirror.base import StreamConfig
from conexion_tv.mirror.caudal import acotar_bitrate


def _ruta():
    return config_dir() / "proyeccion.json"


def cargar() -> StreamConfig:
    ruta = _ruta()
    if not ruta.is_file():
        return StreamConfig()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return StreamConfig()
    if not isinstance(datos, dict):
        return StreamConfig()
    conocidos = {
        campo: getattr(StreamConfig(), campo) for campo in StreamConfig.__dataclass_fields__
    }
    filtrado = {k: datos[k] for k in conocidos if k in datos}
    for clave in ("audio_device", "monitor", "wifi_interface"):
        if filtrado.get(clave) == "":
            filtrado[clave] = None
    if filtrado.get("go_intent") == "":
        filtrado["go_intent"] = None
    if filtrado.get("p2p_channel") == "":
        filtrado["p2p_channel"] = None
    try:
        cfg = StreamConfig(**{**conocidos, **filtrado})
    except TypeError:
        return StreamConfig()
    return replace(cfg, bitrate_kbps=acotar_bitrate(cfg.bitrate_kbps))


def guardar(config: StreamConfig) -> None:
    asegurar_directorio(config_dir())
    _ruta().write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
