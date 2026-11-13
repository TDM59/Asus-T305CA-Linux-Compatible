#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ "$(id -u)" -eq 0 ]; then
    printf '%s\n' "Lance ce script depuis ta session Xfce, sans sudo." >&2
    exit 1
fi
config="${XDG_CONFIG_HOME:-$HOME/.config}"
install -d "$HOME/.local/lib/t305ca" "$config/systemd/user" "$config/autostart"
install -m 644 t305ca-*.py "$HOME/.local/lib/t305ca/"
install -m 644 t305ca-*.service "$config/systemd/user/"
install -m 644 t305ca-mode-tablette.desktop onboard-autostart.desktop "$config/autostart/"
systemctl --user daemon-reload
systemctl --user restart t305ca-mode-tablette.service
if [ "${1:-}" = --luminosite-auto ]; then
    systemctl --user enable t305ca-luminosite-auto.service
    systemctl --user restart t305ca-luminosite-auto.service
fi
