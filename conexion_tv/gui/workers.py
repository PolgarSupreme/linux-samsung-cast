"""Trabajo de red fuera del hilo gráfico."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class PuenteEventos(QObject):
    """Reenvía eventos del backend al hilo de la interfaz."""

    recibido = pyqtSignal(object)


class FuncionEnHilo(QThread):
    """Ejecuta una función y emite el resultado o el error ya traducido."""

    listo = pyqtSignal(object)
    fallo = pyqtSignal(str)

    def __init__(self, funcion: Callable, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._funcion = funcion

    def run(self) -> None:
        try:
            self.listo.emit(self._funcion())
        except Exception as exc:
            self.fallo.emit(str(exc))
