# Current status

> **This is the first file to read when resuming the project.**
> Last update: 2026-10-08 21:54
> Active phase: **Phase 2** — mirror + remote display (virtual audio).
> Next work: try P2P on 5 GHz (same channel as the router); D-14.

## In one sentence

The UE55TU7190UXZG accepts Miracast from Linux at **720p30 and 1080p60**, with
**image and audio**. In Sound you choose whether it plays on the TV, the PC, or
both. The **Screen** tab lets you edit the Direct link and the negotiation.

## What already works

- **Tizen WebSocket control**, verified: paired, token persisted, volume keys
  executed.
- **DLNA and DIAL announced** (SSDP + MediaRenderer DMR-1.50).
- **Network discovery** and device memory.
- **Sender diagnostics** all green (ffmpeg, VAAPI, P2P, X11, pkexec…).
- **PyQt6 interface** with remote and Share screen button. FluxCast runs as an
  external process in `.venv-fluxcast`.
- **Miracast/WFD verified against the set** on 2026-10-07: P2P at 720p30 and
  native **1080p60**, RTSP M1–PLAY, H.264 baseline, **AAC heard** on computer
  and TV (HDMI monitor source). Detail in
  [PROTOCOLOS.md § 2.1](PROTOCOLOS.md#21-verified-rtsp-session-2026-10-07)
  and § 2.2.

## What is missing

1. **Extended desktop (D-14):** the TV as a second monitor, not only a mirror.
   Requires a virtual monitor + capture of that output. Over Miracast the cap
   remains **1080p60**, not 4K (the WFD sink does not announce it).
2. **More latency levers** (GOP, VBV, 720p60). Bitrate is already chosen under
   Image (2–16 Mb/s). Glass-to-glass not measured.
3. Try 1080p30 and 720p60.
4. Open/close cycle for port 7236 against ufw from the GUI.
5. UIBC and VAAPI remain experiments.

## Repository privacy

`INFO/` (real sheet, photos, serial number, MAC) is **not published**. The
repository ships an anonymized example in `tests/datos/tv_ejemplo.json`. The
local sheet still serves as the seed on the development machine.

The first GitHub commit still contains those files in history. Purging them
requires rewriting history (`git filter-repo` + force push), which is not done
without an explicit request.

## Concrete next step

Design extended mode (virtual monitor + Miracast 1080p60), or continue with
latency. The user wants the TV as an extended display; 4K over Wi-Fi Display is
not viable on this set.

## Session log

### 2026-10-08 — Session 7f

User-facing UI, errors, protocol catalog, CLI, and FluxCast log phrases
translated from Spanish to English. `Purpose` values → `projection` /
`power` / `app_launch`; `ProtocolState` → `unknown`/`announced`/`working`/
`failing`/`unsupported` with legacy Spanish values still accepted on load.
`pytest`: 61 passed. Not committed.

### 2026-10-08 — Session 7e

Dropouts with 1080p60@14M: P2P on **2.4 GHz ch1 ~26 Mb/s** and many retries
(MCC with the STA on 5 GHz). GUI: prefer/force 5 GHz channel (wpas + GO 15 +
OperChannel via D-Bus). Pending verification against the TV.

### 2026-10-08 — Session 7d

GUI: Source/Media/Destination graph with status and controls; collapsible
config sections. A/V dropouts: FluxCast does not expose buffer; Samsung VBV =
2× bitrate (~2 s). Lower bitrate/mode if the radio saturates.

### 2026-10-08 — Session 7c

`RemoteDisplay` + `VirtualAudioBus` model: apps → null sink → Miracast;
“both” adds loopback to speakers. HDMI mute discarded. tv↔both hot-switch
without renegotiating RTSP.

### 2026-10-08 — Session 7b

“TV only” failed with `set-sink-mute` (monitor at RMS 0).

### 2026-10-08 — Session 7

New goal: extended desktop (D-14). Clarification: 4K panel, Miracast sink max
1080p60 verified; the GPU does not unlock 4K over WFD.

### 2026-10-07 — Session 6l

Sound: combo “where it plays” (TV only / both / PC only). TV only mutes the
Pulse `.monitor` sink and restores it when the mirror stops. Mid-session,
switching between TV and both applies mute without renegotiating.

### 2026-10-07 — Session 6k

Bitrate as the wait lever: presets (4 / 8 / 14 Mb/s) plus exact kb/s, cap
16 Mb/s because 20 did not connect. CEA mode no longer overwrites a custom
bitrate. Next: local audio mute.

### 2026-10-07 — Session 6j

Working version: 720p30/1080p60, AAC on PC and TV, GUI with P2P retry and two
fields per row. Finding: **20 000 kb/s does not create the connection**. Next:
local audio mute; then latency levers without going to 20 Mb/s.

### 2026-10-07 — Session 6i

Display tab: two fields per row (title + control + hint in each column).

### 2026-10-07 — Session 6h

Perceived audio verified: at 1080p60 sound is heard on the PC and on the TV
(AAC from the HDMI monitor). INFO/tv_samsung.json and PROTOCOLOS.md.

### 2026-10-07 — Session 6g

The GUI failed like the *first* CLI (`peer-not-found`); the manual CLI
retried after ~8 s and then got PLAY. Cause: extra WFD scan + orphan pause +
a single attempt. The adapter already uses the P2P MAC from memory (no prior
scan) and retries once on an empty GO.

### 2026-10-07 — Session 6f

The Display panel covers the verified sequence: live status (interface, IPs,
M3/M4, RTP), GO intent, P2P backend, RTSP/RTP ports, pipeline, radio, scan
timeout, and a button to clear Direct. HDCP, VAAPI, and LPCM remain
read-only data. Prefs expanded.

### 2026-10-07 — Session 6e

720p30 closed with SIGINT/TEARDOWN. First 1080p60 retry: GO with no client.
Second, after ~8 s: M1–PLAY **1920×1080p60**, CBP Level 4.2, AAC, 14 Mb/s,
TV `10.42.0.75` on `p2p-wlp0s20-3`.

### 2026-10-07 — Session 6d

Reconnection verified: TV in Screen Sharing, PC Wi-Fi cycled, WebSocket remote
not used. First attempt timed out in NM `config`; the second did M1–PLAY
720p30 to `10.42.0.75` on `p2p-wlp0s20-1`. PROTOCOLOS.md § 2.4.

### 2026-10-07 — Session 6c

720p30 retries after a bad cut of the good session: the TV announces (WFD + REST
on) and NetworkManager opens the GO, but the client never joins
(`peer-not-found`, no P2P IP, no M1). Closed with SIGINT. Hypothesis: ghost
session on the sink and/or dirty PC P2P stack; a WFD announcement is not the
same as being in Screen Sharing. Detail in PROTOCOLOS.md § 2.4.

### 2026-10-07 — Session 6b

The GUI attempt failed: the 720p30 CLI session was still alive and held port
7236 (`Address already in use`). Also the panel scroll had left settings at
640×480 / 20 Mb/s. Old session closed, prefs restored to 720p30, mouse wheel
no longer changes combos, and success is not declared until PLAY or an error
in clear language.

### 2026-10-07 — Session 6

Projection panel rebuilt: session status, negotiation log in clear language,
and editable controls (CEA mode, bitrate, audio and source, monitor, capture,
firewall 7236, experimental UIBC) each with an explanation. Hot changes
restart the mirror. HDCP, H.264 profile, and VAAPI are shown as data, not as
invented controls. Settings persisted in
`~/.config/conexion_tv/proyeccion.json`.

### 2026-10-07 — Session 5

Real Miracast connection. The “compatible with Windows 10” text does not list
the PC: the computer finds the TV via Wi-Fi Direct (`a8:bb:cc:dd:ee:01`).
Negotiation documented: the sink offers 1080p60 CBP Level 4.2, AAC and LPCM,
and accepts HDCP `none`. We sent 720p30 because the CLI/GUI requested it.
Sender latencies measured; glass-to-glass pending. Updated `PROTOCOLOS.md`,
`INFO/tv_samsung.json` (`miracast_wfd.verificado_en_dispositivo = true`) and the
tips catalogue.

### 2026-10-07 — Session 4

System packages installed; diagnostics pass fully. Discovery, `TVController`,
`ScreenMirroring` contract, CLI, and the GPL isolation test implemented.
28 tests green. Live scan finds the TV. `INFO/` leaves the published tree.

### 2026-10-07 — Session 3

TV found and queried. WebSocket control working for real. DLNA verified.
Decisions on toolkit, FluxCast as a process, and firewall via `pkexec`.

### 2026-10-07 — Session 2

TV photos, `INFO/tv_samsung.json`, DLNA correction, modular backend
architecture.

### 2026-10-07 — Session 1

Sender audit and protocol research. Chromecast and AirPlay discarded; hardware
supports Miracast.
