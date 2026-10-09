from conexion_tv.mirror.backends.fluxcast.cli import construir_comando
from conexion_tv.mirror.p2p_channel import (
    MATCH_AP_5GHZ,
    es_canal_24,
    es_canal_5,
    mhz_a_canal,
    preparar_config_para_canal,
    reg_class_para,
    requiere_fuerza_propia,
    resolver_canal,
)


def test_mhz_a_canal_2y5():
    assert mhz_a_canal(2412) == 1
    assert mhz_a_canal(2437) == 6
    assert mhz_a_canal(5180) == 36
    assert mhz_a_canal(5220) == 44
    assert mhz_a_canal(5000) is None


def test_reg_class():
    assert reg_class_para(1) == 81
    assert reg_class_para(44) == 115
    assert es_canal_24(11)
    assert es_canal_5(36)
    assert requiere_fuerza_propia(44)
    assert requiere_fuerza_propia(MATCH_AP_5GHZ)
    assert not requiere_fuerza_propia(6)
    assert not requiere_fuerza_propia(None)


def test_preparar_5ghz_obliga_wpas_y_go(monkeypatch):
    monkeypatch.setattr(
        "conexion_tv.mirror.p2p_channel.wpas_dbus_legible",
        lambda: True,
    )
    canal, backend, go, aviso = preparar_config_para_canal(
        p2p_channel=44,
        p2p_backend="nm",
        go_intent=None,
    )
    assert canal == 44
    assert backend == "wpas"
    assert go == 15
    assert aviso == ""


def test_preparar_5ghz_sin_dbus_degrada_a_nm(monkeypatch):
    monkeypatch.setattr(
        "conexion_tv.mirror.p2p_channel.wpas_dbus_legible",
        lambda: False,
    )
    canal, backend, go, aviso = preparar_config_para_canal(
        p2p_channel=MATCH_AP_5GHZ,
        p2p_backend="nm",
        go_intent=None,
    )
    assert canal is None
    assert backend == "nm"
    assert "D-Bus" in aviso


def test_match_ap_sin_iw_cae_en_36(monkeypatch):
    monkeypatch.setattr(
        "conexion_tv.mirror.p2p_channel.frecuencia_ap_asociado",
        lambda _iface=None: None,
    )
    assert resolver_canal(MATCH_AP_5GHZ) == 36


def test_match_ap_usa_canal_del_router(monkeypatch):
    monkeypatch.setattr(
        "conexion_tv.mirror.p2p_channel.frecuencia_ap_asociado",
        lambda _iface=None: 5220,
    )
    assert resolver_canal(MATCH_AP_5GHZ) == 44


def test_cli_no_pasa_canal_5ghz_a_fluxcast():
    cmd = construir_comando(
        binario="fluxcast",
        peer="aa:bb:cc:dd:ee:01",
        ancho=1920,
        alto=1080,
        fps=60,
        bitrate_kbps=8000,
        audio=True,
        p2p_backend="wpas",
        p2p_channel=44,
        go_intent=15,
    )
    assert "--wfd-p2p-channel" not in cmd
    assert cmd[cmd.index("--wfd-p2p-backend") + 1] == "wpas"


def test_cli_sigue_pasando_canal_24():
    cmd = construir_comando(
        binario="fluxcast",
        peer="aa:bb:cc:dd:ee:01",
        ancho=1280,
        alto=720,
        fps=30,
        bitrate_kbps=4000,
        audio=True,
        p2p_backend="wpas",
        p2p_channel=6,
    )
    assert cmd[cmd.index("--wfd-p2p-channel") + 1] == "6"
