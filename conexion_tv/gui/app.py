from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from .window import MainWindow


def run_app(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Conexion TV")
    ventana = MainWindow()
    ventana.show()
    return app.exec()
