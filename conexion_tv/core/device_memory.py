"""Persistent device memory and what works with each one.

Records observed facts, not tips: tips live in `protocols`.

Design hinges on two rules:

- **Memory does not degrade on its own.** A service stopping its announcement
  does not mean it is gone; many TVs only advertise certain services in certain
  modes. Downgrading state when unseen would erase memory whenever the set is
  idle.
- **Attempts are never blocked.** A protocol in `FAILING` is still offered,
  because the cause is usually configuration and transient. The only exception
  is `UNSUPPORTED`, reserved for confirmed hardware absences.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .protocols import CATALOGO, Protocol, ProtocolInfo, Purpose

SCHEMA_VERSION = 1


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Legacy Spanish values written by older builds; still accepted on load.
_PROTOCOL_STATE_LEGACY = {
    "desconocido": "unknown",
    "anunciado": "announced",
    "funciona": "working",
    "falla": "failing",
    "no_soportado": "unsupported",
}


class ProtocolState(str, Enum):
    """What we know about a protocol on a specific device."""

    UNKNOWN = "unknown"
    ANNOUNCED = "announced"
    WORKING = "working"
    FAILING = "failing"
    UNSUPPORTED = "unsupported"

    @property
    def se_puede_ofrecer(self) -> bool:
        """Whether the UI should offer the protocol as an activatable option.

        Everything except confirmed hardware absences.
        """
        return self is not ProtocolState.UNSUPPORTED

    @property
    def es_fiable(self) -> bool:
        """Whether we have seen it work on this device."""
        return self is ProtocolState.WORKING


@dataclass
class ProtocolMemory:
    """Lo aprendido sobre un protocolo en un dispositivo.

    `evidencia` no es decorativa: es la salvaguarda contra marcar algo como
    funcional porque "parecía ir". Si no se puede escribir qué se observó, el
    estado no debería ser WORKING.
    """

    estado: ProtocolState = ProtocolState.UNKNOWN
    comprobado_el: str | None = None
    evidencia: str | None = None
    intentos: int = 0
    exitos: int = 0
    ultimo_error: str | None = None
    limitaciones: list[str] = field(default_factory=list)
    datos: dict = field(default_factory=dict)

    @property
    def fiabilidad(self) -> float | None:
        """Proporción de intentos con éxito, o None si nunca se intentó.

        Permite distinguir lo que funciona siempre de lo que funciona a veces,
        que el estado por sí solo no captura.
        """
        if self.intentos == 0:
            return None
        return self.exitos / self.intentos

    def a_dict(self) -> dict:
        return {
            "estado": self.estado.value,
            "comprobado_el": self.comprobado_el,
            "evidencia": self.evidencia,
            "intentos": self.intentos,
            "exitos": self.exitos,
            "ultimo_error": self.ultimo_error,
            "limitaciones": list(self.limitaciones),
            "datos": dict(self.datos),
        }

    @classmethod
    def de_dict(cls, d: dict) -> ProtocolMemory:
        raw = d.get("estado", "unknown")
        if isinstance(raw, str):
            raw = _PROTOCOL_STATE_LEGACY.get(raw, raw)
        try:
            estado = ProtocolState(raw)
        except ValueError:
            estado = ProtocolState.UNKNOWN
        return cls(
            estado=estado,
            comprobado_el=d.get("comprobado_el"),
            evidencia=d.get("evidencia"),
            intentos=int(d.get("intentos", 0)),
            exitos=int(d.get("exitos", 0)),
            ultimo_error=d.get("ultimo_error"),
            limitaciones=list(d.get("limitaciones", [])),
            datos=dict(d.get("datos", {})),
        )


@dataclass
class DeviceRecord:
    """Un dispositivo recordado.

    `clave` es una identidad estable: nunca la IP, que cambia con DHCP. Se
    prefiere el UDN que anuncia por UPnP y, si no lo tiene, su MAC. Todos los
    demás identificadores conocidos quedan en `alias` para poder reconocer el
    aparato por cualquiera de ellos.
    """

    clave: str
    nombre: str = ""
    fabricante: str = ""
    modelo: str = ""
    modelo_interno: str = ""
    plataforma: str = ""
    anio: int | None = None
    alias: list[str] = field(default_factory=list)
    ultima_ip: str | None = None
    visto_primera_vez: str = field(default_factory=_ahora)
    visto_ultima_vez: str = field(default_factory=_ahora)
    protocolos: dict[Protocol, ProtocolMemory] = field(default_factory=dict)

    def memoria(self, protocolo: Protocol) -> ProtocolMemory:
        """Memoria de un protocolo, creándola vacía si no existía."""
        return self.protocolos.setdefault(protocolo, ProtocolMemory())

    def estado(self, protocolo: Protocol) -> ProtocolState:
        mem = self.protocolos.get(protocolo)
        return mem.estado if mem else ProtocolState.UNKNOWN

    # -- Registro de observaciones -------------------------------------------

    def anotar_anuncio(self, protocolo: Protocol, datos: dict | None = None) -> None:
        """El dispositivo anuncia el protocolo (SSDP, REST, descriptor UPnP).

        Solo promociona desde UNKNOWN. Un anuncio es más débil que una prueba
        real, así que no debe sobrescribir un WORKING ni un FAILING, y tampoco
        resucita un NO_SOPORTADO: ese se decide explícitamente.
        """
        mem = self.memoria(protocolo)
        if datos:
            mem.datos.update(datos)
        if mem.estado is ProtocolState.UNKNOWN:
            mem.estado = ProtocolState.ANNOUNCED
            mem.comprobado_el = _ahora()

    def anotar_exito(
        self,
        protocolo: Protocol,
        evidencia: str,
        datos: dict | None = None,
        limitaciones: list[str] | None = None,
    ) -> None:
        """El protocolo se probó y funcionó.

        `evidencia` es obligatoria a propósito: describe qué se observó.
        """
        if not evidencia.strip():
            raise ValueError(
                "anotar_exito requires evidence: without knowing what was "
                "observed, the state cannot be 'working'"
            )
        mem = self.memoria(protocolo)
        mem.estado = ProtocolState.WORKING
        mem.comprobado_el = _ahora()
        mem.evidencia = evidencia
        mem.intentos += 1
        mem.exitos += 1
        mem.ultimo_error = None
        if datos:
            mem.datos.update(datos)
        for lim in limitaciones or []:
            if lim not in mem.limitaciones:
                mem.limitaciones.append(lim)

    def anotar_fallo(self, protocolo: Protocol, error: str) -> None:
        """El protocolo se probó y falló.

        El estado refleja el último intento, pero `exitos` se conserva para que
        la interfaz pueda decir "funcionó 4 de 5 veces" en lugar de dar por
        perdido algo que falla de forma intermitente.
        """
        mem = self.memoria(protocolo)
        mem.estado = ProtocolState.FAILING
        mem.comprobado_el = _ahora()
        mem.intentos += 1
        mem.ultimo_error = error

    def marcar_no_soportado(self, protocolo: Protocol, motivo: str) -> None:
        """Ausencia comprobada en el aparato, no un fallo de configuración.

        Es el único estado que impide ofrecer el protocolo, así que se reserva a
        cases such as "this TV has no Chromecast".
        """
        mem = self.memoria(protocolo)
        mem.estado = ProtocolState.UNSUPPORTED
        mem.comprobado_el = _ahora()
        mem.evidencia = motivo

    # -- Consulta para la interfaz -------------------------------------------

    def opciones(self, proposito: Purpose | None = None) -> list[DeviceOption]:
        """Opciones de conexión del dispositivo, con su estado y sus consejos.

        Las ordena de forma útil para la interfaz: primero lo que se ha visto
        funcionar, luego lo anunciado, y al final lo no soportado.
        """
        orden = {
            ProtocolState.WORKING: 0,
            ProtocolState.ANNOUNCED: 1,
            ProtocolState.FAILING: 2,
            ProtocolState.UNKNOWN: 3,
            ProtocolState.UNSUPPORTED: 4,
        }
        fichas = [
            f
            for f in CATALOGO.values()
            if proposito is None or f.proposito is proposito
        ]
        opciones = [
            DeviceOption(
                info=f,
                memoria=self.protocolos.get(f.id, ProtocolMemory()),
            )
            for f in fichas
        ]
        opciones.sort(key=lambda o: (orden[o.memoria.estado], o.info.nombre))
        return opciones

    def coincide(self, identificador: str) -> bool:
        """Si un identificador (clave, alias, MAC o UUID) apunta a este aparato."""
        ident = _normalizar_id(identificador)
        return ident == self.clave or ident in self.alias

    # -- Serialización -------------------------------------------------------

    def a_dict(self) -> dict:
        return {
            "clave": self.clave,
            "nombre": self.nombre,
            "fabricante": self.fabricante,
            "modelo": self.modelo,
            "modelo_interno": self.modelo_interno,
            "plataforma": self.plataforma,
            "anio": self.anio,
            "alias": list(self.alias),
            "ultima_ip": self.ultima_ip,
            "visto_primera_vez": self.visto_primera_vez,
            "visto_ultima_vez": self.visto_ultima_vez,
            "protocolos": {p.value: m.a_dict() for p, m in self.protocolos.items()},
        }

    @classmethod
    def de_dict(cls, d: dict) -> DeviceRecord:
        protocolos: dict[Protocol, ProtocolMemory] = {}
        for clave, valor in (d.get("protocolos") or {}).items():
            try:
                protocolos[Protocol(clave)] = ProtocolMemory.de_dict(valor)
            except ValueError:
                # Protocolo de una versión futura o renombrado: se ignora en
                # lugar de romper la carga de toda la memoria.
                continue
        return cls(
            clave=d["clave"],
            nombre=d.get("nombre", ""),
            fabricante=d.get("fabricante", ""),
            modelo=d.get("modelo", ""),
            modelo_interno=d.get("modelo_interno", ""),
            plataforma=d.get("plataforma", ""),
            anio=d.get("anio"),
            alias=list(d.get("alias", [])),
            ultima_ip=d.get("ultima_ip"),
            visto_primera_vez=d.get("visto_primera_vez", _ahora()),
            visto_ultima_vez=d.get("visto_ultima_vez", _ahora()),
            protocolos=protocolos,
        )


@dataclass(frozen=True)
class DeviceOption:
    """Una opción de conexión tal como se le presenta al usuario."""

    info: ProtocolInfo
    memoria: ProtocolMemory

    @property
    def estado(self) -> ProtocolState:
        return self.memoria.estado

    @property
    def se_puede_intentar(self) -> bool:
        """Si tiene sentido ofrecer el botón de conectar.

        Dos razones distintas lo impiden: que el aparato no lo tenga, o que no
        haya forma de hablarlo desde Linux. Ambas se explican al usuario, pero
        ninguna de las dos se arregla reintentando.
        """
        return self.estado.se_puede_ofrecer and self.info.disponible_en_linux

    @property
    def motivo_no_disponible(self) -> str | None:
        """Por qué no se puede intentar, para poder explicarlo en la interfaz."""
        if not self.info.disponible_en_linux:
            return "There is no way to use this protocol from Linux."
        if self.estado is ProtocolState.UNSUPPORTED:
            return self.memoria.evidencia or "The device does not support it."
        return None

    @property
    def consejos(self) -> tuple[str, ...]:
        """Qué mostrarle al usuario.

        Con el protocolo ya funcionando no hace falta instruir a nadie; solo se
        avisa de las limitaciones conocidas. En cualquier otro caso se dan los
        requisitos y, si hubo un fallo, también los consejos de diagnóstico.
        """
        if self.estado is ProtocolState.WORKING:
            return tuple(self.memoria.limitaciones)
        consejos = list(self.info.requisitos_dispositivo)
        consejos += list(self.info.requisitos_equipo)
        if (
            self.estado in (ProtocolState.FAILING, ProtocolState.UNSUPPORTED)
            or not self.info.disponible_en_linux
        ):
            consejos += list(self.info.consejos_si_falla)
        return tuple(consejos)


def _normalizar_id(identificador: str) -> str:
    """Normaliza un identificador a la forma `tipo:valor`.

    Acepta una MAC o un UUID sueltos y les pone el prefijo que les corresponde,
    para que quien llama no tenga que saber el formato interno.
    """
    ident = identificador.strip().lower()
    if ident.startswith(("mac:", "udn:", "ip:")):
        tipo, _, valor = ident.partition(":")
        if tipo == "udn":
            valor = valor.removeprefix("uuid:")
        return f"{tipo}:{valor}"
    if ident.startswith("uuid:"):
        return f"udn:{ident.removeprefix('uuid:')}"
    sin_separadores = ident.replace(":", "").replace("-", "")
    if len(sin_separadores) == 12 and all(c in "0123456789abcdef" for c in sin_separadores):
        pares = [sin_separadores[i : i + 2] for i in range(0, 12, 2)]
        return "mac:" + ":".join(pares)
    return f"udn:{ident}"


class DeviceMemory:
    """Catálogo persistente de dispositivos.

    Se guarda con escritura atómica para que un corte a media escritura no deje
    el fichero corrupto y con él toda la memoria acumulada.
    """

    def __init__(self, ruta: Path | None = None) -> None:
        self.ruta = ruta or ruta_por_defecto()
        self._dispositivos: dict[str, DeviceRecord] = {}
        self.cargar()

    # -- Persistencia --------------------------------------------------------

    def cargar(self) -> None:
        self._dispositivos = {}
        if not self.ruta.exists():
            return
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Memoria ilegible: se empieza de cero en lugar de impedir que la
            # aplicación arranque. Es un caché, no datos irremplazables.
            return
        for clave, valor in (datos.get("dispositivos") or {}).items():
            try:
                self._dispositivos[clave] = DeviceRecord.de_dict(valor)
            except (KeyError, TypeError):
                continue

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "actualizado": _ahora(),
            "dispositivos": {k: v.a_dict() for k, v in self._dispositivos.items()},
        }
        texto = json.dumps(payload, indent=2, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(dir=str(self.ruta.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(texto)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.ruta)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    # -- Consulta y alta -----------------------------------------------------

    def todos(self) -> list[DeviceRecord]:
        """Dispositivos recordados, los vistos más recientemente primero."""
        return sorted(
            self._dispositivos.values(),
            key=lambda d: d.visto_ultima_vez,
            reverse=True,
        )

    def buscar(self, identificador: str) -> DeviceRecord | None:
        """Busca por clave, alias, MAC o UUID, en cualquier formato."""
        ident = _normalizar_id(identificador)
        directo = self._dispositivos.get(ident)
        if directo is not None:
            return directo
        for registro in self._dispositivos.values():
            if registro.coincide(ident):
                return registro
        return None

    def registrar(
        self,
        identificadores: list[str],
        *,
        nombre: str = "",
        fabricante: str = "",
        modelo: str = "",
        modelo_interno: str = "",
        plataforma: str = "",
        anio: int | None = None,
        ip: str | None = None,
    ) -> DeviceRecord:
        """Da de alta o actualiza un dispositivo encontrado en un escaneo.

        `identificadores` va en orden de preferencia: el primero que sirva se usa
        como clave y el resto quedan como alias. Si el aparato ya se conocía por
        cualquiera de ellos, se actualiza la entrada existente y se le añaden los
        identificadores nuevos, en lugar de crear un duplicado.
        """
        if not identificadores:
            raise ValueError("at least one identifier is required")
        normalizados = [_normalizar_id(i) for i in identificadores]

        registro = next(
            (r for i in normalizados if (r := self.buscar(i)) is not None), None
        )
        if registro is None:
            registro = DeviceRecord(clave=normalizados[0])
            self._dispositivos[registro.clave] = registro

        for ident in normalizados:
            if ident != registro.clave and ident not in registro.alias:
                registro.alias.append(ident)

        # Los campos vacíos no borran lo que ya se sabía: un escaneo rápido
        # devuelve menos información que un sondeo completo.
        registro.nombre = nombre or registro.nombre
        registro.fabricante = fabricante or registro.fabricante
        registro.modelo = modelo or registro.modelo
        registro.modelo_interno = modelo_interno or registro.modelo_interno
        registro.plataforma = plataforma or registro.plataforma
        registro.anio = anio if anio is not None else registro.anio
        registro.ultima_ip = ip or registro.ultima_ip
        registro.visto_ultima_vez = _ahora()
        return registro

    def olvidar(self, identificador: str) -> bool:
        registro = self.buscar(identificador)
        if registro is None:
            return False
        del self._dispositivos[registro.clave]
        return True


def ruta_por_defecto() -> Path:
    """Ubicación de la memoria, respetando XDG_DATA_HOME."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "conexion_tv" / "devices.json"
