#!/usr/bin/env python3
"""Test manuel du rétroéclairage du clavier ASUS Transformer 3 T305CA."""

import argparse
import fcntl
import os
from pathlib import Path
import stat
import sys

# Descripteur de la collection ASUS contenant le rapport Feature 0x5A.
FEATURE_SIGNATURE = bytes.fromhex("0631ff0976a10105ff855a19002aff00150026ff007508950fb102")
# Requêtes hidraw pour un rapport de 16 octets sur le Linux x86-64 du T305CA.
SET_FEATURE_16 = 0xC0104806
LEVEL_STATE = Path("/run/asus-t305ca-backlight.level")
GET_FEATURE_16 = 0xC0104807
INITIALIZE = b"\x5aASUS Tech.Inc.\x00"
QUERY_CAPABILITIES = bytes.fromhex("5a 05 20 31 00 08")


def find_keyboard():
    model = Path("/sys/class/dmi/id/product_name").read_text().strip()
    if model != "T305CA":
        raise RuntimeError(f"Modèle non pris en charge par cet essai : {model}")

    keyboards = []
    for interface in Path("/sys/class/hidraw").glob("hidraw*"):
        device = interface / "device"
        if "HID_ID=0003:00000B05:0000184A" not in (device / "uevent").read_text().splitlines():
            continue
        if FEATURE_SIGNATURE not in (device / "report_descriptor").read_bytes():
            continue
        keyboards.append(interface)

    if len(keyboards) != 1:
        raise RuntimeError(f"Une interface clavier ASUS attendue, {len(keyboards)} détectée(s).")
    return keyboards[0]


def feature(fd, operation, payload):
    report = bytearray(payload.ljust(16, b"\0"))
    transferred = fcntl.ioctl(fd, operation, report, True)
    if transferred < len(payload):
        raise RuntimeError(f"Rapport HID incomplet ({transferred} octets).")
    return bytes(report[:transferred])


def set_level(interface, level):
    expected_device = tuple(map(int, (interface / "dev").read_text().strip().split(":")))
    fd = os.open(Path("/dev") / interface.name, os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        actual_device = (os.major(info.st_rdev), os.minor(info.st_rdev))
        if not stat.S_ISCHR(info.st_mode) or actual_device != expected_device:
            raise RuntimeError("L’interface du clavier a changé. Rebranche le clavier et réessaie.")

        # Initialisation et interrogation des capacités identifiées dans AsHidSrv.
        feature(fd, SET_FEATURE_16, INITIALIZE)
        feature(fd, SET_FEATURE_16, QUERY_CAPABILITIES)
        capabilities = feature(fd, GET_FEATURE_16, b"\x5a")
        print(f"Réponse du clavier : {capabilities.hex(' ')}", flush=True)
        if len(capabilities) < 7 or not capabilities.startswith(QUERY_CAPABILITIES):
            raise RuntimeError("Le clavier n’a pas renvoyé la réponse de capacités attendue.")
        if not capabilities[6] & 1:
            raise RuntimeError("Le clavier ne signale pas la prise en charge de cette commande de luminosité.")

        feature(fd, SET_FEATURE_16, bytes([0x5A, 0xBA, 0xC5, 0xC4, level]))
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("niveau", nargs="?", type=int, choices=range(4),
                        help="0 pour éteindre, 1 à 3 pour allumer. Sans niveau, détection seule.")
    args = parser.parse_args()
    try:
        interface = find_keyboard()
        print(f"Interface ASUS détectée : /dev/{interface.name}")
        if args.niveau is not None:
            set_level(interface, args.niveau)
            if os.geteuid() == 0:
                LEVEL_STATE.write_text(f"{args.niveau}\n")
            print(f"Niveau {args.niveau} envoyé. Vérifie l’éclairage du clavier.")
    except (OSError, RuntimeError) as error:
        print(f"Essai interrompu : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
