import json
from pathlib import Path

import pytest

from conexion_tv.core.device_memory import (
    DeviceMemory,
    ProtocolState,
    _normalizar_id,
)
from conexion_tv.core.protocols import Protocol, Purpose
from conexion_tv.core.seed import ruta_ficha_por_defecto, sembrar

# Identificadores inventados. Los de un aparato real no entran en el repositorio.
MAC_WIFI = "aa:bb:cc:dd:ee:01"
MAC_CABLE = "aa:bb:cc:dd:ee:02"
UDN = "uuid:00000000-0000-4000-8000-000000000001"

FICHA_EJEMPLO = Path(__file__).parent / "datos" / "tv_ejemplo.json"


@pytest.fixture
def memoria(tmp_path):
    return DeviceMemory(ruta=tmp_path / "devices.json")


def test_identificadores_equivalentes_apuntan_al_mismo_dispositivo():
    """Una MAC suelta, con guiones o con prefijo son el mismo aparato."""
    assert _normalizar_id("AA:BB:CC:DD:EE:01") == f"mac:{MAC_WIFI}"
    assert _normalizar_id("aa-bb-cc-dd-ee-01") == f"mac:{MAC_WIFI}"
    assert _normalizar_id("aabbccddee01") == f"mac:{MAC_WIFI}"
    assert _normalizar_id("uuid:abcd-1234") == "udn:abcd-1234"


def test_registrar_dos_veces_no_duplica_y_acumula_alias(memoria):
    """Reconocer el aparato por cualquier identificador evita duplicados."""
    primero = memoria.registrar([UDN, MAC_WIFI], nombre="[TV] Salon")
    segundo = memoria.registrar([MAC_CABLE, MAC_WIFI])

    assert primero is segundo
    assert len(memoria.todos()) == 1
    assert f"mac:{MAC_CABLE}" in segundo.alias
    # Un escaneo que no trae el nombre no debe borrar el que ya se conocía.
    assert segundo.nombre == "[TV] Salon"


def test_un_anuncio_no_sobrescribe_lo_ya_probado(memoria):
    """Un anuncio es evidencia más débil que una prueba real."""
    registro = memoria.registrar([MAC_WIFI])
    registro.anotar_exito(Protocol.TIZEN_WEBSOCKET, evidencia="KEY_VOLUP aceptada")
    registro.anotar_anuncio(Protocol.TIZEN_WEBSOCKET)

    assert registro.estado(Protocol.TIZEN_WEBSOCKET) is ProtocolState.WORKING


def test_un_anuncio_no_resucita_lo_marcado_como_ausente(memoria):
    registro = memoria.registrar([MAC_WIFI])
    registro.marcar_no_soportado(Protocol.GOOGLE_CAST, "sin anuncios de Cast")
    registro.anotar_anuncio(Protocol.GOOGLE_CAST)

    assert registro.estado(Protocol.GOOGLE_CAST) is ProtocolState.UNSUPPORTED


def test_el_exito_exige_evidencia(memoria):
    """Sin poder decir qué se observó, el estado no puede ser 'funciona'."""
    registro = memoria.registrar([MAC_WIFI])
    with pytest.raises(ValueError, match="evidence"):
        registro.anotar_exito(Protocol.MIRACAST_WFD, evidencia="   ")


def test_un_fallo_posterior_conserva_el_historial_de_exitos(memoria):
    """Lo intermitente debe distinguirse de lo que nunca funcionó."""
    registro = memoria.registrar([MAC_WIFI])
    for _ in range(3):
        registro.anotar_exito(Protocol.MIRACAST_WFD, evidencia="sesión establecida")
    registro.anotar_fallo(Protocol.MIRACAST_WFD, "la negociación RTSP expiró")

    mem = registro.memoria(Protocol.MIRACAST_WFD)
    assert mem.estado is ProtocolState.FAILING
    assert (mem.exitos, mem.intentos) == (3, 4)
    assert mem.fiabilidad == pytest.approx(0.75)
    assert mem.ultimo_error == "la negociación RTSP expiró"


def test_un_fallo_no_impide_volver_a_intentarlo(memoria):
    """La causa de un fallo suele ser de configuración y transitoria."""
    registro = memoria.registrar([MAC_WIFI])
    registro.anotar_fallo(Protocol.MIRACAST_WFD, "sin respuesta")

    opcion = next(
        o for o in registro.opciones() if o.info.id is Protocol.MIRACAST_WFD
    )
    assert opcion.se_puede_intentar
    # Tras un fallo se añaden los consejos de diagnóstico a los requisitos.
    assert any("Screen Sharing" in c for c in opcion.consejos)


def test_lo_ausente_en_el_dispositivo_no_es_activable(memoria):
    registro = memoria.registrar([MAC_WIFI])
    registro.marcar_no_soportado(Protocol.GOOGLE_CAST, "sin anuncios de Cast")

    opcion = next(
        o for o in registro.opciones() if o.info.id is Protocol.GOOGLE_CAST
    )
    assert not opcion.se_puede_intentar
    assert opcion.motivo_no_disponible == "sin anuncios de Cast"


def test_lo_inviable_desde_linux_no_es_activable_aunque_el_tv_lo_soporte(memoria):
    """AirPlay 2: el televisor lo soporta, pero no hay emisor en Linux."""
    registro = memoria.registrar([MAC_WIFI])
    registro.anotar_anuncio(Protocol.AIRPLAY2)

    opcion = next(o for o in registro.opciones() if o.info.id is Protocol.AIRPLAY2)
    assert opcion.estado is ProtocolState.ANNOUNCED
    assert not opcion.se_puede_intentar
    assert "from Linux" in opcion.motivo_no_disponible


def test_las_opciones_se_ordenan_poniendo_delante_lo_que_funciona(memoria):
    registro = memoria.registrar([MAC_WIFI])
    registro.anotar_exito(Protocol.MIRACAST_WFD, evidencia="sesión establecida")
    registro.anotar_anuncio(Protocol.DLNA_AVTRANSPORT)
    registro.marcar_no_soportado(Protocol.GOOGLE_CAST, "sin anuncios de Cast")

    estados = [o.estado for o in registro.opciones(Purpose.PROJECTION)]
    assert estados[0] is ProtocolState.WORKING
    assert estados[-1] is ProtocolState.UNSUPPORTED


def test_lo_que_funciona_solo_muestra_limitaciones_no_instrucciones(memoria):
    """Con el protocolo ya operativo no hay que instruir a nadie."""
    registro = memoria.registrar([MAC_WIFI])
    registro.anotar_exito(
        Protocol.TIZEN_WEBSOCKET,
        evidencia="token emitido",
        limitaciones=["app_list() no responde en este modelo"],
    )

    opcion = next(
        o for o in registro.opciones() if o.info.id is Protocol.TIZEN_WEBSOCKET
    )
    assert opcion.consejos == ("app_list() no responde en este modelo",)


def test_la_memoria_sobrevive_a_un_ciclo_de_guardado(tmp_path):
    ruta = tmp_path / "devices.json"
    memoria = DeviceMemory(ruta=ruta)
    registro = memoria.registrar([MAC_WIFI], modelo="UE55TU7190UXZG")
    registro.anotar_exito(
        Protocol.TIZEN_WEBSOCKET, evidencia="token emitido", datos={"puerto": 8002}
    )
    memoria.guardar()

    recargada = DeviceMemory(ruta=ruta)
    recuperado = recargada.buscar("AA-BB-CC-DD-EE-01")
    assert recuperado is not None
    assert recuperado.modelo == "UE55TU7190UXZG"
    assert recuperado.estado(Protocol.TIZEN_WEBSOCKET) is ProtocolState.WORKING
    assert recuperado.memoria(Protocol.TIZEN_WEBSOCKET).datos["puerto"] == 8002


def test_una_memoria_corrupta_no_impide_arrancar(tmp_path):
    """Es un caché, no datos irremplazables: mejor empezar de cero que fallar."""
    ruta = tmp_path / "devices.json"
    ruta.write_text("{esto no es json", encoding="utf-8")

    assert DeviceMemory(ruta=ruta).todos() == []


def test_un_protocolo_desconocido_en_disco_no_rompe_la_carga(tmp_path):
    """Compatibilidad con memorias escritas por versiones distintas."""
    ruta = tmp_path / "devices.json"
    ruta.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dispositivos": {
                    f"mac:{MAC_WIFI}": {
                        "clave": f"mac:{MAC_WIFI}",
                        "protocolos": {
                            "protocolo_del_futuro": {"estado": "funciona"},
                            "tizen_websocket": {"estado": "funciona"},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    registro = DeviceMemory(ruta=ruta).buscar(MAC_WIFI)
    assert registro is not None
    assert registro.estado(Protocol.TIZEN_WEBSOCKET) is ProtocolState.WORKING


def test_la_siembra_desde_la_ficha_refleja_lo_verificado(memoria):
    """La ficha debe traducirse a los estados que le corresponden."""
    registro = sembrar(memoria, FICHA_EJEMPLO)
    assert registro is not None
    assert registro.modelo == "UE55TU7190UXZG"
    # El UDN es más estable que una MAC: debe ganar como clave.
    assert registro.clave.startswith("udn:")

    # Comprobados contra el aparato.
    assert registro.estado(Protocol.TIZEN_WEBSOCKET) is ProtocolState.WORKING
    assert registro.estado(Protocol.DLNA_AVTRANSPORT) is ProtocolState.WORKING
    # Ausencia de hardware comprobada.
    assert registro.estado(Protocol.GOOGLE_CAST) is ProtocolState.UNSUPPORTED
    # Soportado por especificación pero aún sin probar.
    assert registro.estado(Protocol.MIRACAST_WFD) is ProtocolState.ANNOUNCED
    assert registro.estado(Protocol.WAKE_ON_LAN) is ProtocolState.ANNOUNCED


def test_la_siembra_arrastra_las_limitaciones_conocidas(memoria):
    registro = sembrar(memoria, FICHA_EJEMPLO)
    limitaciones = registro.memoria(Protocol.TIZEN_WEBSOCKET).limitaciones

    assert any("app_list" in lim for lim in limitaciones)


def test_sembrar_dos_veces_no_falsea_los_contadores(memoria):
    primero = sembrar(memoria, FICHA_EJEMPLO)
    intentos = primero.memoria(Protocol.TIZEN_WEBSOCKET).intentos
    segundo = sembrar(memoria, FICHA_EJEMPLO)

    assert len(memoria.todos()) == 1
    assert segundo.memoria(Protocol.TIZEN_WEBSOCKET).intentos == intentos


def test_sin_ficha_la_siembra_no_falla(memoria, tmp_path):
    """Una instalación nueva no tiene ficha, y eso no es un error."""
    assert sembrar(memoria, tmp_path / "no_existe.json") is None


def test_la_ficha_local_si_existe_tambien_se_siembra(memoria):
    """La ficha real vive fuera del repositorio; se comprueba solo si está."""
    ruta = ruta_ficha_por_defecto()
    if not ruta.exists():
        pytest.skip("no hay ficha local en INFO/")

    registro = sembrar(memoria, ruta)
    assert registro is not None
    assert registro.modelo
