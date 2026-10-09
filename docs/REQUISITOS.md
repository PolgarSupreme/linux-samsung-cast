# Requirements

> Last review: 2026-10-08 (revision 8).
> **Revision 8:** extended-desktop goal on the TV (not only mirroring).
> **Revision 7:** choose where audio is heard (TV, PC, or both).
> **Revision 6:** bitrate is the wait lever in the GUI.
> **Revision 5:** mirror verified; next, local audio mute and latency.
> **Revision 4:** the panel covers the Miracast sequence (Direct link, RTSP, media).
> **Revision 3:** the mirror panel exposes settings, status, and reconfiguration.
> **Revision 2:** TV identified, modular architecture decided.
> Items marked with ❓ await user confirmation.

## 1. Goal

A Python desktop application, with a graphical interface, that connects a
Linux computer to a Samsung TV over Wi-Fi to:

1. Share the computer screen on the TV (mirror).
2. **Use the TV as an extended display** of the Linux desktop (another
   logical monitor), not only as a copy of the primary.
3. Also send the computer’s audio.
4. Control the TV from the computer (power, volume, inputs, navigation,
   applications).

Over Wi-Fi Display this model **does not accept 4K**: the panel is 3840×2160,
but the Miracast sink negotiated at most **1920×1080p60**. The PC GPU can
generate more; the TV’s WFD protocol does not request it. See
[PROTOCOLOS.md](PROTOCOLOS.md).

## 2. Target environment

### Sending computer

Verified on 2026-10-07. Full detail in
[PROTOCOLOS.md § 7](PROTOCOLOS.md#7-sender-hardware-and-software).

- Ubuntu 22.04.5 LTS, GNOME 42, **X11** session
- Python 3.10.12
- Intel AX211 Wi-Fi with Wi-Fi Direct available and `wpa_supplicant` as backend
- PipeWire + PulseAudio, GStreamer 1.20, Intel iGPU with VAAPI
- Home IPv4 network behind a home router, same subnet as the TV

Portability to other distributions is not a goal for the first version, but
the code must not assume Ubuntu paths or package names outside the diagnostics
layer.

### Receiving TV

**Samsung UE55TU7190UXZG**, Crystal UHD TU7190 from 2020, Tizen 5.5.
Complete authoritative sheet in [`INFO/tv_samsung.json`](../INFO/tv_samsung.json).

Supports Miracast, Wi-Fi Direct, **DLNA**, AirPlay 2, and the Tizen WebSocket
API v2. Does not support Chromecast.

## 3. Functional requirements

### RF-1 · TV discovery

The application locates Samsung TVs without the user typing an IP.

- Scan the local subnet probing ports 8001/8002 and querying
  `GET /api/v2/` to confirm it is a Samsung and read its model.
- Recognize the known TV by its MACs (Wi-Fi and Ethernet) and by the UDN it
  announces, never by IP (DHCP).
- Discover Miracast receivers via Wi-Fi Direct.
- Manual IP entry as an alternative.
- Found devices are remembered across sessions.

### RF-2 · TV control

Subsystem **independent** of projection, behind a `TVController` interface.

- Connect to the Tizen WebSocket on port 8002, with the acceptance dialog on
  the TV and **token persistence** so it is not repeated.
- Virtual remote: direction, OK, back, home, volume, mute, channels, HDMI
  input selection.
- Launch TV applications by ID.
- Power-on via Wake-on-LAN and power-off via WebSocket.
- Read state: powered on, active input, volume.
- **Must work even if projection is down or unavailable.**

### RF-3 · Screen projection with audio

Behind a `ScreenMirroring` interface with swappable backends.

- Transmit the screen including system audio.
- **Mirror mode** (copy of a real monitor) and, as a goal, **extended mode**:
  a virtual monitor that the desktop treats as a second screen and that is
  sent to the TV. Pending implementation; WFD cap = 1080p60, not 4K.
- Select the monitor or window to share when there are multiple screens.
- Select the audio source (system output, a specific application, or no
  audio).
- **Remote display (`RemoteDisplay`):** the TV has its own video/audio/settings
  package. System audio goes to a **virtual sink**; FluxCast captures that
  monitor. “TV only” = no loopback to speakers; “both” = loopback to the real
  sink; “PC only” = no Miracast audio is sent.
- Quality controls: resolution, framerate, and **bitrate** as the wait/radio
  lever (2–16 Mb/s; 20 Mb/s does not connect); hardware encoding (VAAPI) with
  a software fallback.
- Stop and resume emission without restarting the application.
- **On disconnect no orphan resources remain**: no child processes, no P2P
  interfaces, no firewall rules.

### RF-4 · Modular backend architecture

- The `ScreenMirroring` interface exposes at least: `capabilities()`,
  `is_available()`, `connect()`, `start_stream()`, `stop_stream()`,
  `disconnect()`, plus an event channel.
- States, metrics, and errors that reach the core are from the
  **application vocabulary**, never from the backend.
- The FluxCast dependency (GPL-3.0) is confined to
  `mirror/backends/fluxcast/`. **An automated test fails if a `fluxcast`
  import appears outside that module.**
- Adding a new backend does not require touching the core or the GUI.
- The application chooses a backend automatically by availability, and allows
  forcing it manually.

### RF-5 · Graphical interface

- A single window with connection status always visible.
- Separate panels for devices, projection, remote, and diagnostics.
- The UI **never blocks**: all network and capture work happens off the GUI
  thread.
- Error messages in clear language, with the concrete action to take
  (“turn on the TV”, “accept the permission on screen”).
- Shows which backend is active and why the others are not.
- The **Display** panel shows, with an explanation for each control:
  - **Source → Media → Destination graph:** live status and main controls
    (monitor, capture, audio source, mode, bitrate, pipeline, sound
    destination).
  - **Collapsible sections** for the rest: status, Direct link,
    image/audio/capture details, RTSP negotiation, log.
  - **Live status:** P2P interface, PC/TV IPs, agreed mode, RTP, session,
    M3 announcement (that is not edited).
  - **Link settings:** Wi-Fi radio, P2P backend, GO intent, 2.4 GHz channel
    (wpa_supplicant only), scan wait, clear Direct, RTSP firewall.
  - **Image/audio/capture settings:** CEA mode, bitrate, where audio is
    heard, audio source, monitor, capture method.
  - **Negotiation/media settings:** RTSP port, local RTP port, pipeline,
    test pattern, UIBC.
  Mid-session they can be changed and **applied** (restarts the mirror). What
  FluxCast or Linux do not let you choose (HDCP, H.264 profile, VAAPI, LPCM,
  VBV size, IP that DHCP assigns to the TV) is shown as data, not as a fake
  control. A/V dropouts are usually a saturated radio; FluxCast’s Samsung VBV
  is 2× bitrate (~2 s) and is not exposed separately.

### RF-8 · Device memory

Full design in [MEMORIA_DISPOSITIVOS.md](MEMORIA_DISPOSITIVOS.md).

- The application **remembers** seen devices and which protocol worked with
  each one, in `~/.local/share/conexion_tv/devices.json`.
- The flow is **scan first, offer afterward**: after the scan, connection
  options are shown with their real state.
- Five states per protocol: `unknown`, `announced`, `working`, `failing`, and
  `unsupported`. `announced` lets you offer real options after a quick scan,
  without testing every protocol.
- **You can always try**, even what failed before, because causes are usually
  configuration. Only two cases are disabled: a verified hardware absence,
  and protocols with no way to use them from Linux.
- When a protocol is not in `working`, the application shows **what to
  configure on the TV and on the computer**; if it also failed, it adds
  diagnostic tips and the last error.
- A device’s identity is **never its IP**: UDN or MAC is used, with the rest
  of identifiers as aliases.
- Memory **does not degrade on its own**: a service stopping to announce does
  not lower its state, because many only announce in certain device modes.

### RF-7 · Firewall control from the application

Miracast needs port **7236/tcp** open, and `ufw` is active on the machine.
Opening it permanently leaves an unnecessary hole 99% of the time.

- Port opening is governed from the UI with a **visible switch**, which always
  shows whether it is open or closed.
- It opens only for the duration of the projection session and closes when it
  ends, even if the application crashes (guaranteed cleanup).
- Privilege elevation uses **polkit (`pkexec`)**, not by asking for the `sudo`
  password inside the application or storing it.
- If the user prefers to manage it by hand, the application detects that and
  only informs, without trying to change anything.

### RF-6 · Diagnostics

A check screen that verifies and reports:

- Wi-Fi adapter P2P support and backend in use (`wpa_supplicant` vs `iwd`)
- Required GStreamer binaries and plugins
- Port 7236/tcp open in the firewall
- VAAPI encoder availability
- TV visibility on the network
- Availability of each projection backend, with the reason for discarding

Each failed check indicates the exact command that fixes it.

## 4. Non-functional requirements

- **Projection latency:** under 500 ms with the Miracast backend. The DLNA
  backend cannot meet that (5–20 s) and must declare it in its
  `capabilities()` so the UI can warn.
- **No root privileges in normal use.** Install may ask for a password once
  for the `wpa_supplicant` D-Bus policy and system packages.
- **Failure recovery:** if the link drops, the application reports it and
  allows retry without restarting.
- **Activity log** to a file, with configurable level, to diagnose RTSP
  negotiation failures.
- **Config and tokens** under `~/.config/<app>/`, with the TV token in a
  file with restricted permissions.
- **Single source of truth for the device:** `INFO/tv_samsung.json`. No
  module hard-codes TV data.

## 5. Out of scope (first version)

- Non-Samsung TVs (but the architecture must not prevent it)
- Models before 2016 (encrypted v1 API and Orsay protocol)
- Receiving the TV screen on the computer
- Wayland support (to be considered later; current session is X11)
- Integration with SmartThings or any cloud service

## 6. Decisions taken

| # | Decision | Resolution |
|---|---|---|
| D-1 | TV model | **Samsung UE55TU7190UXZG**, TU7190 from 2020, Tizen 5.5. Taken from the *About This TV* photos. |
| D-2 | MAC for Wake-on-LAN | The TV’s own MACs, read from its screen and from the v2 API. Stored in the local `INFO/` sheet and in device memory, not in code. |
| D-4 | Projection engine | **Modular hybrid.** FluxCast wrapped behind `ScreenMirroring` for fast validation, replaceable later by a custom implementation. Additional backends planned: DLNA, Chromecast, AirPlay. |
| D-8 | Subsystem separation | Projection and TV control are independent subsystems that only share the device sheet. |
| D-9 | Main projection path | **Miracast/WFD**, with **DLNA as a real plan B** (this model still has it). Rationale in [PROTOCOLOS.md](PROTOCOLOS.md). |
| D-3 | GUI toolkit | **PyQt6**. |
| D-5 | FluxCast integration and license | **As an external process**, invoking its CLI. The process boundary keeps GPL-3.0 from reaching our code, so the project license stays free. The adapter translates its output into our state and error vocabulary. |
| D-6 | Privileges | `sudo` exists but **asks for a password**. The user installs system packages with the command we provide. Port 7236 is opened from the app with a visible switch via `pkexec` (see RF-7). |
| D-7 | TV availability | **Powered on and located** on the local network. |
| D-11 | Miracast settings in the GUI | **User-editable**, with explanations, before and during the session. Hot changes restart the mirror. |
| D-12 | Audio on PC and TV at once | **Done.** `RemoteDisplay` + `VirtualAudioBus`: virtual sink → TV; optional loopback to speakers (“both”). |
| D-13 | Latency / “ping” | **Bitrate in the GUI:** presets 4 / 8 / 14 Mb/s and exact value 2–16 Mb/s. More bitrate = more bits/frame (less perceived wait); less bitrate = less radio. 20 Mb/s does not connect. FluxCast does not expose GOP/VBV. Glass-to-glass not measured. |
| D-14 | Extended desktop | **User goal.** The TV as a second monitor, not only a mirror. Planned path: virtual monitor on X11/GNOME + capture only that and send it via Miracast. **Cap: 1080p60** (the WFD sink does not announce 4K/HEVC). 4K would only make sense over wired HDMI, outside this protocol. Not yet implemented. |

## 7. Pending decisions ❓

| # | Question | Status |
|---|---|---|
| D-10 | Is it worth trying Samsung Remote Access (RDP via `xrdp`) as an experiment? | ❓ pending, low priority (the user left the plan as is) |
