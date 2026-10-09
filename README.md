# Linux ↔ Samsung TV connection

Desktop Python application to connect a Linux computer to a Samsung TV over
Wi-Fi: **screen projection with audio** and **remote control of the TV**.

The app uses only the **local network** (LAN and Wi-Fi Direct). It never
contacts the public Internet or cloud services.

> **Status: early development.** TV control works against the real set.
> Miracast/WFD projection is verified (image and audio at 720p30 and 1080p60).
> Read [`docs/ESTADO_ACTUAL.md`](docs/ESTADO_ACTUAL.md) for the up-to-date
> status.

## What it does

| Feature | Status |
|---|---|
| TV control (keys, volume, inputs) | ✅ verified on the set |
| TV discovery on the network | ✅ verified |
| Device memory and working protocols | ✅ implemented |
| Sender diagnostics | ✅ `python3 -m conexion_tv doctor` |
| Discovery persisted in memory | ✅ `python3 -m conexion_tv scan` |
| Screen projection with audio via Miracast | ✅ verified (720p30 / 1080p60, AAC) |
| Projection via DLNA (plan B) | ⏳ protocol confirmed, not implemented |
| Power-on via Wake-on-LAN | ⏳ not verified |
| PyQt6 graphical interface | ✅ remote + Screen share; Display tab editable |
| Extended desktop (TV as second monitor) | ⏳ goal; not implemented (WFD max 1080p60) |

## Why it exists

Sharing a Linux screen onto a Samsung Tizen set is surprisingly hard, and most
paths that look obvious are closed:

- **Chromecast** does not exist on Samsung Tizen. It is a hardware absence.
- **AirPlay 2** is supported on 2019+ TVs, but there is no working AirPlay
  sender for Linux.
- **DLNA** survives on some models, but it is not true mirroring and latency
  is 5 to 20 seconds.
- Samsung **Smart View** and **Screen Sharing** are proprietary Windows and
  macOS clients.

What remains is **Miracast / Wi-Fi Display**, which does real mirroring with
audio and low latency, but requires crossing four layers: Wi-Fi Direct, RTSP
signalling, RTP transport, and real-time H.264 encoding.

The full analysis, with the verdict for each path and its rationale, is in
[`docs/PROTOCOLOS.md`](docs/PROTOCOLOS.md).

## Architecture

Two independent subsystems behind their own interfaces, so the GUI knows
nothing about protocols:

```
ScreenMirroring              TVController
  connect()                    power_on()
  start_stream()               send_key()
  stop_stream()                set_volume()
  disconnect()                 launch_app()
  capabilities()               get_state()
      │                            │
      ├── FluxCastBackend          └── TizenWebSocketController
      ├── DlnaBackend                  (+ WakeOnLan, DIAL)
      ├── NativeMiracastBackend
      └── ChromecastBackend / AirPlayBackend
```

Adding a new protocol does not require touching the core or the UI. Detail is
in [`docs/PLAN_DESARROLLO.md`](docs/PLAN_DESARROLLO.md).

### Device memory

The application **remembers what works with each set**. It scans first and
offers options afterward, with five states per protocol: `unknown`,
`announced`, `working`, `failing`, and `unsupported`.

When something does not work, it shows what to configure on the TV and on the
computer instead of only reporting an error. And it **always allows retry**,
because causes are usually configuration-related and transient.

Design in [`docs/MEMORIA_DISPOSITIVOS.md`](docs/MEMORIA_DISPOSITIVOS.md).

## Development environment

Tested on Ubuntu 22.04 with GNOME on X11, Python 3.10, PipeWire, and an Intel
AX211 Wi-Fi card with Wi-Fi Direct.

```bash
sudo apt install -y python3.10-venv ffmpeg iw gstreamer1.0-plugins-bad vainfo

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Miracast also needs port **7236/tcp** open. The application opens and closes
it for the session only, with a visible switch and elevation via `pkexec`, so
it is not left open the rest of the time.

## Third-party dependencies

- [`samsungtvws`](https://github.com/xchwarze/samsung-tv-ws-api) — Tizen
  WebSocket control channel.
- [FluxCast](https://github.com/IlyaP358/fluxcast) (GPL-3.0) — Miracast stack.
  **Invoked as an external process**, never imported, and all use is confined
  to `conexion_tv/mirror/backends/fluxcast/`. The process boundary keeps
  GPL-3.0 out of the rest of the code, and a test fails if an import appears
  in any other module.

## Documentation

| Document | Contents |
|---|---|
| [`docs/ESTADO_ACTUAL.md`](docs/ESTADO_ACTUAL.md) | Where the project stands and what blocks progress |
| [`docs/REQUISITOS.md`](docs/REQUISITOS.md) | What to build and decisions taken |
| [`docs/PLAN_DESARROLLO.md`](docs/PLAN_DESARROLLO.md) | Architecture and phases |
| [`docs/PROTOCOLOS.md`](docs/PROTOCOLOS.md) | Technical research and discarded paths |
| [`docs/MEMORIA_DISPOSITIVOS.md`](docs/MEMORIA_DISPOSITIVOS.md) | Device and protocol memory |
