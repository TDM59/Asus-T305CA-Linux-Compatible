#!/bin/bash
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

if [[ $EUID -eq 0 || $(cat /sys/class/dmi/id/product_name) != T305CA ||
      $(findmnt -n -o FSTYPE /) != ext4 || $(findmnt -n -o TARGET -T /boot) != / ]]; then
    echo 'Lancer sans sudo depuis la session Mint installée sur le T305CA, avec la racine et /boot sur la même partition ext4.' >&2
    exit 1
fi
. /etc/os-release
[[ $ID == linuxmint && $VERSION_ID == 22.3 && $(dpkg --print-architecture) == amd64 ]]
sha256sum --check --quiet SHA256SUMS.txt

case "${1:-}" in
    systeme)
        if command -v mokutil >/dev/null && mokutil --sb-state 2>/dev/null | grep -q 'SecureBoot enabled'; then
            echo 'Les pilotes caméra fournis sont non signés. Cette restauration attend Secure Boot désactivé.' >&2
            exit 1
        fi
        sudo apt install ./paquets/linux-image-7.0.0-42-generic_*.deb \
            ./paquets/linux-modules-7.0.0-42-generic_*.deb \
            ./paquets/linux-main-modules-*-7.0.0-42-generic_*.deb \
            ./paquets/libcamera*.deb ./paquets/v4l-utils_*.deb ./paquets/libv4l2rds0t64_*.deb \
            ./paquets/iio-sensor-proxy_*.deb ./paquets/libevent-*.deb ./paquets/liblttng-ust*.deb \
            pipewire pipewire-pulse libspa-0.2-modules wireplumber xfce4-pulseaudio-plugin \
            x11-xserver-utils psmisc usbutils zenity
        sudo bash restaurer-systeme.sh "$(id -un)"
        sudo bash demarrage/installer.sh
        echo 'Redémarrer sur l’entrée ASUS T305CA, puis exécuter la phase session.'
        ;;
    session)
        [[ $(uname -r) == 7.0.0-42-generic ]] || {
            echo 'Redémarrer d’abord sur l’entrée ASUS T305CA.' >&2
            exit 1
        }
        install -Dm644 demarrage/t305ca-alerte-materiel.desktop \
            "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/t305ca-alerte-materiel.desktop"
        bash restaurer-session.sh
        ;;
    *)
        echo 'Usage : bash installer-correctifs.sh systeme|session' >&2
        exit 2
        ;;
esac
