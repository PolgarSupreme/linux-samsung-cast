# Protocols available for Linux → Samsung UE55TU7190UXZG

> Research document. Last review: 2026-10-07 (revision 4).
> Device sheet: [`INFO/tv_samsung.json`](../INFO/tv_samsung.json)
> **Revision 4:** after cutting the verified session from the PC, retries fail
> at P2P (`peer-not-found`); the TV still announces WFD. See § 2.4.
> **Revision 3:** RTSP negotiation verified against the UE55TU7190UXZG.
> 720p30 AAC was a conservative choice of ours; the TV announces more.
> **Revision 2:** rewritten after identifying the exact model. Corrects two
> conclusions from revision 1 (see § 6).

## Executive summary

The TV is a **Samsung UE55TU7190UXZG**, Crystal UHD TU7190 series from 2020,
Tizen 5.5, KANT-SU2 chipset, firmware `T-KTSU2DEUC-2743.0`.

For this specific model:

- **Screen mirror with audio → Miracast/WFD.** Remains the only path that does
  real mirroring with sound and low latency.
- **Plan B for mirroring → DLNA/UPnP.** This model **still has DLNA**, unlike
  later Samsungs. It is not true mirroring and latency is high, but it works
  over the normal network without depending on Wi-Fi Direct.
- **TV control → Tizen WebSocket API v2** on port 8002, plus Wake-on-LAN.

These are independent protocol stacks that the application orchestrates
separately.

---

## 1. The device

Data read from the *About This TV* screen on the set itself:

| Field | Value |
|---|---|
| Model | **UE55TU7190UXZG** (55", region XZG / Germany) |
| Series | TU7190 — Crystal UHD Series 7, year **2020** |
| Platform | Tizen 5.5 on KANT-SU2 chipset |
| Firmware | `T-KTSU2DEUC-2743.0` |
| Wi-Fi MAC | read from *About This TV* (local sheet, not in code) |
| Ethernet MAC | read from *About This TV* (local sheet, not in code) |
| Wi-Fi | Wi-Fi 5 (802.11ac), 2.4 and 5 GHz |
| Ethernet | 100 Mbps |

### Why this model is good news

FluxCast, the most advanced Python Miracast implementation, uses as its main
test device a **Samsung UE55TU7092U**: same TU70xx series from 2020, same
chipset, same base firmware, only the regional suffix differs. In its tested
devices table it appears with **WFD and DLNA working**.

Best possible scenario: the main path and the fallback are verified by third
parties on hardware equivalent to ours.

---

## 2. Miracast / Wi-Fi Display — main path

Wi-Fi Alliance standard. Four layers that must all be crossed.

### Layer 1 — Wi-Fi Direct (P2P)

Point-to-point Wi-Fi link between computer and TV, **without going through the
router**. Negotiated with `wpa_supplicant` over D-Bus, or through NetworkManager
on the virtual `p2p-dev-*` interface.

- Requires the driver to support `P2P-client` and `P2P-GO` modes.
- Requires the **`wpa_supplicant`** backend; with `iwd` discovery silently
  returns zero devices.
- The TV supports 802.11ac, so the P2P group **can** run on 5 GHz. In practice
  NetworkManager often mounts the GO on **2.4 GHz channel 1 (20 MHz)** while
  the PC stays on the router at 5 GHz: the radio does MCC and bitrate toward
  the TV can fall to ~26 Mb/s (observed 2026-10-08 with 1080p60@14M →
  dropouts).
- The GUI can **prefer 5 GHz** (same channel as the AP, e.g. 44) or force
  36/40/44/48. That goes to `wpa_supplicant`, GO intent 15, and sets
  `OperRegClass=115` / `OperChannel` via D-Bus (FluxCast only forces 1/6/11).
  If the TV does not associate on 5 GHz, fall back to automatic or 2.4.
- With a single radio, the card time-shares between the normal network and the
  P2P link. Same band/channel as the router usually works better than 5 GHz +
  2.4 at once.

### Layer 2 — RTSP signalling (TCP 7236)

Over the P2P link an RTSP session opens where sender and receiver negotiate
WFD capabilities: resolutions and framerates, H.264 profile, audio format,
HDCP use, packet size. **This is where most attempts fail**, because each
vendor interprets the standard in its own way.

Port **7236/tcp** must be open in the local firewall.

### How to enable it on this TV (UE55TU7190, Spanish menu)

It is not listed as a source called “Screen Mirroring”. On Tizen 5.5 it lives
under **Remote Access** (*Acceso remoto*):

1. Remote **Source** button.
2. Enter **Remote Access** (*Acceso remoto*). There you see Knox / Secure,
   **Remote PC** (*PC remoto*), and **Screen Sharing** (*Uso compartido de
   pantalla*).
3. Choose **Screen Sharing**. The “compatible with Windows 10” text is only
   Samsung marketing: **the Linux PC will not appear in that list**. The TV
   waits and the computer is the one that finds it via Wi-Fi Direct.
4. On the computer press *Share screen*. If the TV asks for permission, accept
   it.

Observed P2P MAC (locally-administered bit relative to Wi-Fi):
`a8:bb:cc:dd:ee:01`. The 2026-10-07 RTSP session is detailed in § 2.1.

**Remote PC is not for mirroring:** it is RDP/VNC; the TV acts as a client and
connects to a PC. Knox/Secure is the container for that feature, not a
projection mode.

The same menu may offer to **add** more services. Inventory seen on this set
and what to do with each:

| Option | What it is | Useful for Linux → TV? |
|---|---|---|
| Screen Sharing | Miracast receiver | **Yes. This is the one to use.** |
| Remote PC | RDP/VNC client (Knox/Secure) | No: the TV controls a PC, it does not show the Linux desktop |
| Office 365 | Office in the TV browser | No: does not project the computer |
| Samsung DeX | Galaxy phone desktop on the TV | No: needs a Samsung phone, not a Linux PC |
| Add | Register a profile (Remote PC, DeX, etc.) | Not for mirroring; nothing needs to be added |

### Layer 3 — Media transport

MPEG-TS encapsulated in RTP over UDP:

- **Video:** H.264, profile per negotiation.
- **Audio:** AAC-LC 48 kHz stereo, or LPCM, **inside the same MPEG-TS**. That
  is why Miracast carries sound natively, unlike the other paths.

### Layer 4 — Capture and encoding on the machine

- **Video:** `x11grab` (our session is X11) or the
  `org.freedesktop.portal.ScreenCast` portal over PipeWire.
- **Audio:** PipeWire/PulseAudio `.monitor` source via `pactl`.
- **Encoding:** VAAPI hardware on the Intel iGPU (`/dev/dri/renderD128`), with
  software `x264` as fallback. The verified session used **software libx264**
  (`veryfast` + `zerolatency` + Constrained Baseline). VAAPI is available on
  the sender and has not yet been tested against this sink.

### Existing implementations

| Project | Language / license | Status 2026 |
|---|---|---|
| **FluxCast** | Python 3.10+, GPL-3.0 | Active. Full WFD stack. Tested on our same TV series. Closest reference to what we want. |
| `gnome-network-displays` | C / GStreamer | Works sometimes. **Does not package audio**: long-standing known limitation. Not in Ubuntu 22.04 repos. |
| `miraclecast` | C | Practically unmaintained. CLI only. |

### 2.1 Verified RTSP session (2026-10-07)

P2P link with NetworkManager: interface `p2p-wlp0s20-1`, subnet `10.42.0.0/24`.
The PC owned the group (`10.42.0.1`); the TV joined as client (`10.42.0.75`).
Port 7236 was opened on that interface, not on the LAN.

Wi-Fi Display handshake (messages M1–M7), all with `200 OK`:

| Step | Who | What |
|---|---|---|
| M1 OPTIONS | PC → TV | `Require: org.wfa.wfd1.0` |
| OPTIONS | TV → PC | The sink also asks for capabilities |
| M3 GET_PARAMETER | PC → TV | Only four fields (see § 2.2) |
| M4 SET_PARAMETER | PC → TV | Chosen mode + `HDCP none` + AAC |
| M5 TRIGGER SETUP | PC → TV | `wfd_trigger_method: SETUP` |
| SETUP | TV → PC | RTP/AVP/UDP, `client_port=19000-19001` |
| PLAY | TV → PC | Session `2022688` |

The TV **announced** this in M3 (`wfd_video_formats`):

```
40 00 01 10 000001e3 0f3fffff 00000fff 00 0000 00c8 01 none none
```

| Field | Value | Reading |
|---|---|---|
| native | `40` | Same identifier FluxCast uses for **1920×1080p60**. This set’s native WFD mode is Full HD at 60 fps, not 4K. |
| preferred-display-mode | `00` | Does not request a separate preferred display mode. |
| profile | `01` | Only **Constrained Baseline** (CBP). Does not announce Constrained High. |
| level | `10` | Bitmap whose highest bit is **H.264 Level 4.2** (fits 1080p60). |
| cea-support | `000001e3` | Bits 0, 1, 5, 6, 7, and 8 (CEA table below). |
| vesa-support | `0f3fffff` | Almost all PC modes up to 1680×1050; **not** 1920×1200. |
| hh-support | `00000fff` | Handheld modes (800×480, 854×480, 960×540, …). Irrelevant here. |
| latency | `00` | Sink declares 0×5 ms decode buffer. An announcement, not a measurement. |
| slice-enc-params | `00c8` | Up to 200 slices/frame. We send one slice. |
| frame-rate-control | `01` | Allows skipping frames. |
| codec extra | `none none` | Single H.264 codec. **No HEVC or WFD 2.0 / 4K.** |

Announced CEA table (`000001e3`):

| Bit | Mode | Announced? |
|---|---|---|
| 0 | 640×480p60 | yes |
| 1 | 720×480p60 | yes |
| 5 | 1280×720p30 | yes |
| 6 | 1280×720p60 | yes |
| 7 | 1920×1080p30 | yes |
| 8 | 1920×1080p60 | yes (native) |
| 3, 4, 10–16 | 50 Hz, 24/25 fps, interlaced | **no** |

The panel is European (50 Hz), but the Miracast sink speaks CEA in 60 Hz.
There is no 720p50 or 1080p50 in the bitmap.

Announced audio:

```
LPCM 00000003 00, AAC 00000001 00
```

- LPCM: 44.1 kHz and 48 kHz, 2 channels, 16 bit.
- AAC: 48 kHz stereo (bit 0). No 5.1.

HDCP: the TV announced `HDCP2.1 port=9999`. In M4 we sent
`wfd_content_protection: none` and **it accepted**. There is no HDCP sender on
Linux; it must not be enabled.

What **we chose** in M4:

```
28 00 01 01 00000020 00000000 00000000 00 0000 0000 00 none none
```

1280×720p30, CBP, Level 3.1, AAC-LC 128 kb/s, 4 Mb/s video. Not because the
TV could not do more: the CLI and GUI button carried
`--output-res 1280x720 --fps 30 --bitrate 4M`. With those figures FluxCast sets
`wants_720` and stays at 720p30 even if the sink has 1080p60.

Media chain for that session:

- `x11grab` capture of `:1+0,0`
- audio `alsa_output.pci-0000_01_00.1.hdmi-stereo.monitor` (HDMI monitor).
  **Perceived** on 2026-10-07: heard on the computer and on the TV.
- `libx264` `veryfast` `zerolatency` `baseline` `level 3.1`, GOP = fps (1 s),
  no B-frames, VBV = 2× bitrate (8 Mb for Samsung)
- MPEG-TS → RTP/UDP `10.42.0.75:19000` from local port 19002
- RTSP M16 keepalive every 25 s; the TV replies `200 OK` with the same session

### 2.2 What the protocol allows and we have not yet requested

FluxCast’s M3 only asks four parameters: content protection, video formats,
audio codecs, and RTP ports. The standard allows more, and this TV may be
offering them without our having read them.

| Possibility | Status | Notes |
|---|---|---|
| 1920×1080p60 | Announced, **native**, **verified** 2026-10-07 | M4 `40 00 01 10 00000100…`, PLAY, RTP to `10.42.0.75:19000`, **14 Mb/s**. Interface `p2p-wlp0s20-3`. |
| Bitrate 20 Mb/s | **Does not connect** (2026-10-07, GUI) | The bitrate spin no longer reaches 20 000 kb/s (cap 16 Mb/s). Verified ceilings: 4 Mb/s (720p30) and 14 Mb/s (1080p60). |
| 1920×1080p30 | Announced, untested | Plan B if 60 fps saturates the radio or encoder. |
| 1280×720p60 | Announced, untested | Useful if fluidity is preferred over sharpness. |
| 640×480p60 | Announced, not interesting | Last resort only if 720p fails. |
| VESA modes (up to 1680×1050) | Announced, FluxCast does not pick them | Current selector only contemplates VESA 1920×1200, which this TV **does not** announce. |
| Constrained High / High | TV **does not** announce it | Sending High would be a risk: profile bitmap is only `01`. |
| HEVC / 4K | Not present in M3 | Miracast 1.0. Panel is 3840×2160; WFD sink is not. The PC GPU does not change this: the TV does not ask for it in negotiation. Extended desktop over Wi-Fi = at most 1080p60. |
| AAC 48 kHz stereo | **Perceived verified** (PC and TV at once) | FluxCast captures a Pulse `.monitor`. “TV only” cannot be `set-sink-mute` (monitor goes to 0): a null sink is used and its monitor is captured. |
| LPCM 48 kHz | Announced, untested | Less encode load; more bitrate. FluxCast reserves LPCM for the Microsoft adapter (PES `0x83`). Trying it here is an experiment, not the default path. |
| HDCP 2.1 | Announced and **rejectable** | Already checked: `none` is accepted. |
| UIBC (remote/mouse back, TCP 7239) | **Not asked** | FluxCast has it opt-in. An M3 with `wfd_uibc_capability` would say whether the TU7190 can send HID toward the PC. |
| `wfd_idr_request` | Planned in the handler | The sink can request a keyframe; satisfied with the next IDR (~1 s). |
| `wfd_standby_resume`, EDID, I2C, 3D | Not asked | 3D does not apply. EDID could refine the native mode. |
| VAAPI encoder | Available on the PC, unused | Replacing `libx264` with `h264_vaapi` should lower CPU and sometimes encode latency. Need to see whether the bitstream (AUD, repeated headers, baseline) still suits the TV. |
| GStreamer pipeline (`gst-x11`) | Unused | Plan B if ffmpeg gives a black screen on another sink. Here ffmpeg already painted. |

The **Display** tab lets you choose the mode (720p30 by default; native
1080p60 already verified on 2026-10-07). Changes apply on (re)connect.

### 2.3 Latency: three different clocks

The log numbers are **not** glass-to-glass latency. They measure the sender
path.

| Clock | Observed value | What it is |
|---|---|---|
| First RTP after PLAY | **700.6 ms** | From the TV saying PLAY until bytes leave `p2p-wlp0s20-1`. Includes starting ffmpeg and the `x11grab` probe (*not enough frames to estimate rate*). |
| Sender-path (RTSP connect → first RTP) | **7224 ms** | M1–M7 handshake (~6.5 s) plus those 700 ms. Time until the mirror *starts*, not per-frame delay. |
| Steady-state glass-to-glass | **unmeasured** (estimate 150–500 ms) | Capture + encode + RTP + TV buffer + decode. |

Where steady delay comes from, piece by piece:

1. **Capture** `x11grab` at 30 fps: ~1 frame (33 ms). At 60 fps it would drop
   to ~16 ms.
2. **Encode** `zerolatency`, no B-frames, `veryfast`: 1–3 frames. The 1 s GOP
   does not add a second of wait: with `tune=zerolatency` each frame leaves
   immediately; the GOP only marks how often an IDR goes.
3. **Samsung VBV = 2× bitrate.** In this session, `bufsize=8M` with `4M`.
   Affects rate control more than a fixed delay, but it is a lever: a smaller
   buffer (LG-style, 0.5×) can cut queue at the cost of artifacts.
4. **AAC.** ~20–50 ms typical lookahead at 48 kHz. LPCM would remove it.
5. **Wi-Fi Direct** on the same radio as the LAN (Intel AX211). Variable
   jitter; with a static desktop observed throughput is around 2–3 Mb/s,
   below the 4 Mb/s ceiling.
6. **TV buffer.** It did not announce it (`latency=00`) and we have not
   measured it. On Samsung it is usually the largest chunk (100–300 ms).

To measure glass-to-glass for real you need a stopwatch on the PC filmed by a
phone that sees the monitor and the TV at once. Until then the catalogue keeps
150–500 ms as a *steady-state estimate*, not as verified data.

Levers, cheapest first:

1. **Bitrate (`--bitrate`) in the GUI.** Presets 4 / 8 / 14 Mb/s and exact
   kb/s between 2 and 16 Mb/s. More bits per frame = the encoder compresses
   less and motion usually looks fresher; less bitrate eases the radio.
   FluxCast sets Samsung VBV = 2× bitrate, so the buffer *in seconds* does not
   shrink when Mb/s rise. **Do not ask for 20 Mb/s:** it never connected.
   15–16 Mb/s are in the spin and not yet verified.
2. 720p60 (more fluidity, same frame size).
3. Shorter GOP (e.g. 15) if the TV asks for many IDRs when moving windows.
   FluxCast has no flag: GOP = fps.
4. Cut VBV (experiment; Samsung asked for 2× in FluxCast due to underflow).
   No CLI flag either.
5. Try VAAPI (less encode queue).
6. Try LPCM (removes AAC lookahead).

### 2.4 Reconnection: the TV announces and does not join the group

The § 2.1 session was cut **from the PC while PLAY was still active**.
FluxCast only does RTSP TEARDOWN and brings down the P2P group if it receives
SIGINT (`KeyboardInterrupt`). SIGTERM or killing the process leaves port 7236
and the group half-open, and the TV may believe the session is still alive.

Retries observed the same day (same 720p30 flags, same P2P MAC
`A8:BB:CC:DD:EE:01`):

1. The WFD scan **still sees** the sink. That only proves it announces the WFD
   IE, not that it is waiting in *Screen Sharing*.
2. NetworkManager activates a new GO (`p2p-wlp0s20-5` … `-12`). The PC is
   `10.42.0.1`; **no client appears**.
3. At ~5 s: `Peer requested in connection is missing for too long` →
   `reason 'peer-not-found'`.
4. FluxCast: `selected TV IP not found for MAC A8:BB:CC:DD:EE:01`. No M1.
   The failure is layer 1 (P2P), not RTSP negotiation.

Powering off the TV cleans its side; it does not clean `FluxCast WFD` profiles
or the `p2p-dev-*` device on the PC. Always close with SIGINT + bring down the
P2P link. If the WFD announcement returns and the group stays empty, the next
lever is restarting the computer’s Wi-Fi **with the TV already in Screen
Sharing**. That was verified on 2026-10-07: after powering off the TV, entering
Screen Sharing, and cycling the PC Wi-Fi, PLAY returned at 720p30
(`p2p-wlp0s20-1`, TV `10.42.0.75`). The first attempt right after the cycle
timed out in `config`; the second, with P2P settled, negotiated M1–PLAY.

---

## 3. DLNA / UPnP — real plan B for this model

This TV **retains DLNA**, confirmed by its technical sheet and by FluxCast
tests on the equivalent series.

- **How it works:** the computer serves the captured screen as an HTTP stream
  and uses UPnP `AVTransport` (`SetAVTransportURI` + `Play`) to tell the TV to
  open it. The TV’s native player does the rest.
- **Goes over the router network**, not Wi-Fi Direct. Does not depend on the
  adapter supporting P2P, and does not compete for the radio.
- **Audio is included** in the container.
- **Latency of 5 to 20 seconds** due to player buffering. Unusable for
  interacting with the computer; acceptable for watching a video.
- On this series **HLS transport** is preferable to progressive MPEG-TS, which
  freezes or stutters on several Samsung models.

**Where it fits:** as a second projection backend, and as the basis for a
“send this video to the TV” feature that is useful on its own.

---

## 4. TV control — Tizen WebSocket API v2

Tizen 5.5 uses the unencrypted v2 API. v1 encryption only affects J and K
models from 2015–2016, so **it does not affect us**.

- **Device information (REST):** `GET http://<IP>:8001/api/v2/`
  Returns model, name, firmware, MAC, and capabilities. Also confirms that a
  found IP is really this TV.
- **Control channel (secure WebSocket):**
  `wss://<IP>:8002/api/v2/channels/samsung.remote.control?name=<name_in_base64>`
  - Self-signed certificate: TLS verification must be disabled.
  - The **first connection shows a permission dialog on the TV**. On accept,
    the TV returns a *token* that must be persisted to disk; otherwise it will
    ask every time.
  - Allows sending keys (`KEY_VOLUP`, `KEY_HOME`, `KEY_HDMI`, …), launching
    applications, changing input, and querying state.
- **Library:** `samsungtvws` 3.0.6, with sync and async support.
- **DIAL** on port 8001 allows launching applications by ID.

### Power-on

The WebSocket only answers with the TV powered on. To power it on, send a
**Wake-on-LAN** magic packet to the TV’s Wi-Fi MAC or, if wired, to the
Ethernet MAC. Both are read from the local sheet.

Requires enabling on the TV: *Settings → General → Network → Expert →
Power On with Mobile* (*Encender con móvil*).

---

## 5. Alternatives considered and discarded

| Path | Verdict for this model | Reason |
|---|---|---|
| **Google Cast** | Impossible | Samsung Tizen sets do not have built-in Chromecast. Hardware absence; the TV will never appear. |
| **AirPlay 2** | Supported by the TV, unusable from Linux | The TU7190 is an AirPlay 2 receiver, but no working AirPlay sender exists for Linux. `uxplay` does the opposite: turns Linux into a receiver. Candidate for a future backend if a sender appears. |
| **Samsung Remote Access** (*Source → Remote Access → Remote PC*) | Cheap experiment, not the main path | The TV acts as an **RDP or VNC client** and connects to the computer. Samsung documents only Windows (RDP) and macOS (VNC), and explicitly states Linux is unsupported. But both are standard protocols and Linux serves them with `xrdp` or `x11vnc`. Two deeper objections: it is not mirroring but a **remote session** (a different desktop, not the one in front of you), and the connection goes in the **reverse direction**, started by the TV, which fits poorly with a desktop app. Audio over RDP depends on Samsung’s embedded client negotiating the `rdpsnd` channel, which is unverified. |
| **Samsung Smart View / Screen Sharing** | Impossible | Proprietary Windows and macOS client. On 2018–2020 models the “Screen Sharing” under *Remote Access* is Miracast underneath, so it adds nothing new. |
| **SmartThings** | Out of scope | Requires a Samsung account and goes through the cloud. Contradicts the goal of direct local connection. |

---

## 6. Corrections relative to revision 1

Two earlier conclusions were wrong for this model, and it is worth recording
them because they affect the architecture:

1. **DLNA is not discarded.** Revision 1 assumed Samsung had removed DLNA from
   Tizen. True on recent models, but **not on the 2020 TU series**: this TV
   still has it. DLNA moves from “discarded” to “second backend with its own
   purpose”.
2. **Samsung Remote Access deserved a mention.** Revision 1 did not evaluate
   it. It is not the solution, but it is a real Samsung protocol and a
   low-cost experiment.

---

## 7. Sender hardware and software

Verified on 2026-10-07.

| Element | Value | Implication |
|---|---|---|
| OS | Ubuntu 22.04.5 LTS (jammy) | GStreamer 1.20, somewhat old packages |
| Session | **X11** + GNOME 42 | `x11grab` is the most direct capture path |
| Python | 3.10.12 | Compatible with `fluxcast` and `samsungtvws` |
| Wi-Fi | Intel AX211 (`8086:7af0`), `iwlwifi` driver | AX2xx family with P2P confirmed by third parties |
| P2P interface | **`p2p-dev-wlp0s20f3` present** | Wi-Fi Direct available |
| Wi-Fi backend | **`wpa_supplicant` active, `iwd` inactive** | Correct for Miracast |
| Network | IPv4 on the same subnet as the TV | The router does not participate in Miracast (goes over Wi-Fi Direct) |
| Audio | PipeWire + PulseAudio | Capture via `.monitor` source |
| GPU | Intel iGPU, `/dev/dri/renderD128` | H.264 encoding via VAAPI |
| GStreamer | base, good, ugly, bad, libav, vaapi, pipewire | Enough to capture and mux |
| Portal | `xdg-desktop-portal-gnome` 42 | ScreenCast available as an alternative |

### System packages

Installed on 2026-10-07: `ffmpeg`, `iw`, `gstreamer1.0-plugins-bad`, `vainfo`,
`python3.10-venv`. Machine diagnostics (`python3 -m conexion_tv diagnostico`)
pass fully.

`gnome-network-displays` and `miraclecast` **are not in Ubuntu 22.04 repos**
and we do not need them: FluxCast covers that path.

### TV status on the network

A first subnet scan with the TV off found no open Samsung ports. After powering
it on, the same scan located it by Wi-Fi MAC and confirmed ports 8001, 8002,
and 9197.

Port **7236 remains closed on the LAN**: the TV only opens it on the Wi-Fi
Direct interface when *Screen Mirroring* is active.
