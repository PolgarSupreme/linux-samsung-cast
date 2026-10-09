"""Adaptador de FluxCast.

FluxCast es GPL-3.0 y se invoca **como proceso externo**, nunca se importa.
Este paquete es el único sitio del árbol donde puede aparecer la palabra
`fluxcast` como dependencia de ejecución.
"""

from .adapter import FluxCastBackend

__all__ = ["FluxCastBackend"]
