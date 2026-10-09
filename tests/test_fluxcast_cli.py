from conexion_tv.core.device_memory import DeviceRecord
from conexion_tv.core.protocols import Protocol
from conexion_tv.mirror.backends.fluxcast.adapter import (
    _elegir_par,
    _peer_mac_del_registro,
)
from conexion_tv.mirror.backends.fluxcast.cli import (
    WfdPeer,
    _pares_desde_salida,
    construir_comando,
    es_fallo_p2p_reintentable,
    extraer_estado_enlace,
    motivo_fallo_desde_log,
    traducir_registro,
)


def test_construir_comando_no_importa_fluxcast_y_fuerza_x11():
    cmd = construir_comando(
        binario="/opt/fluxcast",
        peer="aa:bb:cc:dd:ee:01",
        ancho=1280,
        alto=720,
        fps=30,
        bitrate_kbps=3000,
        audio=True,
        monitor="eDP-1",
        captura="x11grab",
    )
    assert cmd[0] == "/opt/fluxcast"
    assert "--protocol" in cmd and "wfd" in cmd
    assert "--wfd-no-firewall" in cmd
    assert "--wfd-capture-backend" in cmd and "x11grab" in cmd
    assert "--wfd-peer" in cmd and "aa:bb:cc:dd:ee:01" in cmd
    assert "1280x720" in cmd
    assert "--wfd-no-audio" not in cmd


def test_comando_pasa_fuente_de_audio_y_entrada_remota():
    cmd = construir_comando(
        binario="fluxcast",
        peer="aa:bb:cc:dd:ee:01",
        ancho=1920,
        alto=1080,
        fps=60,
        bitrate_kbps=14000,
        audio=True,
        captura="portal",
        audio_device="alsa_output.pci-0000_01_00.1.hdmi-stereo.monitor",
        entrada_remota=True,
    )
    assert "1920x1080" in cmd
    assert cmd[cmd.index("--fps") + 1] == "60"
    assert "portal" in cmd
    assert "--wfd-audio-device" in cmd
    assert "--wfd-uibc" in cmd
    assert "--wfd-no-audio" not in cmd


def test_comando_pasa_ajustes_de_enlace():
    cmd = construir_comando(
        binario="fluxcast",
        peer="aa:bb:cc:dd:ee:01",
        ancho=1920,
        alto=1080,
        fps=60,
        bitrate_kbps=14000,
        audio=True,
        go_intent=15,
        rtsp_port=7237,
        rtp_source_port=19004,
        scan_timeout_s=12,
        p2p_backend="wpas",
        p2p_channel=6,
        media_pipeline="ffmpeg",
        wifi_interface="wlp0s20f3",
        test_pattern=True,
    )
    assert cmd[cmd.index("--wfd-go-intent") + 1] == "15"
    assert cmd[cmd.index("--wfd-rtsp-port") + 1] == "7237"
    assert cmd[cmd.index("--wfd-rtp-source-port") + 1] == "19004"
    assert cmd[cmd.index("--wfd-timeout") + 1] == "12"
    assert cmd[cmd.index("--wfd-p2p-backend") + 1] == "wpas"
    assert cmd[cmd.index("--wfd-p2p-channel") + 1] == "6"
    assert cmd[cmd.index("--wfd-media-pipeline") + 1] == "ffmpeg"
    assert "wlp0s20f3" in cmd
    assert "--wfd-test-pattern" in cmd


def test_comando_por_defecto_no_fuerza_go_ni_puertos():
    cmd = construir_comando(
        binario="fluxcast",
        peer="aa:bb:cc:dd:ee:01",
        ancho=1280,
        alto=720,
        fps=30,
        bitrate_kbps=4000,
        audio=True,
    )
    assert "--wfd-go-intent" not in cmd
    assert "--wfd-rtsp-port" not in cmd
    assert "--wfd-p2p-backend" not in cmd


def test_extrae_hechos_del_log_de_sesion():
    hechos = extraer_estado_enlace(
        """
[FluxCast WFD] NM active connection: activated; p2p-dev-wlp0s20f3/p2p-wlp0s20-3:activated:0
[FluxCast WFD RTSP] TV connected from 10.42.0.75:59630; local=10.42.0.1
[FluxCast WFD RTSP] Negotiated media mode: 1920x1080p60
[FluxCast WFD RTSP]   wfd_video_formats: 40 00 01 10 000001e3
[FluxCast WFD RTSP]   wfd_audio_codecs: LPCM 00000003 00, AAC 00000001 00
[FluxCast WFD RTSP]   wfd_content_protection: HDCP2.1 port=9999
[FluxCast WFD RTSP]   Session: 1947897
[FluxCast WFD Media] RTP target      : 10.42.0.75:19000 from local port 19002
"""
    )
    assert hechos.interface == "p2p-wlp0s20-3"
    assert hechos.local_ip == "10.42.0.1"
    assert hechos.tv_ip == "10.42.0.75"
    assert hechos.mode == "1920x1080p60"
    assert hechos.rtp == "10.42.0.75:19000"
    assert hechos.session_id == "1947897"
    assert "AAC" in hechos.advertised_audio


def test_comando_acota_bitrate_por_encima_del_tope():
    cmd = construir_comando(
        binario="fluxcast",
        peer="aa:bb:cc:dd:ee:01",
        ancho=1920,
        alto=1080,
        fps=60,
        bitrate_kbps=20000,
        audio=True,
    )
    assert "20000k" not in cmd
    assert "16000k" in cmd


def test_sin_audio_anade_el_flag():
    cmd = construir_comando(
        binario="fluxcast",
        peer="aa:bb:cc:dd:ee:01",
        ancho=1920,
        alto=1080,
        fps=30,
        bitrate_kbps=8000,
        audio=False,
    )
    assert "--wfd-no-audio" in cmd


def test_parsea_salida_de_escaneo_wfd():
    texto = """
Scanning for WFD peers...
[1] AA:BB:CC:DD:EE:01  [TV] Salon
    WFD capability data detected
[2] 11:22:33:44:55:66  other
"""
    pares = _pares_desde_salida(texto)
    assert [p.mac for p in pares] == ["aa:bb:cc:dd:ee:01", "11:22:33:44:55:66"]


def test_mac_p2p_desde_la_wifi_sin_escanear():
    registro = DeviceRecord(clave="mac:aa:bb:cc:dd:ee:01", nombre="[TV] Salon")
    assert _peer_mac_del_registro(registro) == "a8:bb:cc:dd:ee:01"


def test_mac_p2p_usa_la_guardada_en_memoria():
    registro = DeviceRecord(clave="mac:aa:bb:cc:dd:ee:01", nombre="[TV] Salon")
    registro.anotar_anuncio(Protocol.MIRACAST_WFD, datos={"peer_mac": "a8:bb:cc:dd:ee:01"})
    assert _peer_mac_del_registro(registro) == "a8:bb:cc:dd:ee:01"


def test_fallo_sin_ip_p2p_se_puede_reintentar():
    motivo = motivo_fallo_desde_log(
        "selected TV IP not found for MAC A8:BB:CC:DD:EE:01 on p2p-wlp0s20-5"
    )
    assert motivo is not None
    assert es_fallo_p2p_reintentable(motivo)


def test_elige_el_par_por_mac_wifi_direct():
    """La MAC P2P no es la de la red: Samsung invierte un bit (bc → be)."""
    registro = DeviceRecord(clave="mac:aa:bb:cc:dd:ee:01", nombre="[TV] Salon")
    pares = [WfdPeer("a8:bb:cc:dd:ee:01", "[TV] Salon")]
    elegido = _elegir_par(pares, registro)
    assert elegido is not None
    assert elegido.mac == "a8:bb:cc:dd:ee:01"


def test_elige_el_par_por_mac_del_registro():
    registro = DeviceRecord(clave="mac:aa:bb:cc:dd:ee:01", nombre="[TV] Salon")
    pares = [
        WfdPeer("11:22:33:44:55:66", "otro"),
        WfdPeer("aa:bb:cc:dd:ee:01", "[TV] Salon"),
    ]
    elegido = _elegir_par(pares, registro)
    assert elegido is not None
    assert elegido.mac == "aa:bb:cc:dd:ee:01"


def test_detecta_tv_sin_ip_en_p2p():
    motivo = motivo_fallo_desde_log(
        "Active probe: selected TV IP not found for MAC A8:BB:CC:DD:EE:01 "
        "on p2p-wlp0s20-2; refusing an unverified fallback."
    )
    assert motivo is not None
    assert "Screen Sharing" in motivo


def test_detecta_puerto_7236_ocupado():
    motivo = motivo_fallo_desde_log("OSError: [Errno 98] Address already in use")
    assert motivo is not None
    assert "7236" in motivo


def test_traduce_el_log_de_negociacion():
    texto = """
[FluxCast WFD] Connecting to [TV] Salon via NetworkManager...
[FluxCast WFD RTSP] Negotiated media mode: 1280x720p30
[FluxCast WFD RTSP] PLAY accepted; media stream started.
CSeq: 3
"""
    out = traducir_registro(texto)
    assert "Connecting over Wi-Fi Direct" in out
    assert "1280x720p30" in out
    assert "PLAY" in out
    assert "CSeq" not in out
