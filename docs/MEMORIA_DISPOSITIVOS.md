# Device memory

> Last review: 2026-10-07.
> Implementation: `conexion_tv/core/device_memory.py` and
> `conexion_tv/core/protocols.py`.

## The problem it solves

Without memory, the application starts from scratch every time: it probes
everything again, does not know what worked yesterday, and offers the user
options already known to fail. Worse: it cannot distinguish *“I have never
tried this”* from *“I tried this and it does not work”*, which are very
different situations for the user.

## Two separate pieces

### 1. Device memory — what was learned, persistent

Catalogue of seen devices, with the real result of each protocol against each
one. Stored in `~/.local/share/conexion_tv/devices.json` and **grows with
use**.

It is a record of facts: what was tried, when, with what result, and with what
evidence. It contains neither tips nor opinions.

### 2. Protocol knowledge base — what is known, static

Ships with the application. For each protocol it describes what it provides,
what the device needs, what the computer needs, and what to check when it
fails.

It is the source of the tips the user sees.

**Why separate them:** memory is specific to each set and obtained by
observation; knowledge is general and obtained by documenting. Mixing them
would force rewriting tips in every entry of every device.

## Protocol states

Five states, because four are not enough to distinguish the cases that matter:

| State | Meaning | What the UI does |
|---|---|---|
| `unknown` | Never observed or attempted | Offers trying it, with prerequisites up front |
| `announced` | The device announces it (SSDP, REST, UPnP descriptor) but it has not been tested | Offers it as available, warning it is unverified |
| `working` | Tested successfully, with date and evidence | Offers it as the preferred option |
| `failing` | Tested and failed, with the reason stored | Offers it anyway, but showing the last error and tips |
| `unsupported` | Determined absent on the device | Shows it disabled and explains why |

`announced` is the state that saves the most work: it lets you show real
options after a quick scan, without starting a trial session for every
protocol.

## Principle: never block the attempt

Even if a protocol is in `failing`, **the application always allows trying
it**. Failure causes are usually transient or configuration-related: the TV
was not in *Screen Mirroring* mode, the port was closed, *Power On with
Mobile* was off. Marking something permanently impossible from one failure is
almost always a mistake.

The only exception is `unsupported`, reserved for verified hardware absences:
this TV has no Chromecast, and no configuration will change that.

## Stable device identity

A DHCP IP is not usable as identity, and a device has several MACs (wired and
Wi-Fi, and sometimes one per service). The key is chosen by preference order:

1. `udn:<uuid>` — the UDN announced via UPnP, if it has one
2. `mac:<mac>` — MAC normalized to lowercase

Each entry also stores **all** known identifiers (all MACs, all UUIDs) as
aliases, so the set can be recognized by any of them. The IP is stored, but
only as the last seen value: never as identity.

## Usage flow

```
1. Quick network scan
       ↓
2. Each found device is looked up in memory by its aliases
       ↓
3. What the device announces now is merged with what is remembered
   · a protocol remembered as 'working' stays 'working'
   · a new one that announces enters as 'announced'
   · a remembered one that no longer announces is not degraded: the
     service may only appear when the set is in a certain mode
       ↓
4. The UI shows the options with their state and tips
       ↓
5. On a connection attempt, the result is written to memory
```

Step 3 has a deliberate rule: **memory does not degrade on its own**. Many TV
services only announce in certain modes; Miracast port 7236, for example, only
listens when *Screen Mirroring* is active. If absence of an announcement
degraded the state, memory would erase itself every time the set is idle.

## File schema

Persisted field names in `devices.json` match the current implementation
(`dispositivos`, `estado`, …). Protocol state **values** stored on disk are
still the Spanish tokens (`desconocido`, `anunciado`, `funciona`, `falla`,
`no_soportado`); in this documentation they are referred to by their English
names (`unknown`, `announced`, `working`, `failing`, `unsupported`).

```json
{
  "schema_version": 1,
  "actualizado": "2026-10-07T17:45:00",
  "dispositivos": {
    "udn:00000000-0000-4000-8000-000000000001": {
      "clave": "udn:00000000-0000-4000-8000-000000000001",
      "nombre": "[TV] Salon",
      "fabricante": "Samsung",
      "modelo": "UE55TU7190UXZG",
      "modelo_interno": "20_KANTSU2_UHD_BASIC",
      "plataforma": "Tizen",
      "anio": 2020,
      "alias": ["mac:aa:bb:cc:dd:ee:01", "mac:aa:bb:cc:dd:ee:02"],
      "ultima_ip": "192.168.1.50",
      "visto_primera_vez": "2026-10-07T17:20:00",
      "visto_ultima_vez": "2026-10-07T17:24:00",
      "protocolos": {
        "tizen_websocket": {
          "estado": "funciona",
          "comprobado_el": "2026-10-07T17:24:00",
          "evidencia": "Token issued and KEY_VOLUP accepted",
          "intentos": 1,
          "exitos": 1,
          "ultimo_error": null,
          "limitaciones": ["app_list() does not respond on this model"],
          "datos": { "puerto": 8002, "token_guardado": true }
        }
      }
    }
  }
}
```

## What it remembers about each protocol

| Field | Purpose |
|---|---|
| `estado` | One of the five above (`funciona` = working, etc.) |
| `comprobado_el` | Allows warning about stale information |
| `evidencia` | What was observed exactly. Forces honesty: if there is no evidence, the state is not `working` |
| `intentos` / `exitos` | Reliability. Something that works 1 of 5 times is not the same as something that always works |
| `ultimo_error` | What to show the user alongside the tips |
| `limitaciones` | What works only partially, such as `app_list()` on this TV |
| `datos` | What was learned for the next connection: ports, control URL, whether there is a token |

The `evidencia` field is not decorative. It is the safeguard against marking
something as working because “it seemed to”: if you cannot write what was
observed, the state must not be `working`.

## Relationship with `INFO/tv_samsung.json`

They are complementary and their roles should not be confused:

- **`INFO/tv_samsung.json`** is the hand-curated sheet for *this* TV, made from
  photos and our probing. It is documentation, readable and reviewable, and
  serves as the **seed** for memory on first launch.
- **`devices.json`** is the application’s runtime catalogue. The program
  maintains it, covers several devices, and is the authority while the
  application runs.

The seed is applied once. After that, memory is in charge.
