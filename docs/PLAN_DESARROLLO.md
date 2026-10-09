# Development plan

> Last review: 2026-10-07 (revision 2).
> **Revision 2:** incorporates the modular backend architecture decided by the
> user and knowledge of the exact TV model.
> GUI toolkit: **PyQt6**. FluxCast is invoked as an external process.

## Guiding principle

Project risk is not evenly distributed. TV control is a solved problem with a
mature library; Miracast mirroring is the fragile part, because it depends on
an RTSP negotiation that each vendor interprets in its own way. Therefore the
plan **attacks the high risk first with a command-line prototype**, before
writing a single line of GUI. If the TV does not negotiate WFD, it is better
to know on day one.

## Architecture decision: encapsulate FluxCast

FluxCast is GPL-3.0. We use it to start quickly and validate real
compatibility with the TV, but it is **never called from the rest of the
code**. All use sits behind our own interface, so that:

- Code affected by GPL-3.0 lives in **a single isolated module**
  (`mirror/backends/fluxcast/`), and can be replaced without touching anything
  else.
- The interface is designed from **our needs**, not from FluxCast’s API. If
  the interface ends up looking like FluxCast, the encapsulation is useless.
- Any FluxCast-specific concept (flags, transport names, error models) is
  **translated** at the adapter boundary.

## Architecture

Four layers. The UI knows nothing about protocols, and protocols know nothing
about the UI. **Projection and control are separate subsystems** that only
meet in the core.

```
┌─────────────────────────────────────────────────────────────┐
│                     Graphical interface                     │
│   Devices · Projection · Remote · Diagnostics               │
└───────────────────────────┬─────────────────────────────────┘
                            │ async events, no blocking calls
┌───────────────────────────┴─────────────────────────────────┐
│                         Core                                │
│   Session · State · Config · Events · Logging               │
│   Device sheet ← INFO/tv_samsung.json                       │
└──────┬─────────────────────┬──────────────────────┬─────────┘
       │                     │                      │
┌──────┴───────┐  ┌──────────┴──────────┐  ┌────────┴────────┐
│ Discovery    │  │   ScreenMirroring   │  │  TVController   │
│              │  │   (interface)       │  │  (interface)    │
│              │  │                     │  │                 │
│ network+P2P  │  │ connect()           │  │ power_on()      │
│              │  │ start_stream()      │  │ send_key()      │
│              │  │ stop_stream()       │  │ set_volume()    │
│              │  │ disconnect()        │  │ launch_app()    │
│              │  │ capabilities()      │  │ get_state()     │
└──────────────┘  └──────────┬──────────┘  └────────┬────────┘
                             │                      │
        ┌────────────┬───────┴────────┬──────┐      │
        │            │                │      │      │
   ┌────┴─────┐ ┌────┴─────┐ ┌────────┴──┐ ┌─┴───┐ │
   │FluxCast  │ │Native    │ │DLNA/UPnP  │ │Cast │ │
   │Backend   │ │Miracast  │ │Backend    │ │ ... │ │
   │(GPL-3.0, │ │Backend   │ │           │ │     │ │
   │ isolated)│ │(future)  │ │           │ │     │ │
   └──────────┘ └──────────┘ └───────────┘ └─────┘ │
                                                    │
                                   ┌────────────────┴──────────┐
                                   │ TizenWebSocketController  │
                                   │ (+ WakeOnLan, DIAL)       │
                                   └───────────────────────────┘
```

### The `ScreenMirroring` interface

Contract every projection backend must satisfy:

| Method | Responsibility |
|---|---|
| `capabilities()` | What this backend supports: audio, expected latency, resolutions, whether it needs Wi-Fi Direct. Lets the UI offer only what is possible. |
| `is_available()` | Whether the backend can work **on this machine and with this device**, without trying to connect. Feeds diagnostics. |
| `connect(device)` | Establishes the transport link. For Miracast, the Wi-Fi Direct group and RTSP session. For DLNA, validate `AVTransport`. |
| `start_stream(config)` | Starts emission with a video and audio configuration. |
| `stop_stream()` | Stops emission leaving the link up, so it can be resumed. |
| `disconnect()` | Closes the link and **releases all resources**: child processes, P2P interfaces, firewall rules. |

Plus a common event channel: state changes, metrics (actual bitrate, dropped
frames, estimated latency), and errors already translated into the
application vocabulary.

**Golden rule:** states and errors are **ours**, not the backend’s. An RTSP
negotiation failure and an `AVTransport` failure reach the core as the same
error type, with the technical detail in the log.

### Planned backends

| Backend | Priority | Status |
|---|---|---|
| `FluxCastBackend` | 1 | Miracast/WFD via encapsulated FluxCast. First implementation. |
| `DlnaBackend` | 2 | UPnP `AVTransport` with HLS transport. This TV still has DLNA. |
| `NativeMiracastBackend` | 3 | Own WFD stack, without GPL-3.0. Only if FluxCast proves insufficient or licensing gets in the way. |
| `ChromecastBackend` | — | Useless with this TV (no Chromecast). Left planned for other devices. |
| `AirPlayBackend` | — | The TV is an AirPlay 2 receiver, but there is no Linux sender. Slot reserved. |

### The `TVController` interface

Subsystem **independent** of projection. Shares only the device sheet. First
and only planned implementation: `TizenWebSocketController`, with Wake-on-LAN
and DIAL as helper pieces.

Keeping them separate has a useful practical consequence: the remote works
even if projection is broken, and vice versa.

### Planned file structure

```
conexion_tv/
├── core/                   session, config, events, logging
│   ├── protocols.py        protocol catalogue and configuration tips
│   ├── device_memory.py    persistent memory of what works with each set
│   └── seed.py             seeds memory from INFO/tv_samsung.json
├── discovery/              network scan, REST /api/v2/, Wi-Fi Direct
├── control/
│   ├── base.py             TVController interface
│   ├── tizen_ws.py         WebSocket API v2 implementation
│   ├── wol.py              Wake-on-LAN
│   └── keys.py             key map
├── mirror/
│   ├── base.py             ScreenMirroring interface, capabilities, events
│   ├── registry.py         backend selection and preference order
│   └── backends/
│       ├── fluxcast/       ← only module with GPL-3.0 dependency
│       ├── dlna/
│       └── native_wfd/     (future)
├── diagnostics/            system checks
└── gui/                    main window and panels
INFO/tv_samsung.json        TV device sheet
docs/                       this documentation
tests/
```

GPL isolation is **structural, not a convention**: `mirror/backends/fluxcast/`
is the only place where `fluxcast` may be imported, and that is verified by a
test that fails if the import appears anywhere else.

## Phases

### Phase 0 · Validation on the real machine — *blocking*

Control, discovery, and diagnostics **no longer wait** on this test: they go
through a different subsystem. Projection does wait on seeing image and audio
at least once.

1. Power on the TV and connect it to the same Wi-Fi network as the computer.
2. Locate it by MAC (Wi-Fi or Ethernet) and read
   `GET http://<IP>:8001/api/v2/` to confirm the sheet.
3. Install what is missing: `ffmpeg`, `iw`, `gstreamer1.0-plugins-bad`,
   `vainfo`.
4. Confirm the adapter announces `P2P-client` and `P2P-GO` modes.
5. Open port 7236/tcp in the firewall.
6. **Fire test:** get image **and sound** on the TV with raw FluxCast from the
   terminal.

**Exit criterion:** image and audio on the TV, even with hand-tuned
parameters. If it fails, the plan changes and DLNA is evaluated as the main
path.

### Phase 1 · Core and TV control

The low-risk part, and the one that already delivers something useful.

- Load and validate `INFO/tv_samsung.json` as the device sheet.
- Discovery by subnet scan with REST identification.
- `TVController` interface and `TizenWebSocketController` implementation.
- Pairing with token persistence under `~/.config/`.
- Keys, volume, input change, application launch.
- Wake-on-LAN and power-off.
- Automatic reconnection when the link is lost.

**Exit criterion:** power on the TV from the computer, raise the volume, and
open an application, from a script.

### Phase 2 · `ScreenMirroring` interface and `FluxCastBackend`

- Define the interface and the event/error model **before** writing the
  adapter, so FluxCast’s API does not contaminate it.
- Implement `FluxCastBackend` translating in both directions.
- X11 video capture and audio from the PipeWire monitor.
- H.264 encoding via VAAPI with a software fallback.
- Test that forbids importing `fluxcast` outside the adapter module.
- Guaranteed cleanup of processes and P2P interfaces on disconnect.

**Exit criterion:** `start_stream()` and `stop_stream()` from Python, with
audio, leaving nothing orphaned.

### Phase 3 · Second backend: `DlnaBackend`

Implemented early, on purpose. **It is the proof that the abstraction
works:** a second backend with a radically different operating model (high
latency, goes through the router, the TV pulls the stream) forces the
interface to be honest. If `ScreenMirroring` only fits Miracast, it is poorly
designed, and better to discover that here than when writing the native
backend.

- UPnP `AVTransport` with HLS transport.
- Local HTTP server for the stream.
- Automatic backend selection based on what is available.

**Exit criterion:** switch backends from the application without the core or
the GUI knowing which one is active.

### Phase 4 · Graphical interface

- Main window with the device list and their status.
- Projection panel: session status, quality/audio/capture settings with
  explanations, apply changes (restarts the mirror), start and stop.
- Virtual remote, with keyboard shortcuts.
- Diagnostics panel.
- All heavy work in threads or async tasks, never on the GUI thread.

**Exit criterion:** a user who does not know the project powers on the TV,
shares the screen with sound, and stops it, without touching the terminal.

### Phase 5 · Robustness and packaging

- Recovery from P2P link drop and from TV power-off.
- File logging with rotation.
- System tray icon.
- Installer that leaves the D-Bus policy and dependencies ready.
- Usage and troubleshooting documentation.

### Phase 6 · Optional: `NativeMiracastBackend`

Only if needed: if FluxCast becomes limiting, stops being maintained, or
GPL-3.0 gets in the way of distribution. By then phase 2 will have paved the
way: implement the interface and change the registry preference.

## Risks

| Risk | Impact | How we mitigate it |
|---|---|---|
| The TV does not negotiate WFD with our stack | High | Validated by phase 0. Partly mitigated: third parties have run FluxCast with the 2020 TU70xx series |
| Missing audio in the mirror | High | Explicit exit criterion of phase 0. Classic failure of `gnome-network-displays` |
| The `ScreenMirroring` interface ends up shaped by FluxCast | High | Design it before the adapter, and validate it with the DLNA backend in phase 3 |
| GPL-3.0 contagion to the rest of the code | Medium | Structural isolation in one module, verified by test |
| Shared radio degrades the network | Medium | Documented as expected behaviour; impact is measured |
| Ubuntu 22.04 with GStreamer 1.20 and no Miracast packages | Medium | Rely on `ffmpeg` and PyPI, not distribution packages |
| X11 session instead of Wayland | Low | `x11grab` works well; the portal remains an alternative |

## How this documentation is maintained

- `INFO/tv_samsung.json` is the **single source** of device information. No
  module hard-codes TV data.
- `PROTOCOLOS.md` changes when something new is learned about protocols or
  hardware, especially observed negotiation failures.
- `REQUISITOS.md` changes when the user decides something or the scope
  changes.
- `ESTADO_ACTUAL.md` is updated **at the end of each work session**, and is
  the first file to read when resuming the project.
- This plan is reviewed at the close of each phase.
