#!/usr/bin/env python3
"""Rowenta Pure Air - Wi-Fi setup wizard for the purifier.

No administrator rights, nothing to install (just Python 3, or the packaged .exe).

    python rowenta_wifi_setup.py            windowed wizard (recommended)
    python rowenta_wifi_setup.py --cli      text version
    python rowenta_wifi_setup.py --selftest [file]   internal check

Steps: 1) put the purifier in pairing mode, 2) connect this computer to its
"AIR PURIFIER XXXX" network, 3) type your home Wi-Fi name and password (sent to the purifier
in one outgoing UDP packet), 4) check that the purifier shows up on your network.
Nothing is sent to the Internet, the password is not stored and saved Windows passwords are not read.

The interface is in English. Set the environment variable ROWENTA_WIFI_LANG=es for Spanish.
"""
from __future__ import annotations

import datetime as dt
import getpass
import ipaddress
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

__version__ = "0.3.0"

PORT = 80
AP_NET = "192.168.10."  # network of the purifier's pairing mode
DESTINATIONS = ("192.168.10.255", "192.168.10.1", "255.255.255.255")
SECURITY_WPA2 = 3  # 0 open, 1 WEP, 2 WPA1, 3 WPA2, 4 WPA1/2
DEVTYPE = 0x4F9A  # Broadlink devtype of the purifier ("supor_air")
AP_NAME_PREFIX = "AIR PURIFIER"
# Window / taskbar icon (64 px PNG: Wi-Fi symbol = local control). Same artwork as assets/icon.ico.
ICON_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAEfklEQVR42u1bS08TURS+/0DFBy6ruFWHhRsTXz9A3ZqoSVMpz6pA"
    "8YWixogBEq3xRViYCComaoyJRd3gmEAEd4grZNEoLjHjBrfH85UWqZ3X7TyovU7yNdd77znn+757ZpiYjBAurlWnjmuMFENnGAwq"
    "Uxg5juCqCa8XJ4kyMmUs2AngHi1FeCTnJFUIoCXiTnwHt3sHt1IHB1YWoElzI54qHJqV+EiFnrxZJxTfDquSCZ1BikAvEL86mYgy"
    "SDFElxuQUdCAzKL49oTGIEWhwYCUwgakYICusAG6WN3WYjBIURhiDQ9Uxn8Dgi6w7UoXHb4/QD1vR2hs9ksWVld+HXsRg9jgDWjl"
    "gc/Y1XeN7r1/R19/zJPXCzmQCzmD4OqrAc2Ph2j6+xwFdSE3apSdAedePKOfvxYorAu1UNMfA042U6nYfzsl3eZjszNZDH+coJ43"
    "6Swwzs/L3h7g4EWDqOIfWUTOJrOk3ZxUenqK23aQdvd1u86PvYhBrJvOAhdwKkWLtAEg53TqOEkIKIWQGZDLqTvAScbkPwac4IFL"
    "ND8atD2RsS8ztP9WimRyygC5UcOu48BRJqeQEW/p/vx8oMLNjEBNq0vGBOFVfL8+SpEzSdv47ZcvZHMMT07YniDWsAd7EWOXEzVR"
    "26sJoup4Ezlheu5bcbstLFDLw0HbuBYmYSfY8S8GxyKHbQ3mAC5F7wzM2Y02sZZ/nLDpdDuNfJoqEL+np9tyP0jZtaj02yDnQk6r"
    "euCy3ARwBWc32lwZkMfw5Adb8Zg36xbf3gQ5t11tcANHGU1ibYIHEtAunTed732ddn2a49za/e9GqXcknQXGmHPbNaglw80O0gaY"
    "YXjig+PJdT5/StpFZ4LYg71OnYSafnAXQYrHqR64eaPk3Igdt3mI+mGCJwNwWmZPYMwdGej35YQA5LKq46arbA1Y19JIXrD32tUC"
    "cmjd2q5O8pr3byDn8tsCNVHba17hJzlgc0eb5b6jfJJoW7OHHeawhj1W8cidr+OXycKvEwI5K/GJoQdS7wXYixjZOqUZ0MyDgLA5"
    "2UbjM6W/CSIWOYLkGJgBe7uvmj64pP/3B/c65/rnDOhNv7Jtcdzv2ANYPReWXnx4T3AGNDVQUEgMPihq6YM3rlvux9rftwxyBMlR"
    "rOefIJE3oY9P0W1MX657EBs0v8ANAGraW0OJKc2ARh4ojBUxoCYRoyd3d9Lnoa1ZYIw5JQyA0J/PthC9jBQAcythgljfUE9h4smd"
    "nUXi88Ba2HzEBv4JE2anv7wLwuYTugFW4vOoeANeD+ywFI+18A2o50GI2Jc8ZPkQxFrYfEI3IG/C+P3aJfEYr4T4FTOgnCA2xOMG"
    "gxSFIarjcZ1BikKHASmFDUiJ6rq4xiBFsfj1CA8yCorPLH0vwP+IKmhA4ed01cfqdAYpAr3om6GNx+oiDINBFQ5oNP+GkBc0BQyw"
    "/3Ywa0KMXYrx5sqC4Sh+yYQY3w6xOr2CxENLRPobYg6KMjL/sHBwj3r+ipyT4LZI5Zw0yrrNFzmCq6t2/w0FJCaubj4mqwAAAABJ"
    "RU5ErkJggg=="
)

# --------------------------------------------------------------------------- textos
TEXTS: dict[str, dict[str, str]] = {
    "es": {
        "window": "Conectar purificador Rowenta al Wi-Fi",
        "step": "Paso {n} de {total}",
        "back": "Atrás",
        "next": "Siguiente",
        "send": "Enviar al purificador",
        "close": "Cerrar",
        "search": "Buscar mi purificador",
        "search_again": "Buscar otra vez",
        "restart": "Empezar de nuevo",
        "skip": "Omitir la comprobación",
        "copy_ip": "Copiar IP",
        "copy_mac": "Copiar dirección física",
        "copied": "Copiado",
        "p0_title": "Pon el purificador en modo emparejamiento",
        "p0_body": (
            "Este asistente envía los datos de tu Wi-Fi al purificador y comprueba que se ha conectado. "
            "No necesita permisos de administrador y no envía nada a Internet.\n\n"
            "Primero, el purificador:\n\n"
            "  1. Enchúfalo y enciéndelo.\n"
            "  2. Mantén pulsado el botón Wi-Fi durante unos 3 segundos.\n"
            "  3. El icono Wi-Fi del aparato debe empezar a parpadear rápido: es la señal de que está en "
            "modo emparejamiento. Si no lo hace, repite la pulsación.\n\n"
            "En ese modo el purificador crea su propia red Wi-Fi, con un nombre como «AIR PURIFIER XXXX» "
            "(las cuatro últimas cifras cambian de un aparato a otro). Su contraseña está en la etiqueta "
            "del aparato."
        ),
        "p1_title": "Conecta este ordenador a la red del purificador",
        "p1_body": (
            "Ahora conecta este ordenador a esa red desde el icono de Wi-Fi de Windows:\n\n"
            "  1. Busca una red llamada «AIR PURIFIER» seguida de cuatro caracteres, por ejemplo "
            "«AIR PURIFIER XXXX».\n"
            "  2. Conéctate con la contraseña de la etiqueta del purificador.\n\n"
            "• Windows puede avisar de «sin Internet»: es normal, mantén la conexión.\n"
            "• Si Windows vuelve solo a tu Wi-Fi de casa, desmarca «Conectar automáticamente» en esa red "
            "mientras dura el proceso.\n"
            "• Si no ves la red, comprueba que el icono Wi-Fi del purificador sigue parpadeando rápido."
        ),
        "p1_current": "Red actual:  {ssid}",
        "p1_none": "Sin conexión Wi-Fi",
        "p1_ok": "✔ Conectado a la red del purificador. Pulsa Siguiente.",
        "p1_wait": "Esperando a que te conectes a «AIR PURIFIER xxxx»…",
        "p1_force": "No detecta mi conexión: continuar de todos modos",
        "p2_title": "Escribe los datos de tu Wi-Fi",
        "p2_body": (
            "Elige o escribe el nombre de tu Wi-Fi y su contraseña. Solo se envían al purificador y no se "
            "guardan.\n\n"
            "Tu Wi-Fi tiene que cumplir:\n"
            "  • Banda de 2,4 GHz activada.\n"
            "  • Seguridad WPA2 (vale la mixta WPA2/WPA3).\n"
            "  • Sin «Smart Connect» ni «band steering» (un único nombre para 2,4 y 5 GHz): en las pruebas, "
            "el purificador no conseguía unirse con eso activado. Desactívalo en tu router."
        ),
        "p2_ssid": "Nombre del Wi-Fi",
        "p2_pwd": "Contraseña",
        "p2_show": "Mostrar la contraseña",
        "p2_bad_ssid": "El nombre debe tener entre 1 y 32 caracteres, sin tildes ni ñ.",
        "p2_bad_pwd": "La contraseña debe tener entre 8 y 63 caracteres, sin tildes ni ñ.",
        "p2_error": "No se pudo enviar: {err}",
        "p3_title": "Comprueba que se ha conectado",
        "p3_body": (
            "Datos enviados. Ahora:\n\n"
            "  1. Reconecta este ordenador a tu Wi-Fi de casa (la red del purificador desaparecerá).\n"
            "  2. Espera unos 30 segundos: el icono Wi-Fi del purificador pasará a fijo.\n"
            "  3. Pulsa «Buscar mi purificador»."
        ),
        "p3_searching": "Buscando en tu red… (puede tardar unos segundos)",
        "p3_notfound": (
            "No lo he encontrado. Comprueba que:\n"
            "  • El icono Wi-Fi del purificador está fijo. Si parpadea despacio y se apaga, no ha podido "
            "unirse: revisa 2,4 GHz, WPA2 y desactiva Smart Connect, y empieza de nuevo.\n"
            "  • Este ordenador está en la misma red (no en una red de invitados aislada)."
        ),
        "p4_title": "¡Listo! El purificador está en tu red",
        "p4_found": "Purificador encontrado:  {ip}   ({mac})",
        "p4_unverified": "No se ha comprobado que el purificador esté en tu red.",
        "p4_next": (
            "Siguientes pasos en Home Assistant:\n\n"
            "  1. Instala la integración «Rowenta Pure Air (local)» (con HACS, o copiando su carpeta a "
            "custom_components) y reinicia Home Assistant.\n"
            "  2. Ajustes → Dispositivos y servicios → Añadir integración → Rowenta Pure Air.\n"
            "  3. Elige «Ya está conectado a mi Wi-Fi: búscalo».\n"
            "  4. Recomendado: en tu router, reserva esa IP para el purificador (reserva DHCP) para que no cambie."
        ),
    },
    "en": {
        "window": "Connect Rowenta purifier to Wi-Fi",
        "step": "Step {n} of {total}",
        "back": "Back",
        "next": "Next",
        "send": "Send to purifier",
        "close": "Close",
        "search": "Find my purifier",
        "search_again": "Search again",
        "restart": "Start over",
        "skip": "Skip the check",
        "copy_ip": "Copy IP",
        "copy_mac": "Copy MAC address",
        "copied": "Copied",
        "p0_title": "Put the purifier in pairing mode",
        "p0_body": (
            "This wizard sends your Wi-Fi details to the purifier and checks that it connected. "
            "It needs no administrator rights and sends nothing to the Internet.\n\n"
            "First, the purifier:\n\n"
            "  1. Plug it in and switch it on.\n"
            "  2. Hold the Wi-Fi button for about 3 seconds.\n"
            "  3. The appliance's Wi-Fi icon should start blinking fast: that means it is in pairing mode. "
            "If it does not, repeat the press.\n\n"
            "In that mode the purifier creates its own Wi-Fi network, named like 'AIR PURIFIER XXXX' (the "
            "last four characters differ from one appliance to another). Its password is on the appliance "
            "label."
        ),
        "p1_title": "Connect this computer to the purifier's network",
        "p1_body": (
            "Now connect this computer to that network from the Windows Wi-Fi icon:\n\n"
            "  1. Look for a network called 'AIR PURIFIER' followed by four characters, for example "
            "'AIR PURIFIER XXXX'.\n"
            "  2. Connect using the password on the purifier's label.\n\n"
            "• Windows may warn 'no Internet': that is normal, stay connected.\n"
            "• If Windows jumps back to your home Wi-Fi, untick 'Connect automatically' on that network "
            "while this runs.\n"
            "• If you cannot see the network, check that the purifier's Wi-Fi icon is still blinking fast."
        ),
        "p1_current": "Current network:  {ssid}",
        "p1_none": "No Wi-Fi connection",
        "p1_ok": "✔ Connected to the purifier's network. Press Next.",
        "p1_wait": "Waiting for you to connect to 'AIR PURIFIER xxxx'…",
        "p1_force": "It does not detect my connection: continue anyway",
        "p2_title": "Enter your Wi-Fi details",
        "p2_body": (
            "Choose or type your Wi-Fi name and its password. They are only sent to the purifier and are "
            "not stored.\n\n"
            "Your Wi-Fi must be:\n"
            "  • 2.4 GHz band enabled.\n"
            "  • WPA2 security (mixed WPA2/WPA3 is fine).\n"
            "  • Without 'Smart Connect' or 'band steering' (one name for 2.4 and 5 GHz): in testing the "
            "purifier could not join with it enabled. Turn it off in your router."
        ),
        "p2_ssid": "Wi-Fi name",
        "p2_pwd": "Password",
        "p2_show": "Show password",
        "p2_bad_ssid": "The name must be 1-32 plain ASCII characters.",
        "p2_bad_pwd": "The password must be 8-63 plain ASCII characters.",
        "p2_error": "Could not send: {err}",
        "p3_title": "Check that it connected",
        "p3_body": (
            "Details sent. Now:\n\n"
            "  1. Reconnect this computer to your home Wi-Fi (the purifier's network will disappear).\n"
            "  2. Wait about 30 seconds: the purifier's Wi-Fi icon turns solid.\n"
            "  3. Press 'Find my purifier'."
        ),
        "p3_searching": "Searching your network… (it may take a few seconds)",
        "p3_notfound": (
            "Not found. Check that:\n"
            "  • The purifier's Wi-Fi icon is solid. If it blinks slowly and turns off, it could not join: "
            "check 2.4 GHz, WPA2, turn off Smart Connect and start over.\n"
            "  • This computer is on the same network (not an isolated guest network)."
        ),
        "p4_title": "Done! The purifier is on your network",
        "p4_found": "Purifier found:  {ip}   ({mac})",
        "p4_unverified": "It was not verified that the purifier is on your network.",
        "p4_next": (
            "Next steps in Home Assistant:\n\n"
            "  1. Install the 'Rowenta Pure Air (local)' integration (with HACS, or by copying its folder "
            "to custom_components) and restart Home Assistant.\n"
            "  2. Settings → Devices & services → Add integration → Rowenta Pure Air.\n"
            "  3. Choose 'It is already on my Wi-Fi: search for it'.\n"
            "  4. Recommended: in your router, reserve that IP for the purifier (DHCP reservation) so it "
            "does not change."
        ),
    },
}


def detect_language() -> str:
    """English by default; Spanish only when ROWENTA_WIFI_LANG=es is set."""
    return "es" if os.environ.get("ROWENTA_WIFI_LANG", "").lower().startswith("es") else "en"


# --------------------------------------------------------------------------- core (no windows)
def build_packet(ssid: str, password: str, security_mode: int = SECURITY_WPA2) -> bytes:
    """Broadlink pairing packet (identical to python-broadlink's ``broadlink.setup``)."""
    payload = bytearray(0x88)
    payload[0x26] = 0x14  # seems fixed
    for i, letter in enumerate(ssid):
        payload[68 + i] = ord(letter)
    for i, letter in enumerate(password):
        payload[100 + i] = ord(letter)
    payload[0x84] = len(ssid)
    payload[0x85] = len(password)
    payload[0x86] = security_mode
    checksum = sum(payload, 0xBEAF) & 0xFFFF
    payload[0x20] = checksum & 0xFF
    payload[0x21] = checksum >> 8
    return bytes(payload)


def valid_ascii(text: str, min_len: int, max_len: int) -> bool:
    return min_len <= len(text) <= max_len and all(32 <= ord(c) < 127 for c in text)


def local_ip_towards_purifier() -> str:
    """Local address that would be used to reach 192.168.10.1 (sends nothing)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((AP_NET + "1", PORT))
        return sock.getsockname()[0]
    except OSError:
        return "?"
    finally:
        sock.close()


def send_packet(packet: bytes) -> None:
    """Send the packet to the purifier's network (and to the broadcasts), several times.

    On Windows with several adapters, 255.255.255.255 may leave through another interface, so the
    purifier network's broadcast and its direct IP are used as well.
    """
    sent = 0
    last_error: OSError | None = None
    for _ in range(2):
        for dest in DESTINATIONS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(packet, (dest, PORT))
                sent += 1
            except OSError as err:  # some route may not exist; it is enough that one gets through
                last_error = err
            finally:
                sock.close()
        time.sleep(0.5)
    if sent == 0 and last_error is not None:
        raise last_error


# -- Windows Wi-Fi (read-only, no administrator) --
def _run_netsh(*args: str) -> str:
    if not sys.platform.startswith("win"):
        return ""
    try:
        out = subprocess.run(
            ["netsh", "wlan", *args],
            capture_output=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    for encoding in ("utf-8", "cp850", "cp1252"):
        try:
            return out.decode(encoding)
        except UnicodeDecodeError:
            continue
    return out.decode("utf-8", errors="replace")


def current_wifi_ssid() -> str | None:
    """Name of the current Wi-Fi network, or None if there is none or it cannot be determined."""
    for line in _run_netsh("show", "interfaces").splitlines():
        match = re.match(r"^\s*SSID\s*:\s*(.+?)\s*$", line)
        if match:
            return match.group(1)
    return None


def known_wifi_profiles() -> list[str]:
    """Names (names only) of the Wi-Fi networks Windows already knows, to suggest them."""
    names: list[str] = []
    for line in _run_netsh("show", "profiles").splitlines():
        if ":" in line and re.search(r"(perfil|profile)", line, re.IGNORECASE):
            name = line.split(":", 1)[1].strip()
            if name and name not in names and not name.startswith(AP_NAME_PREFIX):
                names.append(name)
    return names


# -- Broadlink discovery (unicast hello, no libraries) --
@dataclass(frozen=True)
class Found:
    host: str
    mac: str
    name: str = ""


def hello_packet(now: dt.datetime | None = None) -> bytes:
    """Broadlink discovery 'hello' packet (identical to python-broadlink's)."""
    if now is None:
        now = dt.datetime.now(dt.timezone(dt.timedelta(seconds=-time.timezone)))
    packet = bytearray(0x30)
    data = bytearray(12)
    utcoffset = int(now.utcoffset().total_seconds() / 3600)
    data[:4] = utcoffset.to_bytes(4, "little", signed=True)
    data[4:6] = now.year.to_bytes(2, "little")
    data[6] = now.minute
    data[7] = now.hour
    data[8] = int(now.strftime("%y"))
    data[9] = now.isoweekday()
    data[10] = now.day
    data[11] = now.month
    packet[0x08:0x14] = data
    packet[0x18:0x1C] = socket.inet_aton("0.0.0.0")[::-1]
    packet[0x1C:0x1E] = (0).to_bytes(2, "little")
    packet[0x26] = 6
    checksum = sum(packet, 0xBEAF) & 0xFFFF
    packet[0x20:0x22] = checksum.to_bytes(2, "little")
    return bytes(packet)


def parse_hello_response(resp: bytes) -> tuple[int, str, str] | None:
    """Return (devtype, mac, name) from a 'hello' response, or None if it is not valid."""
    if len(resp) < 0x40:
        return None
    devtype = resp[0x34] | resp[0x35] << 8
    mac = ":".join(f"{b:02x}" for b in resp[0x3A:0x40][::-1])
    name = resp[0x40:].split(b"\x00")[0].decode("utf-8", errors="replace")
    return devtype, mac, name


def probe_host(host: str, *, port: int = PORT, timeout: float = 1.0) -> Found | None:
    """Ask ``host`` whether it is a supported purifier."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        sock.sendto(hello_packet(), (host, port))
        resp, _ = sock.recvfrom(1024)
    except OSError:  # includes timeout
        return None
    finally:
        sock.close()
    parsed = parse_hello_response(resp)
    if parsed is None or parsed[0] != DEVTYPE:
        return None
    return Found(host=host, mac=parsed[1], name=parsed[2])


def local_networks() -> list[ipaddress.IPv4Network]:
    """/24 networks of this computer (the main route's first), excluding the pairing ones."""
    addresses: list[str] = []
    primary = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        primary.connect(("8.8.8.8", 80))  # sends nothing: it only picks the outgoing interface
        addresses.append(primary.getsockname()[0])
    except OSError:
        pass
    finally:
        primary.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.append(info[4][0])
    except OSError:
        pass
    networks: list[ipaddress.IPv4Network] = []
    cgnat = ipaddress.ip_network("100.64.0.0/10")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_loopback or ip.is_link_local or ip in cgnat or address.startswith(AP_NET):
            continue
        net = ipaddress.ip_network(f"{address}/24", strict=False)
        if net not in networks:
            networks.append(net)
    return networks[:6]


def find_purifiers(
    networks: list[ipaddress.IPv4Network] | None = None, *, timeout: float = 1.0, workers: int = 64
) -> list[Found]:
    """Sweep the local networks looking for purifiers (a few seconds per /24 network).

    They are swept one at a time, the main route's first, stopping as soon as one has a result.
    """
    nets = local_networks() if networks is None else networks
    found: list[Found] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for net in nets:
            hosts = [str(h) for h in net.hosts()]
            for item in pool.map(lambda h: probe_host(h, timeout=timeout), hosts):
                if item is not None and item not in found:
                    found.append(item)
            if found:
                break
    return found


# --------------------------------------------------------------------------- text version
def run_cli() -> int:
    t = TEXTS[detect_language()]
    print(f"\n=== {t['window']} ===\n")
    print(f"[1/4] {t['p0_title']}\n{t['p0_body']}\n")
    print(f"[2/4] {t['p1_title']}\n{t['p1_body']}\n")
    try:
        input("Press Enter to continue ... ")
        ip = local_ip_towards_purifier()
        if not ip.startswith(AP_NET):
            print(f"\n(!) {t['p1_wait']}  [{ip}]")
            if input("Send anyway? (y/N): ").strip().lower() not in ("y", "yes"):
                return 1
        print(f"\n[3/4] {t['p2_title']}\n{t['p2_body']}")
        while True:
            ssid = input(f"\n{t['p2_ssid']}: ").strip()
            if valid_ascii(ssid, 1, 32):
                break
            print(t["p2_bad_ssid"])
        while True:
            password = getpass.getpass(f"{t['p2_pwd']}: ")
            if valid_ascii(password, 8, 63):
                break
            print(t["p2_bad_pwd"])
        send_packet(build_packet(ssid, password))
        print(f"\n[4/4] {t['p3_title']}\n{t['p3_body']}")
        answer = input("\nPress Enter to search (n = skip): ").strip().lower()
        found = [] if answer == "n" else find_purifiers()
    except (KeyboardInterrupt, EOFError):
        print()
        return 1
    if found:
        print("\n" + t["p4_title"] + "\n" + t["p4_found"].format(ip=found[0].host, mac=found[0].mac))
    else:
        print("\n" + (t["p4_unverified"] if answer == "n" else t["p3_notfound"]))
    print("\n" + t["p4_next"])
    return 0 if found or answer == "n" else 2


# --------------------------------------------------------------------------- windowed wizard
class SetupWizard:
    """5-screen wizard (4 steps + final). External functions are injectable for testing.

    0 pairing mode · 1 connect the PC to the purifier's network · 2 Wi-Fi details ·
    3 verify · 4 done.
    """

    TOTAL = 4  # numbered screens (the last one, "done", does not count)
    LAST = 4

    def __init__(
        self,
        root,
        lang: str,
        *,
        ssid_fn: Callable[[], str | None] = current_wifi_ssid,
        profiles_fn: Callable[[], list[str]] = known_wifi_profiles,
        ap_ip_fn: Callable[[], str] = local_ip_towards_purifier,
        send_fn: Callable[[bytes], None] = send_packet,
        scan_fn: Callable[[], list[Found]] = find_purifiers,
    ) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.root = root
        self.t = TEXTS[lang]
        self.ssid_fn, self.profiles_fn, self.ap_ip_fn = ssid_fn, profiles_fn, ap_ip_fn
        self.send_fn, self.scan_fn = send_fn, scan_fn
        self.page = 0
        self.found: Found | None = None
        self.verified = False
        self._queue: queue.Queue = queue.Queue()
        self._poll_job = None
        self._closing = False

        root.title(self.t["window"])
        try:
            self._icon = self.tk.PhotoImage(data=ICON_PNG_B64)  # keep a reference
            root.iconphoto(True, self._icon)
        except Exception:  # noqa: BLE001 - the icon is cosmetic
            pass
        root.geometry("700x620")
        root.minsize(640, 580)

        style = ttk.Style(root)
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Step.TLabel", foreground="#666666")
        style.configure("Ok.TLabel", foreground="#1a7f37")

        outer = ttk.Frame(root, padding=(24, 18, 24, 14))
        outer.pack(fill="both", expand=True)
        self.step_label = ttk.Label(outer, style="Step.TLabel")
        self.step_label.pack(anchor="w")
        self.title_label = ttk.Label(outer, style="Title.TLabel", wraplength=640)
        self.title_label.pack(anchor="w", pady=(2, 12))
        self.body = ttk.Frame(outer)
        self.body.pack(fill="both", expand=True)
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        self.back_btn = ttk.Button(footer, command=self.go_back)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(footer, command=self.go_next)
        self.next_btn.pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.show(0)
        self._drain_job = root.after(100, self._drain_queue)

    # -- helpers
    def close(self) -> None:
        self._closing = True
        for job in (self._poll_job, self._drain_job):
            if job is not None:
                self.root.after_cancel(job)
        self.root.destroy()

    def _run_bg(self, fn: Callable[[], object], on_done: Callable[[object], None]) -> None:
        def worker() -> None:
            try:
                result: object = fn()
            except Exception as err:  # noqa: BLE001 - handed back to the UI thread
                result = err
            self._queue.put((on_done, result))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                on_done, result = self._queue.get_nowait()
                on_done(result)
        except queue.Empty:
            pass
        self._drain_job = self.root.after(100, self._drain_queue)

    def _label(self, parent, text: str, **kwargs):
        label = self.ttk.Label(parent, text=text, wraplength=640, justify="left", **kwargs)
        label.pack(anchor="w", fill="x", pady=(0, 8))
        return label

    # -- navigation
    def show(self, page: int) -> None:
        if self._poll_job is not None:
            self.root.after_cancel(self._poll_job)
            self._poll_job = None
        self.page = page
        for child in self.body.winfo_children():
            child.destroy()
        t = self.t
        numbered = page < self.TOTAL
        self.step_label.config(text=t["step"].format(n=page + 1, total=self.TOTAL) if numbered else "")
        self.back_btn.config(text=t["back"], state="normal" if 0 < page < self.LAST else "disabled")
        self.next_btn.pack_forget()
        self.next_btn.pack(side="right")
        self.next_btn.config(text=t["next"], state="normal")
        self.title_label.config(text=t[f"p{page}_title"])
        getattr(self, f"_build_{page}")()

    def go_next(self) -> None:
        if self.page == 2:
            self._send()
        elif self.page == self.LAST:
            self.close()
        elif self.page < 3:
            self.show(self.page + 1)

    def go_back(self) -> None:
        if self.page > 0:
            self.show(self.page - 1)

    # -- screens
    def _build_0(self) -> None:
        self._label(self.body, self.t["p0_body"])

    def _build_1(self) -> None:
        ttk, tk, t = self.ttk, self.tk, self.t
        self._label(self.body, t["p1_body"])
        self.net_label = ttk.Label(self.body, font=("Segoe UI", 11, "bold"))
        self.net_label.pack(anchor="w", pady=(8, 2))
        self.net_status = ttk.Label(self.body, wraplength=640)
        self.net_status.pack(anchor="w")
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.body, text=t["p1_force"], variable=self.force_var, command=self._update_p1_next
        ).pack(anchor="w", pady=(14, 0))
        self._ap_connected = False
        self._update_p1_next()
        self._poll_wifi()

    def _poll_wifi(self) -> None:
        if self._closing or self.page != 1:
            return

        def work() -> tuple[str | None, str]:
            return self.ssid_fn(), self.ap_ip_fn()

        def done(result: object) -> None:
            if self._closing or self.page != 1 or isinstance(result, Exception):
                return
            ssid, ip = result  # type: ignore[misc]
            self._ap_connected = bool((ssid or "").upper().startswith(AP_NAME_PREFIX)) or ip.startswith(AP_NET)
            self.net_label.config(text=self.t["p1_current"].format(ssid=ssid or self.t["p1_none"]))
            if self._ap_connected:
                self.net_status.config(text=self.t["p1_ok"], style="Ok.TLabel")
            else:
                self.net_status.config(text=self.t["p1_wait"], style="TLabel")
            self._update_p1_next()

        self._run_bg(work, done)
        self._poll_job = self.root.after(2000, self._poll_wifi)

    def _update_p1_next(self) -> None:
        ok = getattr(self, "_ap_connected", False) or self.force_var.get()
        self.next_btn.config(state="normal" if ok else "disabled")

    def _build_2(self) -> None:
        ttk, tk, t = self.ttk, self.tk, self.t
        self._label(self.body, t["p2_body"])
        form = ttk.Frame(self.body)
        form.pack(anchor="w", fill="x", pady=(6, 0))
        ttk.Label(form, text=t["p2_ssid"]).grid(row=0, column=0, sticky="w", pady=4)
        self.ssid_var = tk.StringVar()
        self.ssid_box = ttk.Combobox(form, textvariable=self.ssid_var, width=38)
        self.ssid_box.grid(row=0, column=1, sticky="w", padx=10)
        ttk.Label(form, text=t["p2_pwd"]).grid(row=1, column=0, sticky="w", pady=4)
        self.pwd_var = tk.StringVar()
        self.pwd_entry = ttk.Entry(form, textvariable=self.pwd_var, show="•", width=40)
        self.pwd_entry.grid(row=1, column=1, sticky="w", padx=10)
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form, text=t["p2_show"], variable=self.show_var,
            command=lambda: self.pwd_entry.config(show="" if self.show_var.get() else "•"),
        ).grid(row=2, column=1, sticky="w", padx=10)
        self.error_label = ttk.Label(self.body, foreground="#b42318", wraplength=640, justify="left")
        self.error_label.pack(anchor="w", pady=(12, 0))
        for var in (self.ssid_var, self.pwd_var):
            var.trace_add("write", lambda *_: self._validate_p2())
        self.next_btn.config(text=t["send"], state="disabled")
        self._run_bg(self.profiles_fn, self._fill_profiles)
        self.ssid_box.focus_set()

    def _fill_profiles(self, result: object) -> None:
        if self.page == 2 and not isinstance(result, Exception) and result:
            self.ssid_box.config(values=list(result))  # type: ignore[arg-type]

    def _validate_p2(self) -> None:
        ssid, pwd = self.ssid_var.get().strip(), self.pwd_var.get()
        message = ""
        if ssid and not valid_ascii(ssid, 1, 32):
            message = self.t["p2_bad_ssid"]
        elif pwd and (len(pwd) > 63 or not all(32 <= ord(c) < 127 for c in pwd)):
            message = self.t["p2_bad_pwd"]  # (while typing, fewer than 8 characters is not an error yet)
        self.error_label.config(text=message)
        ok = valid_ascii(ssid, 1, 32) and valid_ascii(pwd, 8, 63)
        self.next_btn.config(state="normal" if ok else "disabled")

    def _send(self) -> None:
        ssid, pwd = self.ssid_var.get().strip(), self.pwd_var.get()
        self.next_btn.config(state="disabled")
        self.back_btn.config(state="disabled")
        packet = build_packet(ssid, pwd)

        def done(result: object) -> None:
            if isinstance(result, Exception):
                self.error_label.config(text=self.t["p2_error"].format(err=result))
                self.back_btn.config(state="normal")
                self._validate_p2()
                return
            self.pwd_var.set("")  # the password is not kept
            self.show(3)

        self._run_bg(lambda: self.send_fn(packet), done)

    def _build_3(self) -> None:
        ttk, t = self.ttk, self.t
        self._label(self.body, t["p3_body"])
        self.search_btn = ttk.Button(self.body, text=t["search"], command=self._search)
        self.search_btn.pack(anchor="w", pady=(10, 6))
        self.progress = ttk.Progressbar(self.body, mode="indeterminate", length=320)
        self.result_label = ttk.Label(self.body, wraplength=640, justify="left")
        self.result_label.pack(anchor="w", pady=(10, 0), fill="x")
        links = ttk.Frame(self.body)
        links.pack(anchor="w", pady=(16, 0))
        self.restart_btn = ttk.Button(links, text=t["restart"], command=lambda: self.show(0))
        self.restart_btn.pack(side="left")
        self.skip_btn = ttk.Button(links, text=t["skip"], command=self._skip)
        self.skip_btn.pack(side="left", padx=10)
        self.next_btn.pack_forget()  # on this screen you advance with "Search" or "Skip"
        self.back_btn.config(state="disabled")

    def _search(self) -> None:
        self.search_btn.config(state="disabled")
        self.result_label.config(text=self.t["p3_searching"])
        self.progress.pack(anchor="w")
        self.progress.start(12)

        def done(result: object) -> None:
            if self._closing or self.page != 3:
                return
            self.progress.stop()
            self.progress.pack_forget()
            self.search_btn.config(state="normal", text=self.t["search_again"])
            if isinstance(result, Exception) or not result:
                self.result_label.config(text=self.t["p3_notfound"])
                return
            self.found = result[0]  # type: ignore[index]
            self.verified = True
            self.show(4)

        self._run_bg(self.scan_fn, done)

    def _skip(self) -> None:
        self.found, self.verified = None, False
        self.show(4)

    def _build_4(self) -> None:
        ttk, t = self.ttk, self.t
        self.next_btn.config(text=t["close"], state="normal")
        self.back_btn.config(state="disabled")
        found = self.found
        if self.verified and found:
            ttk.Label(
                self.body, text=t["p4_found"].format(ip=found.host, mac=found.mac),
                font=("Segoe UI", 11, "bold"), style="Ok.TLabel",
            ).pack(anchor="w", pady=(0, 6))
            buttons = ttk.Frame(self.body)
            buttons.pack(anchor="w", pady=(0, 10))
            self.copy_ip_btn = ttk.Button(
                buttons, text=t["copy_ip"], command=lambda: self._copy(found.host, self.copy_ip_btn, t["copy_ip"])
            )
            self.copy_ip_btn.pack(side="left")
            self.copy_mac_btn = ttk.Button(
                buttons, text=t["copy_mac"], command=lambda: self._copy(found.mac, self.copy_mac_btn, t["copy_mac"])
            )
            self.copy_mac_btn.pack(side="left", padx=8)
        else:
            self._label(self.body, t["p4_unverified"])
        self._label(self.body, t["p4_next"])

    def _copy(self, text: str, button, original: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        button.config(text=self.t["copied"])
        self.root.after(1500, lambda: button.winfo_exists() and button.config(text=original))


def run_gui() -> int:
    if sys.platform.startswith("win"):
        try:  # sharp on scaled displays (125 %, 150 %...)
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001 - older Windows versions
            pass
    try:
        import tkinter as tk

        root = tk.Tk()
    except Exception:  # noqa: BLE001 - no tkinter or no display: text version
        return run_cli()
    SetupWizard(root, detect_language())
    root.mainloop()
    return 0


# --------------------------------------------------------------------------- internal self-test
def selftest(output: str | None) -> int:
    """Quick check without network or windows (useful on the .exe)."""
    lines = []
    try:
        packet = build_packet("MiRed", "clave-1234")
        assert len(packet) == 0x88 and packet[0x84] == 5 and packet[0x85] == 10
        assert len(hello_packet()) == 0x30
        assert valid_ascii("Wifi_2G", 1, 32) and not valid_ascii("passwórd1", 8, 63)
        for lang, texts in TEXTS.items():  # every screen has a title and a body
            for page in range(5):
                assert texts[f"p{page}_title"], (lang, page)
        lines.append(f"local networks: {[str(n) for n in local_networks()]}")
        import tkinter  # noqa: F401

        lines.append(f"tkinter {tkinter.TkVersion}")
        lines.append(f"rowenta_wifi_setup {__version__} OK")
        code = 0
    except Exception as err:  # noqa: BLE001
        lines.append(f"FALLO: {type(err).__name__}: {err}")
        code = 1
    text = "\n".join(lines) + "\n"
    if output:
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return code


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "--selftest":
        return selftest(args[1] if len(args) > 1 else None)
    if args and args[0] == "--cli":
        return run_cli()
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
