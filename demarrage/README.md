# Correctifs de démarrage

Sur le T305CA avec Mint Xfce, installe les services système puis le lanceur d’alerte.

```sh
sudo apt install usbutils zenity
sudo bash demarrage/installer.sh
install -Dm644 demarrage/t305ca-alerte-materiel.desktop \
  "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/t305ca-alerte-materiel.desktop"
```

Le contrôle se lance avant LightDM. Un clavier détaché est normal. Les caméras et le capteur de lumière nécessitent leurs pilotes. Pour lire le bilan après démarrage, le compte doit pouvoir lire le journal système (groupe `adm` sur Mint).

```sh
journalctl -b -u asus-t305ca-verifier-materiel.service
```

Pour masquer GRUB si Mint démarre déjà sur l’entrée `t305ca-ov13850-7`, lance `sudo bash demarrage/masquer-grub.sh`.
