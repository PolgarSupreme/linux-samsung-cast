"""La GPL-3.0 de FluxCast no puede filtrarse al resto del código por un import."""

from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "conexion_tv"
PERMITIDO = RAIZ / "mirror" / "backends" / "fluxcast"


def _imports_de(path: Path) -> list[str]:
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nombres: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.extend(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.append(nodo.module)
    return nombres


def test_ningun_modulo_fuera_del_adaptador_importa_fluxcast():
    filtraciones = []
    for path in RAIZ.rglob("*.py"):
        if PERMITIDO in path.parents or path.parent == PERMITIDO:
            continue
        for nombre in _imports_de(path):
            raiz = nombre.split(".", 1)[0]
            if raiz == "fluxcast":
                filtraciones.append(f"{path.relative_to(RAIZ)} importa {nombre}")
    assert filtraciones == []
