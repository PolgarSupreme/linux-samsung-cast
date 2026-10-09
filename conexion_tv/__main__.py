"""Command-line entry point, before the graphical UI."""

from __future__ import annotations

import argparse
import sys

from conexion_tv.core.device_memory import DeviceMemory, ProtocolState
from conexion_tv.core.seed import sembrar
from conexion_tv.diagnostics import comprobar_sistema
from conexion_tv.discovery import escanear


_ICONO = {
    ProtocolState.WORKING: "OK",
    ProtocolState.ANNOUNCED: "announced",
    ProtocolState.FAILING: "failing",
    ProtocolState.UNKNOWN: "?",
    ProtocolState.UNSUPPORTED: "no",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="conexion-tv",
        description=(
            "Project and control Samsung TVs from Linux. "
            "Uses only the local network (LAN / Wi-Fi Direct); never the public Internet."
        ),
    )
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("gui", help="Open the graphical UI (default)")
    sub.add_parser("doctor", help="Check the sender machine")
    sub.add_parser("scan", help="Search for TVs on the local network")
    sub.add_parser("memory", help="Show remembered devices")
    # Legacy Spanish aliases (same handlers).
    sub.add_parser("diagnostico", help=argparse.SUPPRESS)
    sub.add_parser("escanear", help=argparse.SUPPRESS)
    sub.add_parser("memoria", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.comando in (None, "gui"):
        from conexion_tv.gui.app import run_app

        return run_app()
    if args.comando in ("doctor", "diagnostico"):
        return _doctor()
    if args.comando in ("scan", "escanear"):
        return _scan()
    if args.comando in ("memory", "memoria"):
        return _memory()
    return 1


def _doctor() -> int:
    fallos = 0
    for c in comprobar_sistema():
        marca = "OK" if c.ok else "FAIL"
        print(f"[{marca}] {c.titulo}: {c.detalle}")
        if not c.ok:
            fallos += 1
            if c.arreglo:
                print(f"       → {c.arreglo}")
    return 1 if fallos else 0


def _scan() -> int:
    memoria = DeviceMemory()
    sembrar(memoria)
    registros = escanear(memoria)
    if not registros:
        print("No TV found.")
        print("Power it on and check it is on the same Wi-Fi network.")
        return 1
    for r in registros:
        print(f"{r.nombre or '(unnamed)'}  {r.modelo}  {r.ultima_ip}")
        for o in r.opciones():
            extra = "" if o.se_puede_intentar else f"  [{o.motivo_no_disponible}]"
            print(f"  {_ICONO[o.estado]:<10} {o.info.nombre}{extra}")
    return 0


def _memory() -> int:
    memoria = DeviceMemory()
    sembrar(memoria)
    todos = memoria.todos()
    if not todos:
        print("Memory is empty. Run: python3 -m conexion_tv scan")
        return 0
    for r in todos:
        print(f"{r.nombre or '(unnamed)'}  {r.modelo}  {r.ultima_ip}")
        print(f"  key {r.clave}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
