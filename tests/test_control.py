import pytest

from conexion_tv.control.base import PowerState
from conexion_tv.control.keys import TECLAS, por_grupo
from conexion_tv.control.tizen import TizenWebSocketController
from conexion_tv.core.device_memory import DeviceMemory
from conexion_tv.core.errors import DeviceUnreachableError
from conexion_tv.core.protocols import Protocol


class FakeTV:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.keys: list[str] = []
        self.closed = False

    def rest_device_info(self):
        return {"device": {"PowerState": "on", "modelName": "UE55TU7190UXZG"}}

    def send_key(self, key: str):
        self.keys.append(key)

    def close(self):
        self.closed = True


@pytest.fixture
def registro(tmp_path):
    mem = DeviceMemory(ruta=tmp_path / "devices.json")
    return mem.registrar(
        ["uuid:00000000-0000-4000-8000-000000000001", "aa:bb:cc:dd:ee:01"],
        nombre="[TV] Salon",
        modelo="UE55TU7190UXZG",
        ip="192.168.1.50",
    )


def test_el_mando_tiene_direccion_volumen_y_navegacion():
    grupos = {t.grupo for t in TECLAS}
    assert {"direccion", "volumen", "navegacion", "alimentacion"} <= grupos
    assert len(por_grupo("direccion")) == 5


def test_connect_abre_el_canal_y_recuerda_el_exito(registro, monkeypatch, tmp_path):
    fake = FakeTV()
    monkeypatch.setattr("samsungtvws.SamsungTVWS", lambda **kw: fake)
    monkeypatch.setattr(
        "conexion_tv.control.tizen.token_path",
        lambda clave: tmp_path / "token.txt",
    )

    ctrl = TizenWebSocketController(registro)
    ctrl.connect()
    ctrl.send_key("KEY_VOLUP")
    ctrl.disconnect()

    assert fake.keys == ["KEY_VOLUP"]
    assert fake.closed
    assert registro.memoria(Protocol.TIZEN_WEBSOCKET).exitos == 1


def test_send_key_sin_conectar_falla_claro(registro):
    ctrl = TizenWebSocketController(registro)
    with pytest.raises(DeviceUnreachableError, match="remote channel"):
        ctrl.send_key("KEY_HOME")


def test_power_on_usa_la_mac_del_alias(registro, monkeypatch):
    enviadas = []
    monkeypatch.setattr("conexion_tv.control.tizen.wake", lambda mac, **k: enviadas.append(mac))
    ctrl = TizenWebSocketController(registro)
    ctrl.power_on()
    assert enviadas == ["aa:bb:cc:dd:ee:01"]


def test_get_state_lee_powerstate(registro, monkeypatch, tmp_path):
    monkeypatch.setattr("samsungtvws.SamsungTVWS", lambda **kw: FakeTV())
    monkeypatch.setattr(
        "conexion_tv.control.tizen.token_path",
        lambda clave: tmp_path / "token.txt",
    )
    ctrl = TizenWebSocketController(registro)
    ctrl.connect()
    assert ctrl.get_state().alimentacion is PowerState.ON
