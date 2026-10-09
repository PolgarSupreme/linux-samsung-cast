"""Live Source → Media → Destination graph: status and controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Column colors (reasonable light/dark via luminosity).
_COL = {
    "source": ("#2563eb", "#dbeafe"),
    "media": ("#16a34a", "#dcfce7"),
    "destination": ("#db2777", "#fce7f3"),
}


class _ColumnaFlujo(QFrame):
    def __init__(self, clave: str, titulo: str, subtitulo: str) -> None:
        super().__init__()
        self._clave = clave
        borde, fondo = _COL[clave]
        self.setObjectName(f"col_{clave}")
        self.setStyleSheet(
            f"QFrame#col_{clave} {{"
            f" border: 2px solid {borde};"
            f" border-radius: 8px;"
            f" background: {fondo};"
            f"}}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        cabeza = QHBoxLayout()
        tit = QLabel(f"<b>{titulo}</b>")
        tit.setTextFormat(Qt.TextFormat.RichText)
        self._estado = QLabel("—")
        self._estado.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._pintar_pill("idle", "idle")
        cabeza.addWidget(tit)
        cabeza.addStretch(1)
        cabeza.addWidget(self._estado)
        lay.addLayout(cabeza)

        sub = QLabel(subtitulo)
        sub.setWordWrap(True)
        f = sub.font()
        f.setPointSize(max(8, f.pointSize() - 1))
        sub.setFont(f)
        lay.addWidget(sub)

        self._cuerpo = QVBoxLayout()
        self._cuerpo.setSpacing(6)
        lay.addLayout(self._cuerpo)
        lay.addStretch(1)

    @property
    def cuerpo(self) -> QVBoxLayout:
        return self._cuerpo

    def set_estado(self, tono: str, texto: str) -> None:
        self._pintar_pill(tono, texto)

    def _pintar_pill(self, tono: str, texto: str) -> None:
        colores = {
            "ok": ("#166534", "#bbf7d0"),
            "live": ("#1d4ed8", "#bfdbfe"),
            "warn": ("#9a3412", "#fed7aa"),
            "idle": ("#374151", "#e5e7eb"),
            "err": ("#991b1b", "#fecaca"),
        }
        fg, bg = colores.get(tono, colores["idle"])
        self._estado.setText(texto)
        self._estado.setStyleSheet(
            f"QLabel {{ color: {fg}; background: {bg}; border-radius: 8px; "
            f"padding: 2px 8px; font-weight: 600; }}"
        )


class _Flecha(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(28)
        self.setMinimumHeight(40)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#64748b"))
        pen.setWidth(2)
        p.setPen(pen)
        mid = self.height() // 2
        p.drawLine(2, mid, self.width() - 6, mid)
        p.drawLine(self.width() - 14, mid - 6, self.width() - 4, mid)
        p.drawLine(self.width() - 14, mid + 6, self.width() - 4, mid)


class GrafoFlujo(QWidget):
    """Three Source / Media / Destination columns with status and controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(6)

        leyenda = QLabel(
            "<b>Projection flow</b> — live status; controls in each column "
            "change Source, Media, or Destination."
        )
        leyenda.setWordWrap(True)
        leyenda.setTextFormat(Qt.TextFormat.RichText)
        raiz.addWidget(leyenda)

        fila = QHBoxLayout()
        fila.setSpacing(4)
        self.source = _ColumnaFlujo(
            "source",
            "SOURCE",
            "Origin: PC monitor and audio.",
        )
        self.media = _ColumnaFlujo(
            "media",
            "MEDIA",
            "Pipeline: virtual bus, codec, and Wi-Fi Direct.",
        )
        self.destination = _ColumnaFlujo(
            "destination",
            "DESTINATION",
            "Destination: TV and, if applicable, PC speakers.",
        )
        fila.addWidget(self.source, 1)
        fila.addWidget(_Flecha())
        fila.addWidget(self.media, 1)
        fila.addWidget(_Flecha())
        fila.addWidget(self.destination, 1)
        raiz.addLayout(fila)

        self._nota = QLabel("")
        self._nota.setWordWrap(True)
        f = self._nota.font()
        f.setPointSize(max(8, f.pointSize() - 1))
        self._nota.setFont(f)
        raiz.addWidget(self._nota)

    def set_nota(self, texto: str) -> None:
        self._nota.setText(texto)

    def actualizar_estados(
        self,
        *,
        proyectando: bool,
        error: bool = False,
        p2p: bool = False,
        audio_ruta: str = "tv",
        bus_activo: bool = False,
        monitor: str = "",
        modo: str = "",
        bitrate_kbps: int = 0,
        tele: str = "",
    ) -> None:
        if error:
            self.source.set_estado("err", "error")
            self.media.set_estado("err", "error")
            self.destination.set_estado("err", "error")
        elif proyectando:
            self.source.set_estado("live", "capturing")
            self.media.set_estado(
                "ok" if p2p or bus_activo else "live",
                "live" if p2p else "encoding",
            )
            dest = "TV"
            if audio_ruta == "both":
                dest = "TV+PC"
            elif audio_ruta == "pc":
                dest = "PC only"
            self.destination.set_estado("ok", dest)
        else:
            self.source.set_estado("idle", "ready")
            self.media.set_estado("idle", "idle")
            self.destination.set_estado("idle", "no session")

        partes = []
        if monitor:
            partes.append(f"video source {monitor}")
        if modo:
            partes.append(modo)
        if bitrate_kbps:
            partes.append(f"{bitrate_kbps // 1000} Mb/s")
        if tele:
            partes.append(tele)
        if partes:
            self.set_nota(" · ".join(partes))
