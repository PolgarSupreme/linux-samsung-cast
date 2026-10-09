# Linux ↔ Samsung TV connection

Desktop Python application to connect a Linux computer to a Samsung TV over
Wi-Fi: **screen projection with audio** and **remote control of the TV**.

The app uses only the **local network** (LAN and Wi-Fi Direct). It never
contacts the public Internet or cloud services.

> **Status:** TV control and Miracast/WFD projection are verified on a real
> Samsung UE55TU7190 (Tizen 5.5): image and audio at **720p30** and **1080p60**.
> Extended desktop (TV as a second monitor) is planned but not implemented yet.
> See [`docs/ESTADO_ACTUAL.md`](docs/ESTADO_ACTUAL.md) for the latest status.

## What it does

| Feature | Status |
|---|---|
| TV control (keys, volume, inputs) | ✅ verified on the set |
| TV discovery on the network | ✅ verified |
| Device memory and working protocols | ✅ implemented |
| Sender diagnostics | ✅ `python3 -m conexion_tv doctor` |
| Discovery persisted in memory | ✅ `python3 -m conexion_tv scan` |
| Screen projection with audio via Miracast | ✅ verified (720p30 / 1080p60, AAC) |
| Choose where audio is heard (TV / PC / both) | ✅ virtual audio bus |
| Projection via DLNA (plan B) | ⏳ protocol confirmed, not implemented |
| Power-on via Wake-on-LAN | ⏳ not verified |
| PyQt6 graphical interface | ✅ Devices, Screen, Remote, Diagnostics |
| Extended desktop (TV as second monitor) | ⏳ goal; WFD max 1080p60 |

## Requirements

### On the computer

Tested on **Ubuntu 22.04** with **GNOME on X11**, Python 3.10, PipeWire, and an
Intel AX211 Wi-Fi card with Wi-Fi Direct.

- Python 3.10+
- `ffmpeg`, `iw`, GStreamer (bad plugins), optional `vainfo` for hardware H.264
- **NetworkManager** with a `wifi-p2p` interface (`wpa_supplicant` backend; **not** iwd)
- **FluxCast** for Miracast (installed in a separate virtualenv; see below)
- `pkexec` if you want the app to open firewall port **7236/tcp** only during a session

### On the TV

Samsung Tizen sets from 2018–2020 with Miracast / Screen Sharing. The app was
developed against a **UE55TU7190UXZG** (Crystal UHD, Tizen 5.5).

Before sharing the screen, put the TV in the correct mode:

1. Press **Source** on the remote.
2. Open **Remote Access** (*Acceso remoto*).
3. Choose **Screen Sharing** (*Uso compartido de pantalla*) — **not** Remote PC
   or Knox/Secure.
4. The TV waits for a sender. Your Linux PC **will not** appear in Samsung’s
   “compatible with Windows 10” list; the computer finds the TV over Wi-Fi
   Direct when you press **Share screen**.

## Installation

```bash
# System packages (Ubuntu 22.04)
sudo apt install -y python3.10-venv ffmpeg iw gstreamer1.0-plugins-bad vainfo

# Application
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Miracast engine (GPL-3.0, isolated in its own venv)
python3 -m venv .venv-fluxcast
.venv-fluxcast/bin/pip install fluxcast --no-deps

# Verify the sender
python3 -m conexion_tv doctor
pytest
```

If `doctor` reports a missing P2P interface, confirm Wi-Fi Direct is supported
and that NetworkManager (not iwd) manages Wi-Fi.

Optional: to **prefer 5 GHz** for the Wi-Fi Direct link, install FluxCast’s
D-Bus policy for `wpa_supplicant` and choose the 5 GHz channel in the Screen
tab. Without that policy the app falls back to NetworkManager’s automatic
channel (often 2.4 GHz).

## Running the application

### Graphical interface (default)

```bash
source .venv/bin/activate
python3 -m conexion_tv          # same as: python3 -m conexion_tv gui
```

### Command line

| Command | Purpose |
|---|---|
| `python3 -m conexion_tv doctor` | Check ffmpeg, VAAPI, P2P, FluxCast, pkexec, etc. |
| `python3 -m conexion_tv scan` | Search the LAN for Samsung TVs and show protocol status |
| `python3 -m conexion_tv memory` | List devices remembered from past sessions |

Legacy Spanish aliases still work: `diagnostico`, `escanear`, `memoria`.

## Using the GUI

The window has four tabs.

### Devices

- **Scan network** finds Samsung TVs on your subnet (ports 8001/8002, SSDP).
- Select a device to see its model, IP, and which protocols are known to work.
- The app remembers devices in `~/.local/share/conexion_tv/devices.json` and
  matches them by MAC/UDN, not by IP (DHCP may change addresses).

### Screen

This is where you configure and start Miracast projection.

**Typical workflow**

1. On the TV: **Source → Remote Access → Screen Sharing**.
2. In the app, open **Screen** and review the **Source / Media / Destination**
   graph at the top.
3. Press **Share screen**. Approve the firewall prompt (`pkexec`) if asked.
4. Accept any connection prompt on the TV.
5. When finished, press **Stop**. Port 7236 closes if the firewall option was enabled.

**Source column**

| Setting | Meaning |
|---|---|
| Display | Which monitor is captured and sent to the TV |
| Capture method | **Direct X11** is the verified path on X11; use GStreamer if the picture stays black |
| Audio source | Pulse/PipeWire output whose monitor FluxCast reads (via the virtual audio bus) |

**Media column**

| Setting | Meaning |
|---|---|
| Resolution and fps | Presets include 720p30 and 1080p60 (verified). 20 Mb/s does not connect on this set |
| Bitrate | 2–16 Mb/s; lower this if video or audio stutters (radio saturation, not buffer size) |
| Pipeline | Automatic ffmpeg, or GStreamer as a fallback |

**Destination column**

| Setting | Meaning |
|---|---|
| Where you hear it | **TV only** — apps play to a virtual sink, audio goes to the TV, no PC loopback |
| | **Computer and TV** — same virtual sink plus loopback to your speakers |
| | **Computer only** — no audio over Miracast (restarts the session when changed) |

Collapsible sections below the graph expose more detail:

- **Connection status** — live state, negotiated mode, Direct-link IPs, firewall toggle.
- **Wi-Fi Direct link** — Wi-Fi radio, P2P backend (NetworkManager vs wpa_supplicant),
  group owner, P2P channel, scan timeout, **Clear Direct link** (use after a bad
  disconnect; do not press while mirroring).
- **Picture / Sound / RTSP** — extra hints and advanced knobs.

While streaming, some settings can be changed with **Apply** without a full
reconnect; others require stopping and sharing again.

### Remote

1. Select your TV on the **Devices** tab.
2. Press **Connect remote**. The first time, accept the pairing dialog on the TV.
   The token is saved for later sessions.
3. Use the on-screen remote for direction, OK, back, home, volume, mute, channels,
   and HDMI input selection.
4. **Power on (WoL)** sends Wake-on-LAN if the set supports it (not verified on all models).

Remote control works **independently** of screen sharing: you can control the TV
even when not mirroring.

### Diagnostics

Shows the same checks as `doctor`, with a **Refresh** button. Fix any **FAIL**
items before troubleshooting projection.

## Audio routing (how it works)

System audio is routed through a **virtual Pulse/PipeWire sink** while mirroring:

```
Applications → virtual sink → FluxCast (.monitor) → Miracast AAC → TV
                              ↘ loopback (optional) → PC speakers
```

- **TV only:** no loopback; you hear nothing on the PC unless the TV is your
  audio output (e.g. HDMI).
- **Both:** loopback to the real sink so PC and TV play the same audio.
- **PC only:** Miracast carries no audio.

You can switch between **TV only** and **both** during a session without
renegotiating RTSP.

## Firewall and port 7236

Miracast uses **RTSP on TCP port 7236** on the computer (the TV connects to
you, not the other way around). If `ufw` or similar blocks it, enable **Open
firewall port 7236 when sharing** on the Screen tab. The app opens the port
only for the session and closes it when you stop, using `pkexec` for elevation.

## Troubleshooting

| Symptom | What to try |
|---|---|
| TV not found when sharing | TV must be in **Screen Sharing**, not Remote PC. Wait a few seconds, then retry |
| Choppy video or audio dropouts | P2P may be on 2.4 GHz with limited throughput. Lower bitrate (e.g. 8 Mb/s) or switch to **720p30** |
| Port 7236 busy | Stop the previous session or press **Clear Direct link** (TV back in Screen Sharing) |
| Black screen | Try **GStreamer over X11** capture or check Diagnostics for ffmpeg/VAAPI |
| Remote works, mirror does not | Run `doctor`; confirm FluxCast is installed and P2P interface exists |
| Reconnect fails after crash | TV in Screen Sharing, **Clear Direct link**, cycle PC Wi-Fi if needed |

On Samsung sets, FluxCast sets the encoder VBV buffer to **2× the bitrate**
(~2 s). There is no separate buffer control; dropouts from a saturated radio
are fixed by **bitrate or resolution**, not by enlarging a buffer.

More detail: [`docs/PROTOCOLOS.md`](docs/PROTOCOLOS.md) (negotiation, P2P, TV menu).

## Why it exists

Sharing a Linux screen onto a Samsung Tizen set is surprisingly hard, and most
paths that look obvious are closed:

- **Chromecast** does not exist on Samsung Tizen.
- **AirPlay 2** is supported on 2019+ TVs, but there is no working AirPlay
  sender for Linux.
- **DLNA** survives on some models, but it is not true mirroring and latency
  is 5 to 20 seconds.
- Samsung **Smart View** and **Screen Sharing** are proprietary Windows and
  macOS clients.

What remains is **Miracast / Wi-Fi Display**: real mirroring with audio and
low latency, crossing Wi-Fi Direct, RTSP signalling, RTP transport, and
real-time H.264 encoding. The full analysis is in
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
      └── …
```

The app **remembers what works with each TV** (protocol states: `unknown`,
`announced`, `working`, `failing`, `unsupported`) and offers configuration
hints when something fails. See [`docs/PLAN_DESARROLLO.md`](docs/PLAN_DESARROLLO.md)
and [`docs/MEMORIA_DISPOSITIVOS.md`](docs/MEMORIA_DISPOSITIVOS.md).

## Privacy

- The repository ships an **anonymized example** device sheet in
  `tests/datos/tv_ejemplo.json`.
- Real device data (`INFO/tv_samsung.json`, photos, tokens) stays **local**
  and is listed in `.gitignore`.
- Runtime device memory lives in `~/.local/share/conexion_tv/`.

## Third-party dependencies

- [`samsungtvws`](https://github.com/xchwarze/samsung-tv-ws-api) — Tizen
  WebSocket control channel.
- [FluxCast](https://github.com/IlyaP358/fluxcast) (GPL-3.0) — Miracast stack,
  **invoked as an external process** only inside
  `conexion_tv/mirror/backends/fluxcast/`. A test fails if FluxCast is imported
  elsewhere, keeping GPL-3.0 isolated from the rest of the code.

## Documentation

| Document | Contents |
|---|---|
| [`docs/ESTADO_ACTUAL.md`](docs/ESTADO_ACTUAL.md) | Current status and session log |
| [`docs/REQUISITOS.md`](docs/REQUISITOS.md) | Functional requirements and decisions |
| [`docs/PLAN_DESARROLLO.md`](docs/PLAN_DESARROLLO.md) | Architecture and phases |
| [`docs/PROTOCOLOS.md`](docs/PROTOCOLOS.md) | Technical research and TV setup |
| [`docs/MEMORIA_DISPOSITIVOS.md`](docs/MEMORIA_DISPOSITIVOS.md) | Device and protocol memory |

## License

Application code: see repository license. FluxCast is GPL-3.0 and runs as a
separate process; see FluxCast’s repository for its terms.
