"""Temporary open of RTSP port 7236/tcp via pkexec + ufw.

The port should stay open only while projecting. ufw is active on this machine
and FluxCast does not touch it (firewalld only).
"""

from __future__ import annotations

import subprocess

from conexion_tv.core.errors import FirewallError

PUERTO = 7236
_COMENTARIO = "conexion-tv-miracast"


def puerto_abierto(puerto: int = PUERTO) -> bool:
    """True if ufw already has a rule for the RTSP port.

    `ufw status` often needs privileges; on failure we return False and the UI
    shows it as closed.
    """
    try:
        r = subprocess.run(
            ["ufw", "status"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    texto = (r.stdout or "") + (r.stderr or "")
    return str(puerto) in texto and "ALLOW" in texto.upper()


def abrir_puerto(puerto: int = PUERTO) -> None:
    _pkexec(["ufw", "allow", f"{puerto}/tcp", "comment", _COMENTARIO])


def cerrar_puerto(puerto: int = PUERTO) -> None:
    _pkexec(["ufw", "delete", "allow", f"{puerto}/tcp"])


def _pkexec(argv: list[str]) -> None:
    try:
        r = subprocess.run(
            ["pkexec", *argv],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise FirewallError(
            "pkexec is not available.",
            consejo="Install policykit-1 or open the port by hand: sudo ufw allow 7236/tcp",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise FirewallError("Timed out waiting for the firewall password.") from exc
    if r.returncode != 0:
        detalle = (r.stderr or r.stdout or "").strip() or f"code {r.returncode}"
        raise FirewallError(
            f"Could not change the firewall: {detalle}",
            consejo="Cancel if you do not want to open it, or run: sudo ufw allow 7236/tcp",
        )
