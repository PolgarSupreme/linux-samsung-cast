"""Mirror tab: pre-session settings, live status, and reconfiguration."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from conexion_tv.gui.grafo_flujo import GrafoFlujo
from conexion_tv.gui.seccion import SeccionColapsable


class _ComboSinRueda(QComboBox):
    """Panel scroll must not change mode or capture."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class _SpinSinRueda(QSpinBox):
    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()

from conexion_tv.core.events import ConnectionState, StateChanged, UserMessage
from conexion_tv.mirror.base import LinkFacts, StreamConfig
from conexion_tv.mirror.remote_display import audio_y_silencio, destino_desde_config
from conexion_tv.mirror.caudal import (
    BITRATE_MAX_KBPS,
    BITRATE_MIN_KBPS,
    CAUDAL_PERSONALIZADO,
    CAUDALES,
    caudal_por_id,
    caudal_por_kbps,
    pista_caudal,
)
from conexion_tv.mirror.firewall import puerto_abierto
from conexion_tv.mirror.p2p_channel import MATCH_AP_5GHZ
from conexion_tv.mirror.prefs import cargar as cargar_prefs
from conexion_tv.mirror.prefs import guardar as guardar_prefs
from conexion_tv.mirror.sources import fuentes_audio, interfaces_wifi, pantallas
from conexion_tv.mirror.video_modes import (
    MODO_POR_DEFECTO,
    MODOS_VIDEO,
    modo_desde_tamano,
    modo_por_id,
)

_ESTADO = {
    ConnectionState.DISCONNECTED: "No mirror session",
    ConnectionState.DISCOVERING: "Looking for the TV over Wi-Fi Direct…",
    ConnectionState.PAIRING: "Pairing (direct link and port 7236)…",
    ConnectionState.CONNECTED: "Link ready; starting the picture…",
    ConnectionState.STREAMING: "Projecting",
    ConnectionState.ERROR: "Error",
}

_CAPTURAS = (
    (
        "x11",
        "Direct X11",
        "Captures this graphical session with no extra dialog. The path that already worked.",
    ),
    (
        "portal",
        "Desktop portal",
        "GNOME asks permission to share. Meant for Wayland; on X11 almost never needed.",
    ),
    (
        "auto",
        "Automatic",
        "The backend chooses capture. If it fails, try Direct X11.",
    ),
    (
        "gstreamer",
        "GStreamer over X11",
        "Plan B if the picture stays black with normal capture.",
    ),
)

_DESTINOS_AUDIO = (
    (
        "tv",
        "TV only",
        "Apps play into a virtual sink; that audio goes to the TV. "
        "PC speakers get no loopback.",
    ),
    (
        "both",
        "Computer and TV",
        "Same virtual sink toward the TV, plus loopback to your speakers. "
        "PC and TV hear the same without muting HDMI.",
    ),
    (
        "pc",
        "Computer only",
        "No audio sent over Miracast (restarts the mirror when enabled).",
    ),
)


def _pista(texto: str) -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setWordWrap(True)
    fuente = etiqueta.font()
    fuente.setPointSize(max(8, fuente.pointSize() - 1))
    etiqueta.setFont(fuente)
    return etiqueta


def _columna(titulo: str, *widgets: QWidget | None) -> QWidget:
    """One field (title + control + hint) taking half the row."""
    caja = QWidget()
    lay = QVBoxLayout(caja)
    lay.setContentsMargins(0, 0, 12, 0)
    lay.setSpacing(4)
    if titulo:
        lay.addWidget(QLabel(f"<b>{titulo}</b>"))
    for w in widgets:
        if w is None:
            continue
        if hasattr(w, "setSizePolicy"):
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(w)
    lay.addStretch(1)
    return caja


def _campo_compacto(titulo: str, *widgets: QWidget) -> QWidget:
    """Stacked field for a graph column."""
    caja = QWidget()
    lay = QVBoxLayout(caja)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lay.addWidget(QLabel(f"<b>{titulo}</b>"))
    for w in widgets:
        if hasattr(w, "setSizePolicy"):
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(w)
    return caja


def _dos(destino: QVBoxLayout, izq: QWidget, der: QWidget | None = None) -> None:
    fila = QHBoxLayout()
    fila.setSpacing(8)
    fila.addWidget(izq, 1)
    fila.addWidget(der if der is not None else QWidget(), 1)
    destino.addLayout(fila)


class PanelPantalla(QWidget):
    compartir = pyqtSignal()
    detener = pyqtSignal()
    aplicar = pyqtSignal()
    limpiar_enlace = pyqtSignal()
    silencio_local_cambiado = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._estado = ConnectionState.DISCONNECTED
        self._proyectando = False
        self._detalle_backend = ""
        self._modo_id_prev: str | None = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        interior = QWidget()
        scroll.setWidget(interior)
        raiz_ext = QVBoxLayout(self)
        raiz_ext.setContentsMargins(0, 0, 0, 0)
        raiz_ext.addWidget(scroll)
        raiz = QVBoxLayout(interior)

        pasos = QLabel(
            "<b>Before sharing</b><ol>"
            "<li>On the TV: <b>Source</b> → <b>Remote Access</b> → "
            "<b>Screen Sharing</b> (not Remote PC). The computer "
            "<i>does not</i> appear in that list: ignore the Windows 10 text.</li>"
            "<li>Adjust Source / Media / Destination and press <b>Share screen</b>.</li>"
            "<li>Accept the firewall prompt if it appears, and the connection on the TV.</li>"
            "</ol>"
        )
        pasos.setWordWrap(True)
        pasos.setTextFormat(Qt.TextFormat.RichText)
        raiz.addWidget(pasos)

        self._crear_controles()
        self._grafo = GrafoFlujo()
        self._montar_grafo()
        raiz.addWidget(self._grafo)

        raiz.addWidget(self._caja_acciones())
        raiz.addWidget(self._caja_estado())
        raiz.addWidget(self._caja_enlace())
        raiz.addWidget(self._caja_calidad())
        raiz.addWidget(self._caja_audio())
        raiz.addWidget(self._caja_captura())
        raiz.addWidget(self._caja_protocolo())
        raiz.addWidget(self._caja_registro())
        raiz.addStretch()

        self._cargar_prefs()
        self._actualizar_pistas()
        self._refrescar_firewall()
        self._refrescar_grafo()

        self._reloj = QTimer(self)
        self._reloj.setInterval(1200)
        self._reloj.timeout.connect(self._refrescar_firewall)
        self._reloj.start()

    def _crear_controles(self) -> None:
        """Create widgets once; the graph and sections reuse them."""
        self._monitor = _ComboSinRueda()
        self._rellenar_monitores()
        self._captura = _ComboSinRueda()
        for ident, etiqueta, _exp in _CAPTURAS:
            self._captura.addItem(etiqueta, ident)
        self._lbl_captura = _pista("")
        self._captura.currentIndexChanged.connect(self._al_cambiar_captura)
        self._monitor.currentIndexChanged.connect(self._refrescar_grafo)

        self._fuente = _ComboSinRueda()
        self._rellenar_fuentes()

        self._modo = _ComboSinRueda()
        for modo in MODOS_VIDEO:
            self._modo.addItem(modo.etiqueta, modo.id)
        self._lbl_modo = _pista("")
        self._caudal = _ComboSinRueda()
        for preset in CAUDALES:
            self._caudal.addItem(preset.etiqueta, preset.id)
        self._caudal.addItem("Custom", CAUDAL_PERSONALIZADO)
        self._bitrate = _SpinSinRueda()
        self._bitrate.setRange(BITRATE_MIN_KBPS, BITRATE_MAX_KBPS)
        self._bitrate.setSingleStep(500)
        self._bitrate.setSuffix(" kb/s")
        self._lbl_caudal = _pista("")
        self._modo.currentIndexChanged.connect(self._al_cambiar_modo)
        self._caudal.currentIndexChanged.connect(self._al_cambiar_caudal)
        self._bitrate.valueChanged.connect(self._al_cambiar_bitrate)

        self._destino_audio = _ComboSinRueda()
        for ident, etiqueta, _exp in _DESTINOS_AUDIO:
            self._destino_audio.addItem(etiqueta, ident)
        self._lbl_destino = _pista("")
        self._destino_audio.currentIndexChanged.connect(self._al_cambiar_destino_audio)

        self._pipeline = _ComboSinRueda()
        self._pipeline.addItem("Automatic (ffmpeg for the desktop)", "auto")
        self._pipeline.addItem("ffmpeg (the one that already painted)", "ffmpeg")
        self._pipeline.addItem("GStreamer (plan B if the screen is black)", "gst")

    def _montar_grafo(self) -> None:
        self._grafo.source.cuerpo.addWidget(
            _campo_compacto(
                "Display",
                self._monitor,
                _pista("Monitor captured toward the TV."),
            )
        )
        self._grafo.source.cuerpo.addWidget(
            _campo_compacto("Capture method", self._captura)
        )
        self._grafo.source.cuerpo.addWidget(
            _campo_compacto(
                "Audio source",
                self._fuente,
                _pista("Pulse output whose .monitor FluxCast reads (via virtual bus)."),
            )
        )

        self._grafo.media.cuerpo.addWidget(
            _campo_compacto("Resolution and fps", self._modo)
        )
        self._grafo.media.cuerpo.addWidget(
            _campo_compacto("Bitrate", self._caudal, self._bitrate)
        )
        self._grafo.media.cuerpo.addWidget(
            _campo_compacto("Pipeline", self._pipeline)
        )
        self._grafo.media.cuerpo.addWidget(
            _pista(
                "If picture or sound drop out: lower the bitrate or try "
                "720p30. FluxCast sets the VBV buffer to 2× the bitrate on "
                "Samsung (~2 s); there is no separate buffer dial. More buffer "
                "adds wait, it does not fix dropouts from a saturated radio."
            )
        )

        self._grafo.destination.cuerpo.addWidget(
            _campo_compacto("Where you hear it", self._destino_audio)
        )
        self._lbl_dest_vivo = QLabel("TV: no session")
        self._lbl_dest_vivo.setWordWrap(True)
        self._grafo.destination.cuerpo.addWidget(self._lbl_dest_vivo)
        self._grafo.destination.cuerpo.addWidget(
            _pista(
                "TV only = virtual sink without loopback. Both = loopback to "
                "HDMI. PC only = no Miracast AAC."
            )
        )

    def _caja_estado(self) -> SeccionColapsable:
        caja = SeccionColapsable("Connection status", abierta=True)
        lay = caja.cuerpo
        self._lbl_estado = QLabel(_ESTADO[ConnectionState.DISCONNECTED])
        self._lbl_estado.setWordWrap(True)
        self._lbl_mensaje = QLabel(
            "No session yet. The mirror goes over Wi-Fi Direct, not the router."
        )
        self._lbl_mensaje.setWordWrap(True)
        self._lbl_firewall = QLabel()
        self._lbl_firewall.setWordWrap(True)
        self._chk_firewall = QCheckBox(
            "Open firewall port 7236 when sharing"
        )
        self._chk_firewall.setChecked(True)
        self._lbl_enlace = QLabel("Direct link: no group yet.")
        self._lbl_enlace.setWordWrap(True)
        self._lbl_negociado = QLabel("Negotiation: waiting for M1–PLAY.")
        self._lbl_negociado.setWordWrap(True)
        _dos(lay, self._lbl_estado, self._lbl_mensaje)
        _dos(lay, self._lbl_enlace, self._lbl_negociado)
        _dos(lay, self._lbl_firewall, self._chk_firewall)
        lay.addWidget(_pista(
            "Status, IPs and agreed mode are not editable: they change when connecting. "
            "Port 7236 opens only during the session (pkexec) and closes when you stop."
        ))
        return caja

    def _caja_enlace(self) -> SeccionColapsable:
        caja = SeccionColapsable("Wi-Fi Direct link (layer 1)", abierta=True)
        lay = caja.cuerpo
        self._iface = _ComboSinRueda()
        for op in interfaces_wifi():
            self._iface.addItem(op.etiqueta, op.id)
        self._p2p_backend = _ComboSinRueda()
        self._p2p_backend.addItem("NetworkManager (the one that already worked)", "nm")
        self._p2p_backend.addItem("Direct wpa_supplicant (experimental)", "wpas")
        self._go = _ComboSinRueda()
        self._go.addItem("Do not force — NetworkManager decides", "")
        self._go.addItem("PC as group owner (15) — as in the good sessions", "15")
        self._go.addItem("TV as group owner (0) — what FluxCast asks for", "0")
        self._canal = _ComboSinRueda()
        self._canal.addItem("Automatic (driver chooses; often 2.4 GHz)", "")
        self._canal.addItem(
            "Prefer 5 GHz · same channel as the router",
            str(MATCH_AP_5GHZ),
        )
        self._canal.addItem("Force channel 36 (5 GHz)", "36")
        self._canal.addItem("Force channel 40 (5 GHz)", "40")
        self._canal.addItem("Force channel 44 (5 GHz)", "44")
        self._canal.addItem("Force channel 48 (5 GHz)", "48")
        self._canal.addItem("Force channel 1 (2.4 GHz)", "1")
        self._canal.addItem("Force channel 6 (2.4 GHz)", "6")
        self._canal.addItem("Force channel 11 (2.4 GHz)", "11")
        self._timeout = _SpinSinRueda()
        self._timeout.setRange(5, 30)
        self._timeout.setValue(8)
        self._timeout.setSuffix(" s")
        self.btn_limpiar = QPushButton("Clear Direct link")
        self.btn_limpiar.clicked.connect(self.limpiar_enlace.emit)
        self._p2p_backend.currentIndexChanged.connect(self._al_cambiar_p2p)
        _dos(
            lay,
            _columna(
                "Wi-Fi radio",
                self._iface,
                _pista("With a single antenna it time-shares between the router and Direct."),
            ),
            _columna(
                "How the group is created",
                self._p2p_backend,
                _pista("NetworkManager is the verified path. wpa_supplicant can force 2.4 GHz."),
            ),
        )
        _dos(
            lay,
            _columna(
                "Who owns the group (GO intent)",
                self._go,
                _pista("In good sessions the PC was 10.42.0.1 and the TV a client. NM sometimes ignores this value."),
            ),
            _columna(
                "P2P channel",
                self._canal,
                _pista(
                    "5 GHz needs D-Bus permission for wpa_supplicant (FluxCast "
                    "policy). Without it the program falls back to automatic "
                    "NetworkManager. Same channel as the router = fewer radio hops."
                ),
            ),
        )
        _dos(
            lay,
            _columna(
                "Direct scan wait",
                self._timeout,
                _pista("Seconds searching for WFD peers. 8 s was enough on Screen Sharing."),
            ),
            _columna(
                "Session leftovers",
                self.btn_limpiar,
                _pista("SIGINT + TEARDOWN. Do not press this while mirroring."),
            ),
        )
        self._al_cambiar_p2p()
        return caja

    def _caja_calidad(self) -> SeccionColapsable:
        caja = SeccionColapsable("Picture · detail", abierta=False)
        lay = caja.cuerpo
        lay.addWidget(self._lbl_modo)
        lay.addWidget(self._lbl_caudal)
        lay.addWidget(
            _pista(
                "Resolution and bitrate are edited in the Media column of the graph. "
                "Dropouts (choppy audio/video) almost never get fixed by "
                "enlarging a buffer: on Samsung FluxCast already uses VBV = 2× "
                "bitrate. If Direct saturates, lower Mb/s or the mode (e.g. "
                "720p30)."
            )
        )
        return caja

    def _caja_audio(self) -> SeccionColapsable:
        caja = SeccionColapsable("Sound · detail", abierta=False)
        lay = caja.cuerpo
        lay.addWidget(self._lbl_destino)
        lay.addWidget(
            _pista(
                "Destination and source are edited in Source / Destination of the graph. "
                "The HDMI monitor is the one heard on PC and TV."
            )
        )
        return caja

    def _caja_captura(self) -> SeccionColapsable:
        caja = SeccionColapsable("Capture · detail", abierta=False)
        lay = caja.cuerpo
        lay.addWidget(self._lbl_captura)
        lay.addWidget(
            _pista(
                "Display and method are in the Source column. Direct X11 is "
                "verified; portal is for Wayland."
            )
        )
        return caja

    def _caja_protocolo(self) -> SeccionColapsable:
        caja = SeccionColapsable("RTSP and media negotiation (layers 2–4)", abierta=False)
        lay = caja.cuerpo
        self._lbl_m3 = _pista(
            "When connected, here you will see what the TV advertises in M3 "
            "(formats, audio, HDCP). That comes from the TV; we choose in M4."
        )
        self._rtsp = _SpinSinRueda()
        self._rtsp.setRange(1024, 65535)
        self._rtsp.setValue(7236)
        self._rtp = _SpinSinRueda()
        self._rtp.setRange(1024, 65534)
        self._rtp.setValue(19002)
        self._chk_patron = QCheckBox("Send a test pattern instead of the desktop")
        self._chk_uibc = QCheckBox("Accept remote input from the TV (experimental)")
        lay.addWidget(self._lbl_m3)
        _dos(
            lay,
            _columna(
                "RTSP port (M1–PLAY)",
                self._rtsp,
                _pista("7236 is the Wi-Fi Display port. The TV connects to us; its 7236 rejects."),
            ),
            _columna(
                "Local outbound RTP port",
                self._rtp,
                _pista("Video leaves from here. The TV's port is told in M3."),
            ),
        )
        _dos(
            lay,
            _columna(
                "Media pipeline",
                _pista("The pipeline is chosen in the Media column of the graph."),
            ),
            _columna(
                "Tests",
                self._chk_patron,
                _pista("Generated pattern instead of the desktop, to see if capture or the link fails."),
            ),
        )
        hdcp = QLabel("HDCP: sending «none». This model accepted it (advertises HDCP 2.1).")
        hdcp.setWordWrap(True)
        codec = QLabel(
            "M4 video: H.264 Constrained Baseline (libx264). Only profile the TV advertised."
        )
        codec.setWordWrap(True)
        _dos(lay, hdcp, codec)
        _dos(
            lay,
            _columna(
                "Remote input",
                self._chk_uibc,
                _pista("UIBC (7239): the TV remote might move the cursor. Unverified; leave it off."),
            ),
            None,
        )
        return caja

    def _caja_acciones(self) -> SeccionColapsable:
        caja = SeccionColapsable("Session", abierta=True)
        lay = caja.cuerpo
        fila = QHBoxLayout()
        self.btn_compartir = QPushButton("Share screen")
        self.btn_aplicar = QPushButton("Apply changes")
        self.btn_detener = QPushButton("Stop sharing")
        self.btn_compartir.setEnabled(False)
        self.btn_aplicar.setEnabled(False)
        self.btn_detener.setEnabled(False)
        self.btn_compartir.clicked.connect(self.compartir.emit)
        self.btn_aplicar.clicked.connect(self.aplicar.emit)
        self.btn_detener.clicked.connect(self.detener.emit)
        fila.addWidget(self.btn_compartir)
        fila.addWidget(self.btn_aplicar)
        fila.addWidget(self.btn_detener)
        fila.addStretch()
        lay.addLayout(fila)
        lay.addWidget(_pista(
            "Settings are sent when connecting. Mid-session, «Apply "
            "changes» briefly stops the mirror and renegotiates with "
            "the new values (Miracast cannot change resolution or "
            "bitrate live)."
        ))
        return caja

    def _caja_registro(self) -> SeccionColapsable:
        caja = SeccionColapsable("What is happening", abierta=False)
        lay = caja.cuerpo
        self._registro = QTextEdit()
        self._registro.setReadOnly(True)
        self._registro.setMinimumHeight(140)
        lay.addWidget(self._registro)
        lay.addWidget(_pista(
            "Negotiation and send phrases. They show whether the TV "
            "accepted PLAY, which mode was agreed, and whether data is "
            "flowing. This is not the latency you see on the glass."
        ))
        return caja

    def _rellenar_fuentes(self) -> None:
        self._fuente.clear()
        for op in fuentes_audio():
            self._fuente.addItem(op.etiqueta, op.id)

    def _rellenar_monitores(self) -> None:
        self._monitor.clear()
        for op in pantallas():
            self._monitor.addItem(op.etiqueta, op.id)

    def _al_cambiar_modo(self) -> None:
        modo = modo_por_id(self._modo.currentData() or MODO_POR_DEFECTO)
        self._lbl_modo.setText(modo.explicacion)
        anterior = modo_por_id(self._modo_id_prev) if self._modo_id_prev else None
        actual = int(self._bitrate.value())
        if anterior is None or actual == anterior.bitrate_sugerido_kbps:
            self._bitrate.blockSignals(True)
            self._bitrate.setValue(modo.bitrate_sugerido_kbps)
            self._bitrate.blockSignals(False)
            self._sincronizar_combo_caudal()
        self._modo_id_prev = modo.id
        self._actualizar_pista_caudal()
        self._refrescar_grafo()

    def _al_cambiar_caudal(self) -> None:
        preset = caudal_por_id(self._caudal.currentData() or "")
        if preset is not None:
            self._bitrate.blockSignals(True)
            self._bitrate.setValue(preset.kbps)
            self._bitrate.blockSignals(False)
        self._actualizar_pista_caudal()
        self._refrescar_grafo()

    def _al_cambiar_bitrate(self) -> None:
        self._sincronizar_combo_caudal()
        self._actualizar_pista_caudal()
        self._refrescar_grafo()

    def _sincronizar_combo_caudal(self) -> None:
        preset = caudal_por_kbps(int(self._bitrate.value()))
        ident = preset.id if preset is not None else CAUDAL_PERSONALIZADO
        self._caudal.blockSignals(True)
        self._poner_combo(self._caudal, ident)
        self._caudal.blockSignals(False)

    def _actualizar_pista_caudal(self) -> None:
        modo = modo_por_id(self._modo.currentData() or MODO_POR_DEFECTO)
        self._lbl_caudal.setText(pista_caudal(int(self._bitrate.value()), modo.fps))

    def _actualizar_pistas(self) -> None:
        modo = modo_por_id(self._modo.currentData() or MODO_POR_DEFECTO)
        self._lbl_modo.setText(modo.explicacion)
        self._actualizar_pista_caudal()
        self._al_cambiar_captura()
        self._al_cambiar_destino_audio()

    def _al_cambiar_captura(self) -> None:
        ident = self._captura.currentData()
        for cid, _et, exp in _CAPTURAS:
            if cid == ident:
                self._lbl_captura.setText(exp)
                self._refrescar_grafo()
                return
        self._lbl_captura.clear()
        self._refrescar_grafo()

    def _al_cambiar_destino_audio(self) -> None:
        ident = self._destino_audio.currentData() or "both"
        for did, _et, exp in _DESTINOS_AUDIO:
            if did == ident:
                self._lbl_destino.setText(exp)
                break
        self._fuente.setEnabled(ident != "pc")
        self.silencio_local_cambiado.emit()
        self._refrescar_grafo()

    def _al_cambiar_p2p(self) -> None:
        # Channel is always choosable; when forcing, the adapter switches to wpas + GO 15.
        self._canal.setEnabled(True)

    def _refrescar_grafo(self) -> None:
        if not hasattr(self, "_grafo"):
            return
        modo = modo_por_id(self._modo.currentData() or MODO_POR_DEFECTO)
        mon = self._monitor.currentData() or self._monitor.currentText() or "auto"
        ruta = self._destino_audio.currentData() or "tv"
        error = self._estado is ConnectionState.ERROR
        tele = ""
        if hasattr(self, "_lbl_dest_vivo"):
            tele = self._lbl_dest_vivo.text()
        self._grafo.actualizar_estados(
            proyectando=self._proyectando
            or self._estado
            in (
                ConnectionState.STREAMING,
                ConnectionState.CONNECTED,
                ConnectionState.PAIRING,
            ),
            error=error,
            p2p=self._proyectando or self._estado is ConnectionState.STREAMING,
            audio_ruta=str(ruta),
            bus_activo=self._proyectando and str(ruta) != "pc",
            monitor=str(mon),
            modo=modo.etiqueta,
            bitrate_kbps=int(self._bitrate.value()),
            tele=tele,
        )

    def _refrescar_firewall(self) -> None:
        puerto = int(self._rtsp.value()) if hasattr(self, "_rtsp") else 7236
        abierto = puerto_abierto(puerto)
        self._lbl_firewall.setText(
            f"Port {puerto}/tcp: <b>open</b>."
            if abierto
            else f"Port {puerto}/tcp: <b>closed</b> right now."
        )
        self._lbl_firewall.setTextFormat(Qt.TextFormat.RichText)

    def config_actual(self) -> StreamConfig:
        modo = modo_por_id(self._modo.currentData() or MODO_POR_DEFECTO)
        audio_dev = self._fuente.currentData() or None
        monitor = self._monitor.currentData() or None
        go = self._go.currentData()
        canal_dato = self._canal.currentData()
        canal = int(canal_dato) if canal_dato not in (None, "") else None
        audio, mute_local = audio_y_silencio(self._destino_audio.currentData() or "both")
        cfg = StreamConfig(
            ancho=modo.ancho,
            alto=modo.alto,
            fps=modo.fps,
            bitrate_kbps=int(self._bitrate.value()),
            audio=audio,
            mute_local=mute_local,
            audio_device=audio_dev or None,
            monitor=monitor or None,
            captura=self._captura.currentData() or "x11",
            gestionar_firewall=self._chk_firewall.isChecked(),
            entrada_remota=self._chk_uibc.isChecked(),
            go_intent=int(go) if go not in (None, "") else None,
            rtsp_port=int(self._rtsp.value()),
            rtp_source_port=int(self._rtp.value()),
            scan_timeout_s=int(self._timeout.value()),
            p2p_backend=self._p2p_backend.currentData() or "nm",
            p2p_channel=canal,
            media_pipeline=self._pipeline.currentData() or "auto",
            wifi_interface=self._iface.currentData() or None,
            test_pattern=self._chk_patron.isChecked(),
        )
        guardar_prefs(cfg)
        return cfg

    def _cargar_prefs(self) -> None:
        cfg = cargar_prefs()
        modo = modo_desde_tamano(cfg.ancho, cfg.alto, cfg.fps)
        if modo is not None:
            idx = self._modo.findData(modo.id)
            if idx >= 0:
                self._modo.blockSignals(True)
                self._modo.setCurrentIndex(idx)
                self._modo.blockSignals(False)
        self._bitrate.blockSignals(True)
        self._bitrate.setValue(cfg.bitrate_kbps)
        self._bitrate.blockSignals(False)
        self._modo_id_prev = modo.id if modo is not None else None
        self._sincronizar_combo_caudal()
        self._actualizar_pista_caudal()
        self._destino_audio.blockSignals(True)
        self._poner_combo(
            self._destino_audio,
            destino_desde_config(audio=cfg.audio, mute_local=cfg.mute_local),
        )
        self._destino_audio.blockSignals(False)
        if cfg.audio_device:
            idx = self._fuente.findData(cfg.audio_device)
            if idx >= 0:
                self._fuente.setCurrentIndex(idx)
        if cfg.monitor:
            idx = self._monitor.findData(cfg.monitor)
            if idx >= 0:
                self._monitor.setCurrentIndex(idx)
        idx = self._captura.findData(cfg.captura)
        if idx >= 0:
            self._captura.setCurrentIndex(idx)
        self._chk_firewall.setChecked(cfg.gestionar_firewall)
        self._chk_uibc.setChecked(cfg.entrada_remota)
        self._poner_combo(self._go, "" if cfg.go_intent is None else str(cfg.go_intent))
        self._rtsp.setValue(int(cfg.rtsp_port))
        self._rtp.setValue(int(cfg.rtp_source_port))
        self._timeout.setValue(int(cfg.scan_timeout_s))
        self._poner_combo(self._p2p_backend, cfg.p2p_backend or "nm")
        self._poner_combo(
            self._canal,
            "" if cfg.p2p_channel is None else str(int(cfg.p2p_channel)),
        )
        self._poner_combo(self._pipeline, cfg.media_pipeline or "auto")
        if cfg.wifi_interface:
            self._poner_combo(self._iface, cfg.wifi_interface)
        self._chk_patron.setChecked(cfg.test_pattern)
        self._al_cambiar_p2p()

    def _poner_combo(self, combo: QComboBox, valor: object) -> None:
        idx = combo.findData(valor)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def marcar_progreso(self, hay_dispositivo: bool, proyectando: bool) -> None:
        self._proyectando = proyectando
        self.btn_compartir.setEnabled(hay_dispositivo and not proyectando)
        self.btn_aplicar.setEnabled(proyectando)
        self.btn_detener.setEnabled(proyectando)
        self.btn_limpiar.setEnabled(not proyectando)
        self._pintar_estado()

    def aplicar_evento(self, evento: object) -> None:
        if isinstance(evento, StateChanged):
            self._estado = evento.estado
            if evento.detalle and evento.estado is ConnectionState.STREAMING:
                pass
            self._pintar_estado()
        elif isinstance(evento, UserMessage):
            self._lbl_mensaje.setText(evento.texto)
            self._pintar_estado()

    def set_detalle_backend(self, texto: str) -> None:
        self._detalle_backend = texto
        if texto:
            self._registro.setPlainText(texto)

    def aplicar_enlace(self, hechos: LinkFacts) -> None:
        if hechos.interface or hechos.tv_ip:
            pc = hechos.local_ip or "…"
            tv = hechos.tv_ip or "no client"
            iface = hechos.interface or "no interface"
            self._lbl_enlace.setText(
                f"Direct link: <b>{iface}</b> · PC {pc} · TV {tv}"
            )
            if hasattr(self, "_lbl_dest_vivo"):
                self._lbl_dest_vivo.setText(
                    f"TV: {tv} · link {iface} · PC {pc}"
                )
        else:
            self._lbl_enlace.setText("Direct link: no group yet.")
            if hasattr(self, "_lbl_dest_vivo") and not self._proyectando:
                self._lbl_dest_vivo.setText("TV: no session")
        self._lbl_enlace.setTextFormat(Qt.TextFormat.RichText)
        partes = []
        if hechos.mode:
            partes.append(f"mode <b>{hechos.mode}</b>")
        if hechos.rtp:
            partes.append(f"RTP {hechos.rtp}")
        if hechos.session_id:
            partes.append(f"session {hechos.session_id}")
        self._lbl_negociado.setText(
            "Negotiation: " + (" · ".join(partes) if partes else "waiting for M1–PLAY.")
        )
        self._lbl_negociado.setTextFormat(Qt.TextFormat.RichText)
        if hechos.advertised_video or hechos.advertised_audio:
            self._lbl_m3.setText(
                "TV advertised in M3: video "
                f"{hechos.advertised_video or '—'}; audio "
                f"{hechos.advertised_audio or '—'}; "
                f"HDCP {hechos.hdcp or '—'}. In M4 we send the Picture mode and "
                "bitrate, AAC, and HDCP none."
            )
        self._refrescar_grafo()

    def _pintar_estado(self) -> None:
        self._lbl_estado.setText(
            f"<b>{_ESTADO.get(self._estado, self._estado)}</b>"
        )
        self._lbl_estado.setTextFormat(Qt.TextFormat.RichText)
        self._refrescar_grafo()
