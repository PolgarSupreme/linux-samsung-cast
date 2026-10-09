# Project context

Python application with a graphical interface to connect a Linux computer to a
Samsung TV over Wi-Fi: screen mirroring with audio and remote control of the
TV.

The app uses only the **local network** (LAN and Wi-Fi Direct). It never
contacts the public Internet or cloud services.

## Reference documentation

**Always** read before working, in this order:

1. [`docs/ESTADO_ACTUAL.md`](docs/ESTADO_ACTUAL.md) — where the project stands,
   what blocks progress, and what the next step is.
2. [`docs/REQUISITOS.md`](docs/REQUISITOS.md) — what to build and which
   decisions remain open.
3. [`docs/PLAN_DESARROLLO.md`](docs/PLAN_DESARROLLO.md) — architecture and
   phases.
4. [`docs/PROTOCOLOS.md`](docs/PROTOCOLOS.md) — technical research, discarded
   paths, and hardware audit.
5. [`docs/MEMORIA_DISPOSITIVOS.md`](docs/MEMORIA_DISPOSITIVOS.md) — how the app
   remembers what works with each device.
6. [`INFO/tv_samsung.json`](INFO/tv_samsung.json) — TV device sheet.

## The device

Samsung **UE55TU7190UXZG**, Crystal UHD TU7190 from 2020, Tizen 5.5.

`INFO/tv_samsung.json` is the hand-curated sheet for the TV, and the **seed**
for device memory. No module hard-codes its IP, MAC, model, or capabilities.

At runtime the authority is **device memory**
(`~/.local/share/conexion_tv/devices.json`), which the program maintains and
which can cover several sets.

Configuration tips do not go in memory: they live in the protocol catalogue
(`conexion_tv/core/protocols.py`), because they are general knowledge, not
observations about a specific set.

## Maintenance rules

- Update `docs/ESTADO_ACTUAL.md` at the end of each work session, including an
  entry in the session log.
- Move a user decision into `docs/REQUISITOS.md` as soon as it is taken, and
  remove it from the pending table.
- Record in `docs/PROTOCOLOS.md` any new finding about protocols or hardware,
  especially negotiation failures observed against the TV.
- When a capability is verified against the real set, set the corresponding
  `verificado_en_dispositivo` field to `true` in `INFO/tv_samsung.json`.
- Do not treat any TV capability as confirmed without verifying it against the
  real set. Verified and assumed facts are distinguished explicitly.

## Architecture rules

- Projection (`ScreenMirroring`) and TV control (`TVController`) are
  **independent** subsystems. They only share the device sheet.
- The FluxCast dependency (GPL-3.0) lives **only** in
  `mirror/backends/fluxcast/`. Importing it from any other module breaks the
  license isolation, and a test enforces that.
- States, metrics, and errors that cross into the core use the application
  vocabulary, never the backend’s.

## Language

Documentation, UI messages, and user communication in **English**. Code
identifiers in English.
