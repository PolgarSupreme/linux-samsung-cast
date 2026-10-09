from conexion_tv.mirror.base import StreamConfig
from conexion_tv.mirror.caudal import (
    BITRATE_MAX_KBPS,
    acotar_bitrate,
    kbit_por_fotograma,
    pista_caudal,
)
from conexion_tv.mirror.prefs import cargar, guardar
from conexion_tv.mirror.remote_display import (
    RemoteDisplay,
    RemoteDisplayRuntime,
    audio_y_silencio,
    destino_desde_config,
)
from conexion_tv.mirror.video_modes import modo_desde_tamano, modo_por_id
from conexion_tv.mirror.virtual_audio import NULL_MONITOR, NULL_SINK, VirtualAudioBus


def test_modo_1080p60_existe_y_sugiere_bitrate_alto():
    modo = modo_por_id("1080p60")
    assert modo.ancho == 1920
    assert modo.fps == 60
    assert modo.bitrate_sugerido_kbps >= 8000
    assert modo_desde_tamano(1280, 720, 30) is not None


def test_prefs_redondean_viaje(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    original = StreamConfig(
        ancho=1920,
        alto=1080,
        fps=60,
        bitrate_kbps=14000,
        audio=True,
        mute_local=True,
        audio_device="sink.monitor",
        monitor="HDMI-0",
        captura="portal",
        gestionar_firewall=False,
        entrada_remota=True,
        go_intent=15,
        rtsp_port=7236,
        rtp_source_port=19002,
        scan_timeout_s=8,
        p2p_backend="nm",
        media_pipeline="ffmpeg",
        wifi_interface="wlp0s20f3",
        test_pattern=False,
    )
    guardar(original)
    leido = cargar()
    assert leido == original


def test_prefs_ausentes_devuelven_el_modo_probado():
    cfg = StreamConfig()
    assert cfg.ancho == 1280
    assert cfg.fps == 30
    assert cfg.captura == "x11"
    assert cfg.gestionar_firewall is True


def test_caudal_acota_el_20_mbps_que_no_conecta():
    assert acotar_bitrate(20000) == BITRATE_MAX_KBPS
    assert acotar_bitrate(500) == 2000
    assert acotar_bitrate(14000) == 14000
    assert kbit_por_fotograma(14000, 60) == 233
    assert "20 Mb/s" in pista_caudal(14000, 60)


def test_destino_audio_mapea_silencio_local():
    assert destino_desde_config(audio=True, mute_local=True) == "tv"
    assert destino_desde_config(audio=True, mute_local=False) == "both"
    assert destino_desde_config(audio=False, mute_local=False) == "pc"
    assert audio_y_silencio("tv") == (True, True)
    assert audio_y_silencio("both") == (True, False)
    assert audio_y_silencio("pc") == (False, False)


def test_remote_display_desde_stream_config():
    cfg = StreamConfig(ancho=1920, alto=1080, fps=60, bitrate_kbps=14000, mute_local=True)
    remota = RemoteDisplay.from_stream_config(cfg)
    assert remota.audio_route == "tv"
    assert remota.envia_audio() is True
    assert remota.altavoces_pc() is False


def test_bus_virtual_abre_null_y_loopback(monkeypatch):
    llamadas: list[tuple[str, ...]] = []
    null_ok = {"v": False}
    loop_ok = {"v": False}

    class _R:
        def __init__(self, stdout: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode

    def fake_run(cmd, **_kwargs):
        llamadas.append(tuple(cmd))
        args = tuple(cmd[1:])
        if args[:1] == ("load-module",) and args[1] == "module-null-sink":
            null_ok["v"] = True
            return _R("42")
        if args[:1] == ("load-module",) and args[1] == "module-loopback":
            loop_ok["v"] = True
            return _R("99")
        if args == ("list", "short", "sinks"):
            base = "3\thdmi\tmodule\ts16le\tIDLE\n"
            if null_ok["v"]:
                base += f"9\t{NULL_SINK}\tmodule-null-sink.c\ts16le\tIDLE\n"
            return _R(base)
        if args == ("get-default-sink",):
            return _R("hdmi")
        if args == ("list", "short", "sink-inputs"):
            return _R("7\t3\t12\tprotocol-native.c\tx")
        if args == ("list", "short", "modules"):
            lineas = []
            if null_ok["v"]:
                lineas.append(f"42\tmodule-null-sink\tsink_name={NULL_SINK}")
            if loop_ok["v"]:
                lineas.append(f"99\tmodule-loopback\tsource={NULL_MONITOR}")
            return _R("\n".join(lineas))
        if args[:1] == ("unload-module",):
            if args[1] == "99":
                loop_ok["v"] = False
            if args[1] == "42":
                null_ok["v"] = False
            return _R()
        return _R()

    monkeypatch.setattr("conexion_tv.mirror.virtual_audio.subprocess.run", fake_run)
    bus = VirtualAudioBus()
    assert bus.open() is True
    assert bus.monitor == NULL_MONITOR
    assert ("pactl", "set-default-sink", NULL_SINK) in llamadas
    assert ("pactl", "move-sink-input", "7", NULL_SINK) in llamadas
    assert bus.set_speakers(True) is True
    assert any(c[1:3] == ("load-module", "module-loopback") for c in llamadas)
    bus.close()
    assert ("pactl", "set-default-sink", "hdmi") in llamadas
    assert ("pactl", "unload-module", "42") in llamadas


def test_runtime_tv_sin_loopback_both_con_loopback(monkeypatch):
    llamadas: list[tuple[str, ...]] = []
    null_ok = {"v": False}
    loop_ok = {"v": False}

    class _R:
        def __init__(self, stdout: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode

    def fake_run(cmd, **_kwargs):
        llamadas.append(tuple(cmd))
        args = tuple(cmd[1:])
        if args[:1] == ("load-module",) and len(args) > 1 and args[1] == "module-null-sink":
            null_ok["v"] = True
            return _R("42")
        if args[:1] == ("load-module",) and len(args) > 1 and args[1] == "module-loopback":
            loop_ok["v"] = True
            return _R("99")
        if args == ("list", "short", "sinks"):
            base = "3\thdmi\tmodule\ts16le\tIDLE\n"
            if null_ok["v"]:
                base += f"9\t{NULL_SINK}\tmodule\ts16le\tIDLE\n"
            return _R(base)
        if args == ("get-default-sink",):
            return _R("hdmi")
        if args == ("list", "short", "sink-inputs"):
            return _R("")
        if args == ("list", "short", "modules"):
            lineas = []
            if null_ok["v"]:
                lineas.append(f"42\tmodule-null-sink\tsink_name={NULL_SINK}")
            if loop_ok["v"]:
                lineas.append(f"99\tmodule-loopback\tsource={NULL_MONITOR}")
            return _R("\n".join(lineas))
        if args[:1] == ("unload-module",):
            if args[1] == "99":
                loop_ok["v"] = False
            if args[1] == "42":
                null_ok["v"] = False
            return _R()
        return _R()

    monkeypatch.setattr("conexion_tv.mirror.virtual_audio.subprocess.run", fake_run)
    rt = RemoteDisplayRuntime()
    assert rt.apply_audio("tv") is True
    assert rt.pulse_capture_device() == NULL_MONITOR
    assert not any("module-loopback" in " ".join(c) for c in llamadas if c[1] == "load-module")
    assert rt.apply_audio("both") is True
    assert any(c[1:3] == ("load-module", "module-loopback") for c in llamadas)
    rt.close()


def test_prefs_acotan_bitrate_al_cargar(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    guardar(StreamConfig(bitrate_kbps=20000))
    leido = cargar()
    assert leido.bitrate_kbps == BITRATE_MAX_KBPS
