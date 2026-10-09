"""Main window: devices, remote, and diagnostics."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from conexion_tv.control.keys import TECLAS
from conexion_tv.control.tizen import TizenWebSocketController
from conexion_tv.core.device_memory import DeviceMemory, DeviceRecord, ProtocolState
from conexion_tv.core.events import ConnectionState, StateChanged
from conexion_tv.core.seed import sembrar
from conexion_tv.diagnostics import comprobar_sistema
from conexion_tv.discovery import escanear
from conexion_tv.mirror.backends.fluxcast import FluxCastBackend

from .panel_pantalla import PanelPantalla
from .workers import FuncionEnHilo, PuenteEventos

_ESTADO = {
    ProtocolState.WORKING: "Works",
    ProtocolState.ANNOUNCED: "Advertised",
    ProtocolState.FAILING: "Failed before",
    ProtocolState.UNKNOWN: "Untested",
    ProtocolState.UNSUPPORTED: "Unsupported",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Linux ↔ Samsung TV connection")
        self.resize(1040, 780)

        self.memoria = DeviceMemory()
        sembrar(self.memoria)
        self._registro: DeviceRecord | None = None
        self._mando: TizenWebSocketController | None = None
        self._proyeccion = FluxCastBackend()
        self._proyectando = False
        self._trabajo: FuncionEnHilo | None = None

        self._puente = PuenteEventos(self)
        self._puente.recibido.connect(self._al_evento_proyeccion)
        self._proyeccion.set_event_handler(self._puente.recibido.emit)

        self._lista = QListWidget()
        self._detalle = QTextEdit()
        self._detalle.setReadOnly(True)
        self._diagnostico = QTextEdit()
        self._diagnostico.setReadOnly(True)
        self._panel_pantalla = PanelPantalla()

        self._btn_escanear = QPushButton("Scan network")
        self._btn_conectar = QPushButton("Connect remote")
        self._btn_encender = QPushButton("Power on (WoL)")
        self._btn_conectar.setEnabled(False)
        self._btn_encender.setEnabled(False)

        self._estado = QLabel("No device selected")
        self._estado.setWordWrap(True)

        pestanas = QTabWidget()
        pestanas.addTab(self._panel_dispositivos(), "Devices")
        pestanas.addTab(self._panel_pantalla, "Screen")
        pestanas.addTab(self._panel_mando(), "Remote")
        pestanas.addTab(self._panel_diagnostico(), "Diagnostics")
        self.setCentralWidget(pestanas)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        self._btn_escanear.clicked.connect(self._escanear)
        self._btn_conectar.clicked.connect(self._conectar_mando)
        self._btn_encender.clicked.connect(self._encender)
        self._lista.currentItemChanged.connect(self._al_cambiar_dispositivo)
        self._panel_pantalla.compartir.connect(self._compartir)
        self._panel_pantalla.detener.connect(self._detener)
        self._panel_pantalla.aplicar.connect(self._aplicar_espejo)
        self._panel_pantalla.limpiar_enlace.connect(self._limpiar_enlace)
        self._panel_pantalla.silencio_local_cambiado.connect(self._aplicar_silencio_local)

        self._reloj = QTimer(self)
        self._reloj.setInterval(900)
        self._reloj.timeout.connect(self._vigilar_proyeccion)
        self._reloj.start()

        self._poblar_lista()
        self._refrescar_diagnostico()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._mando is not None:
            self._mando.disconnect()
        if self._proyectando:
            try:
                self._proyeccion.disconnect()
            except Exception:
                pass
        super().closeEvent(event)

    def _panel_dispositivos(self) -> QWidget:
        panel = QWidget()
        raiz = QVBoxLayout(panel)
        barra = QHBoxLayout()
        barra.addWidget(self._btn_escanear)
        barra.addStretch()
        raiz.addLayout(barra)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._lista)
        split.addWidget(self._detalle)
        split.setStretchFactor(1, 2)
        raiz.addWidget(split)
        return panel

    def _panel_mando(self) -> QWidget:
        panel = QWidget()
        raiz = QVBoxLayout(panel)
        raiz.addWidget(self._estado)

        acciones = QHBoxLayout()
        acciones.addWidget(self._btn_conectar)
        acciones.addWidget(self._btn_encender)
        acciones.addStretch()
        raiz.addLayout(acciones)

        grupos: dict[str, QGroupBox] = {}
        rejillas: dict[str, QGridLayout] = {}
        titulos = {
            "alimentacion": "Power",
            "volumen": "Volume",
            "direccion": "Direction",
            "navegacion": "Navigation",
            "entrada": "Input",
            "canal": "Channel",
            "reproduccion": "Playback",
        }
        for tecla in TECLAS:
            if tecla.grupo not in grupos:
                caja = QGroupBox(titulos.get(tecla.grupo, tecla.grupo))
                rejilla = QGridLayout(caja)
                grupos[tecla.grupo] = caja
                rejillas[tecla.grupo] = rejilla
                raiz.addWidget(caja)
            boton = QPushButton(tecla.etiqueta)
            boton.clicked.connect(lambda _=False, codigo=tecla.codigo: self._enviar_tecla(codigo))
            fila = rejillas[tecla.grupo].rowCount()
            if tecla.grupo == "direccion":
                posiciones = {
                    "KEY_UP": (0, 1),
                    "KEY_LEFT": (1, 0),
                    "KEY_ENTER": (1, 1),
                    "KEY_RIGHT": (1, 2),
                    "KEY_DOWN": (2, 1),
                }
                r, c = posiciones.get(tecla.codigo, (fila, 0))
                rejillas[tecla.grupo].addWidget(boton, r, c)
            else:
                rejillas[tecla.grupo].addWidget(boton, 0, rejillas[tecla.grupo].columnCount())
        raiz.addStretch()
        return panel

    def _panel_diagnostico(self) -> QWidget:
        panel = QWidget()
        raiz = QVBoxLayout(panel)
        recargar = QPushButton("Check again")
        recargar.clicked.connect(self._refrescar_diagnostico)
        raiz.addWidget(recargar, alignment=Qt.AlignmentFlag.AlignLeft)
        raiz.addWidget(self._diagnostico)
        return panel

    def _poblar_lista(self) -> None:
        self._lista.clear()
        for registro in self.memoria.todos():
            texto = f"{registro.nombre or registro.modelo or 'TV'}"
            if registro.ultima_ip:
                texto += f"  ·  {registro.ultima_ip}"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, registro.clave)
            self._lista.addItem(item)
        if self._lista.count():
            self._lista.setCurrentRow(0)

    def _al_cambiar_dispositivo(self, actual: QListWidgetItem | None) -> None:
        if actual is None:
            self._registro = None
            self._detalle.clear()
            self._btn_conectar.setEnabled(False)
            self._btn_encender.setEnabled(False)
            self._panel_pantalla.marcar_progreso(False, self._proyectando)
            return
        clave = actual.data(Qt.ItemDataRole.UserRole)
        self._registro = self.memoria.buscar(clave)
        self._btn_conectar.setEnabled(self._registro is not None)
        self._btn_encender.setEnabled(self._registro is not None)
        self._panel_pantalla.marcar_progreso(self._registro is not None, self._proyectando)
        self._pintar_detalle()
        self._actualizar_estado_mando()

    def _pintar_detalle(self) -> None:
        registro = self._registro
        if registro is None:
            self._detalle.clear()
            return
        lineas = [
            f"{registro.nombre or 'TV'}",
            f"Model: {registro.modelo or '—'}",
            f"IP: {registro.ultima_ip or '—'}",
            "",
            "Connection options",
            "",
        ]
        for opcion in registro.opciones():
            activable = "can try" if opcion.se_puede_intentar else "not activatable"
            lineas.append(f"· {opcion.info.nombre}  [{_ESTADO[opcion.estado]} · {activable}]")
            if opcion.motivo_no_disponible:
                lineas.append(f"    {opcion.motivo_no_disponible}")
            for consejo in opcion.consejos[:3]:
                lineas.append(f"    → {consejo}")
            lineas.append("")
        self._detalle.setPlainText("\n".join(lineas))

    def _ocupado(self) -> bool:
        return self._trabajo is not None and self._trabajo.isRunning()

    def _lanzar(self, funcion, al_listo, mensaje: str) -> None:
        if self._ocupado():
            self.statusBar().showMessage("Wait for the current operation to finish")
            return
        self.statusBar().showMessage(mensaje)
        trabajo = FuncionEnHilo(funcion, self)
        trabajo.listo.connect(al_listo)
        trabajo.fallo.connect(self._mostrar_error)
        self._trabajo = trabajo
        trabajo.start()

    def _escanear(self) -> None:
        self._btn_escanear.setEnabled(False)

        def trabajo():
            return escanear(self.memoria)

        def listo(_registros):
            self._btn_escanear.setEnabled(True)
            self._poblar_lista()
            n = self._lista.count()
            self.statusBar().showMessage(
                f"{n} device(s) on the network" if n else "No TV found"
            )

        self._lanzar(trabajo, listo, "Scanning the network…")

    def _conectar_mando(self) -> None:
        registro = self._registro
        if registro is None:
            return

        def trabajo():
            mando = TizenWebSocketController(registro)
            mando.connect()
            return mando

        def listo(mando):
            if self._mando is not None:
                self._mando.disconnect()
            self._mando = mando
            self.memoria.guardar()
            self._pintar_detalle()
            self._actualizar_estado_mando()
            self.statusBar().showMessage("Remote connected. If the TV asks for permission, accept it.")

        self._lanzar(trabajo, listo, "Connecting the remote… watch the TV screen")

    def _encender(self) -> None:
        registro = self._registro
        if registro is None:
            return

        def trabajo():
            TizenWebSocketController(registro).power_on()
            return True

        def listo(_):
            self.statusBar().showMessage("Wake packet sent. Wait a few seconds.")

        self._lanzar(trabajo, listo, "Sending Wake-on-LAN…")

    def _compartir(self) -> None:
        registro = self._registro
        if registro is None:
            return
        disponible, motivo = self._proyeccion.is_available(registro)
        if not disponible:
            QMessageBox.warning(self, "Cannot share", motivo)
            return
        config = self._panel_pantalla.config_actual()

        def trabajo():
            self._proyeccion.connect(registro, config)
            self._proyeccion.start_stream(config)
            return True

        def listo(_):
            self._proyectando = True
            self.memoria.guardar()
            self._panel_pantalla.marcar_progreso(True, True)
            self.statusBar().showMessage("Sharing screen")

        self._lanzar(trabajo, listo, "Looking for the TV over Miracast…")

    def _aplicar_espejo(self) -> None:
        registro = self._registro
        if registro is None or not self._proyectando:
            return
        config = self._panel_pantalla.config_actual()

        def trabajo():
            self._proyeccion.disconnect()
            self._proyeccion.connect(registro, config)
            self._proyeccion.start_stream(config)
            return True

        def listo(_):
            self._proyectando = True
            self._panel_pantalla.marcar_progreso(True, True)
            self.statusBar().showMessage("Mirror restarted with the new settings")

        self._lanzar(trabajo, listo, "Restarting the mirror with the new settings…")

    def _aplicar_silencio_local(self) -> None:
        """tv↔both: loopback only. Enabling/disabling Miracast audio: restart."""
        if not self._proyectando:
            return
        cfg = self._panel_pantalla.config_actual()
        if cfg.audio:
            self._proyeccion.aplicar_ruta_audio(cfg)
            return
        self._aplicar_espejo()

    def _detener(self) -> None:
        def trabajo():
            self._proyeccion.disconnect()
            return True

        def listo(_):
            self._proyectando = False
            hay = self._registro is not None
            self._panel_pantalla.marcar_progreso(hay, False)
            self.statusBar().showMessage("Screen sharing stopped")

        self._lanzar(trabajo, listo, "Stopping projection…")

    def _limpiar_enlace(self) -> None:
        if self._proyectando:
            QMessageBox.information(
                self,
                "Mirror running",
                "Press «Stop sharing» first. Clearing the Direct link "
                "while the session is live cuts it badly.",
            )
            return

        def trabajo():
            from conexion_tv.mirror.backends.fluxcast.adapter import _cerrar_huerfanos_wfd
            from conexion_tv.mirror.backends.fluxcast.cli import cerrar_enlace_p2p

            _cerrar_huerfanos_wfd()
            cerrar_enlace_p2p()
            return True

        def listo(_):
            self.statusBar().showMessage("Wi-Fi Direct link cleared")

        self._lanzar(trabajo, listo, "Closing leftover Wi-Fi Direct…")

    def _vigilar_proyeccion(self) -> None:
        self._panel_pantalla.set_detalle_backend(self._proyeccion.detalle_sesion())
        self._panel_pantalla.aplicar_enlace(self._proyeccion.resumen_enlace())
        if self._proyectando and not self._ocupado() and not self._proyeccion.esta_activo():
            try:
                self._proyeccion.disconnect()
            except Exception:
                pass
            self._proyectando = False
            self._panel_pantalla.marcar_progreso(self._registro is not None, False)
            self._panel_pantalla.aplicar_evento(
                StateChanged(estado=ConnectionState.ERROR, detalle="sesion")
            )
            self.statusBar().showMessage("The mirror session dropped")

    def _al_evento_proyeccion(self, evento: object) -> None:
        self._panel_pantalla.aplicar_evento(evento)

    def _enviar_tecla(self, codigo: str) -> None:
        if self._mando is None:
            QMessageBox.information(
                self,
                "Remote not connected",
                "Press «Connect remote» first. The first time the TV asks for permission on screen.",
            )
            return

        def trabajo():
            self._mando.send_key(codigo)
            return codigo

        def listo(tecla):
            self.statusBar().showMessage(f"Sent {tecla}")

        self._lanzar(trabajo, listo, f"Sending {codigo}…")

    def _actualizar_estado_mando(self) -> None:
        if self._registro is None:
            self._estado.setText("No device selected")
            return
        nombre = self._registro.nombre or self._registro.modelo or "the TV"
        if self._mando is not None:
            self._estado.setText(f"Remote connected to {nombre} ({self._registro.ultima_ip})")
        else:
            self._estado.setText(
                f"Selected: {nombre}. Connect the remote to send keys. "
                "If it is the first time, accept the dialog on the TV."
            )

    def _refrescar_diagnostico(self) -> None:
        lineas = []
        for c in comprobar_sistema():
            marca = "OK" if c.ok else "FAIL"
            lineas.append(f"[{marca}] {c.titulo}")
            lineas.append(f"    {c.detalle}")
            if c.arreglo and not c.ok:
                lineas.append(f"    → {c.arreglo}")
            lineas.append("")
        lineas.append("To share the screen: Screen tab.")
        self._diagnostico.setPlainText("\n".join(lineas))

    def _mostrar_error(self, texto: str) -> None:
        self._btn_escanear.setEnabled(True)
        if not self._proyeccion.esta_activo():
            self._proyectando = False
        hay = self._registro is not None
        self._panel_pantalla.marcar_progreso(hay, self._proyectando)
        self._panel_pantalla.aplicar_evento(StateChanged(estado=ConnectionState.ERROR))
        self.statusBar().showMessage("Error")
        QMessageBox.warning(self, "Could not complete", texto)
