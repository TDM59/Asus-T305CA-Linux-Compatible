#!/bin/bash
set -Eeuo pipefail
cd "$(dirname "$(realpath "$0")")"
dropin=/etc/default/grub.d/99-t305ca-menu-masque.cfg
active=/boot/grub/grub.cfg
custom=/boot/grub/custom.cfg
backup=$(mktemp -d /var/backups/t305ca-demarrage.XXXXXX)
candidate=$(mktemp /boot/grub/t305ca-grub.XXXXXX)
modified=0
installed=0
cleanup() {
    if (( modified && ! installed )); then
        if [[ -f "$backup/menu-masque.cfg" ]]; then
            install -m 644 "$backup/menu-masque.cfg" "$dropin"
        else
            unlink "$dropin"
        fi
    fi
    if [[ -e "$candidate" ]]; then unlink "$candidate"; fi
    if [[ -e "$candidate.new" ]]; then unlink "$candidate.new"; fi
}
trap cleanup EXIT

grep -q 'GRUB_DEFAULT=t305ca-ov13850-7' /etc/default/grub.d/95-t305ca-camera.cfg
grep -q -- "--id 't305ca-ov13850-7'" "$custom"
grep -q 't305ca_ov13850_test=1' /proc/cmdline
grub-script-check "$custom"
cp -p "$active" "$backup/grub.cfg"
if [[ -f "$dropin" ]]; then cp -p "$dropin" "$backup/menu-masque.cfg"; fi

install -m 644 99-t305ca-menu-masque.cfg "$dropin"
modified=1
grub-mkconfig -o "$candidate"
grub-script-check "$candidate"
grep -q 'set default="t305ca-ov13850-7"' "$candidate"
grep -q 'set timeout_style=hidden' "$candidate"
grep -q 'set timeout=2$' "$candidate"
grep -q 'source.*custom.cfg' "$candidate"
if awk '/BEGIN .*30_os-prober/{section=1} /END .*30_os-prober/{section=0} section && /set timeout_style=menu/{found=1} END{exit !found}' "$candidate"; then
    echo 'La détection d’un autre système a forcé l’affichage du menu. Configuration GRUB conservée.' >&2
    exit 1
fi
chmod --reference="$active" "$candidate"
mv -T "$candidate" "$active"
installed=1
printf 'Menu GRUB masqué. Configuration précédente dans %s\n' "$backup"
