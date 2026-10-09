"""Rutas de configuración y datos, respetando XDG."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(variable: str, fallback: Path) -> Path:
    valor = os.environ.get(variable)
    return Path(valor) if valor else fallback


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / "conexion_tv"


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / "conexion_tv"


def token_path(clave_dispositivo: str) -> Path:
    """Fichero del token Tizen de un dispositivo, con nombre seguro para el disco."""
    seguro = "".join(c if c.isalnum() or c in "-_." else "_" for c in clave_dispositivo)
    return config_dir() / "tokens" / f"{seguro}.txt"


def asegurar_directorio(ruta: Path, *, modo: int = 0o700) -> None:
    ruta.mkdir(parents=True, exist_ok=True)
    try:
        ruta.chmod(modo)
    except OSError:
        pass
