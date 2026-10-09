import json
from ipaddress import IPv4Network
from pathlib import Path

from conexion_tv.core.device_memory import DeviceMemory, ProtocolState
from conexion_tv.core.protocols import Protocol
from conexion_tv.discovery.scan import _hit_desde_api, barrer_rest, escanear

FICHA = Path(__file__).parent / "datos" / "tv_ejemplo.json"
API = json.loads(FICHA.read_text(encoding="utf-8"))


def _payload_api() -> dict:
    return {
        "device": {
            "OS": "Tizen",
            "type": "Samsung SmartTV",
            "name": "[TV] Salon",
            "modelName": "UE55TU7190UXZG",
            "model": "20_KANTSU2_UHD_BASIC",
            "duid": "uuid:00000000-0000-4000-8000-000000000001",
            "wifiMac": "AA:BB:CC:DD:EE:01",
            "TokenAuthSupport": "true",
            "PowerState": "on",
        },
        "name": "[TV] Salon",
    }


def test_hit_extrae_identificadores_estables():
    hit = _hit_desde_api("192.168.1.50", _payload_api())
    assert "uuid:00000000-0000-4000-8000-000000000001" in hit.identificadores
    assert hit.modelo == "UE55TU7190UXZG"
    assert Protocol.TIZEN_WEBSOCKET in hit.anuncios


def test_barrido_rest_solo_devuelve_tizen(monkeypatch):
    monkeypatch.setattr(
        "conexion_tv.discovery.scan._puerto_abierto",
        lambda ip, puerto, timeout=0.6: ip == "192.168.1.50",
    )

    def opener(url: str) -> bytes:
        assert "192.168.1.50" in url
        return json.dumps(_payload_api()).encode()

    hits = barrer_rest(["192.168.1.50", "192.168.1.51"], opener=opener, workers=2)
    assert len(hits) == 1
    assert hits[0].ip == "192.168.1.50"


def test_escanear_anuncia_sin_marcar_como_funciona(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "conexion_tv.discovery.scan._puerto_abierto",
        lambda ip, puerto, timeout=0.6: ip.endswith(".50"),
    )
    monkeypatch.setattr("conexion_tv.discovery.scan.descubrir_ssdp", lambda **k: {})
    monkeypatch.setattr(
        "conexion_tv.discovery.scan.redes_locales",
        lambda: [IPv4Network("192.168.1.0/30")],
    )

    def opener(url: str) -> bytes:
        return json.dumps(_payload_api()).encode()

    memoria = DeviceMemory(ruta=tmp_path / "devices.json")
    registros = escanear(
        memoria, red=IPv4Network("192.168.1.48/30"), opener=opener, incluir_ssdp=False
    )

    assert len(registros) == 1
    registro = registros[0]
    assert registro.modelo == "UE55TU7190UXZG"
    # Un escaneo anuncia; no afirma que el mando funcione.
    assert registro.estado(Protocol.TIZEN_WEBSOCKET) is ProtocolState.ANNOUNCED
    assert registro.ultima_ip == "192.168.1.50"
