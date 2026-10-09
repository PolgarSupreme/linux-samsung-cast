"""Preferencia de canal Wi-Fi Direct (2,4 o 5 GHz).

FluxCast solo fuerza canales 1/6/11 (2,4 GHz) vía CLI. Para 5 GHz fijamos
OperRegClass/OperChannel en wpa_supplicant por D-Bus antes de arrancar, con
backend wpas y el PC como GO (intent 15).

Sentinel MATCH_AP_5GHZ (-1): usar el canal 5 GHz del AP asociado si lo hay;
si no, canal 36.
"""

from __future__ import annotations

import re
import subprocess

# Preferir el canal 5 GHz del router (misma radio = menos saltos de banda).
MATCH_AP_5GHZ = -1

# Clase operativa global IEEE (Annex E): 81 = 2,4 GHz; 115 = 5 GHz 36–48.
_REG_CLASS_24 = 81
_REG_CLASS_5_UNII1 = 115

CANALES_24 = frozenset({1, 6, 11})
CANALES_5 = frozenset({36, 40, 44, 48})


def es_canal_24(canal: int) -> bool:
    return int(canal) in CANALES_24


def es_canal_5(canal: int) -> bool:
    return int(canal) in CANALES_5


def requiere_fuerza_propia(canal: int | None) -> bool:
    """True si hay que fijar el canal fuera de la CLI de FluxCast (5 GHz)."""
    if canal is None:
        return False
    if int(canal) == MATCH_AP_5GHZ:
        return True
    return es_canal_5(int(canal))


def reg_class_para(canal: int) -> int:
    c = int(canal)
    if es_canal_24(c):
        return _REG_CLASS_24
    if es_canal_5(c):
        return _REG_CLASS_5_UNII1
    raise ValueError(f"Unsupported P2P channel: {c}")


def mhz_a_canal(mhz: int) -> int | None:
    """Convierte frecuencia Wi-Fi a número de canal (2,4 o UNII-1)."""
    f = int(mhz)
    if 2412 <= f <= 2472 and (f - 2412) % 5 == 0:
        return 1 + (f - 2412) // 5
    if 5180 <= f <= 5240 and (f - 5180) % 20 == 0:
        return 36 + (f - 5180) // 5
    return None


def frecuencia_ap_asociado(iface: str | None = None) -> int | None:
    """MHz del AP al que está asociada la interfaz managed, o None."""
    cmd = ["iw", "dev"]
    if iface:
        cmd = ["iw", "dev", iface, "link"]
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=3)
        except (OSError, subprocess.SubprocessError):
            return None
        m = re.search(r"freq:\s*(\d+)", out)
        return int(m.group(1)) if m else None
    try:
        out = subprocess.check_output(["iw", "dev"], text=True, stderr=subprocess.DEVNULL, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    # Primer enlace "Connected" con freq.
    m = re.search(r"Connected to .*?\n\s+freq:\s*(\d+)", out, re.DOTALL)
    if m:
        return int(m.group(1))
    m = re.search(r"freq:\s*(\d+)", out)
    return int(m.group(1)) if m else None


def resolver_canal(pedido: int | None, *, wifi_interface: str | None = None) -> int | None:
    """None → sin forzar; MATCH_AP_5GHZ → canal concreto; resto → tal cual."""
    if pedido is None:
        return None
    if int(pedido) != MATCH_AP_5GHZ:
        return int(pedido)
    mhz = frecuencia_ap_asociado(wifi_interface)
    if mhz is not None:
        canal = mhz_a_canal(mhz)
        if canal is not None and es_canal_5(canal):
            return canal
    return 36


def wpas_dbus_legible() -> bool:
    """True si el usuario puede leer Interfaces de wpa_supplicant por D-Bus.

    Sin la política `zz-dev.fluxcast.wpa-supplicant.conf`, el backend wpas de
    FluxCast falla con «P2P interface not found» aunque el kernel tenga P2P.
    """
    try:
        r = subprocess.run(
            [
                "gdbus",
                "call",
                "--system",
                "--dest",
                "fi.w1.wpa_supplicant1",
                "--object-path",
                "/fi/w1/wpa_supplicant1",
                "--method",
                "org.freedesktop.DBus.Properties.Get",
                "fi.w1.wpa_supplicant1",
                "Interfaces",
            ],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode != 0:
        return False
    err = (r.stderr or "") + (r.stdout or "")
    return "AccessDenied" not in err and "Rejected" not in err


def preparar_config_para_canal(
    *,
    p2p_channel: int | None,
    p2p_backend: str,
    go_intent: int | None,
    wifi_interface: str | None = None,
) -> tuple[int | None, str, int | None, str]:
    """Devuelve (canal, backend, go_intent, aviso).

    Forzar canal exige wpas + GO 15. Si D-Bus deniega wpa_supplicant, se
    degrada a NetworkManager y se anula el canal (aviso no vacío).
    """
    resuelto = resolver_canal(p2p_channel, wifi_interface=wifi_interface)
    backend = p2p_backend or "nm"
    go = go_intent
    aviso = ""
    if resuelto is None:
        return None, backend, go, aviso

    necesita_wpas = es_canal_5(resuelto) or es_canal_24(resuelto)
    if not necesita_wpas:
        return resuelto, backend, go, aviso

    if not wpas_dbus_legible():
        return (
            None,
            "nm",
            go_intent,
            "Cannot force the channel: missing D-Bus permission for wpa_supplicant "
            "(FluxCast policy). Continuing with NetworkManager on automatic channel. "
            "For 5 GHz install that policy and reload dbus.",
        )
    return resuelto, "wpas", 15 if go is None else go, aviso


def _rutas_p2p(iface: str | None) -> list[str]:
    try:
        r = subprocess.run(
            [
                "gdbus",
                "call",
                "--system",
                "--dest",
                "fi.w1.wpa_supplicant1",
                "--object-path",
                "/fi/w1/wpa_supplicant1",
                "--method",
                "org.freedesktop.DBus.Properties.Get",
                "fi.w1.wpa_supplicant1",
                "Interfaces",
            ],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    paths = re.findall(r"'(/[^']+)'", r.stdout or "")
    if not paths:
        return []
    physical = iface or ""
    p2p_dev = f"p2p-dev-{physical}" if physical and not physical.startswith("p2p-dev-") else physical

    def prio(path: str) -> int:
        try:
            ir = subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--system",
                    "--dest",
                    "fi.w1.wpa_supplicant1",
                    "--object-path",
                    path,
                    "--method",
                    "org.freedesktop.DBus.Properties.Get",
                    "fi.w1.wpa_supplicant1.Interface",
                    "Ifname",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return 9
        name = ""
        m = re.search(r"<'([^']*)'", ir.stdout or "")
        if m:
            name = m.group(1)
        if name == p2p_dev:
            return 0
        if name == physical:
            return 1
        return 2

    return sorted(paths, key=prio)


def aplicar_canal_operacion(
    canal: int,
    *,
    wifi_interface: str | None = None,
    usar_pkexec: bool = True,
) -> bool:
    """Fija OperRegClass/OperChannel en las interfaces P2P de wpa_supplicant."""
    reg = reg_class_para(canal)
    paths = _rutas_p2p(wifi_interface)
    if not paths:
        return False
    variante = (
        f"<{{'OperRegClass': <uint32 {reg}>, 'OperChannel': <uint32 {int(canal)}>}}>"
    )
    ok = False
    for path in paths:
        base = [
            "gdbus",
            "call",
            "--system",
            "--dest",
            "fi.w1.wpa_supplicant1",
            "--object-path",
            path,
            "--method",
            "org.freedesktop.DBus.Properties.Set",
            "fi.w1.wpa_supplicant1.Interface.P2PDevice",
            "P2PDeviceConfig",
            variante,
        ]
        cmds = [base]
        if usar_pkexec:
            cmds.insert(0, ["pkexec", *base])
        for cmd in cmds:
            try:
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if r.returncode == 0:
                ok = True
                break
        if ok:
            break
    return ok
