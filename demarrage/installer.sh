#!/bin/bash
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

if [[ $EUID -ne 0 || $(cat /sys/class/dmi/id/product_name) != T305CA ]]; then
    echo 'Exécuter avec sudo sur un ASUS T305CA.' >&2
    exit 1
fi
for tool in usbreset zenity; do command -v "$tool" >/dev/null; done

install -Dm755 asus-t305ca-reprendre-clavier /usr/local/libexec/asus-t305ca-reprendre-clavier
install -Dm755 asus-t305ca-verifier-materiel /usr/local/libexec/asus-t305ca-verifier-materiel
install -Dm755 asus-t305ca-backlight.py /usr/local/libexec/asus-t305ca-backlight.py
install -Dm755 t305ca-alerte-materiel /usr/local/bin/t305ca-alerte-materiel

for unit in asus-t305ca-reprendre-clavier.service asus-t305ca-verifier-materiel.service; do
    install -m 644 "$unit" "/etc/systemd/system/$unit"
done
systemd-analyze verify /etc/systemd/system/asus-t305ca-{reprendre-clavier,verifier-materiel}.service
systemctl daemon-reload
systemctl enable --now asus-t305ca-reprendre-clavier.service asus-t305ca-verifier-materiel.service
