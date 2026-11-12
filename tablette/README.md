# Mode tablette ASUS T305CA

Pour Linux Mint 22.3 Xfce sous X11. Le mode s’active quand le clavier ASUS est détaché. Il gère la rotation de l’écran et du tactile, l’accueil, les applications par catégorie et le clavier virtuel.

## Installation

Depuis la racine du dépôt, dans la session Xfce du T305CA.

```sh
sudo apt install python3-gi python3-gi-cairo python3-pyudev gir1.2-gtk-3.0 gir1.2-wnck-3.0 onboard iio-sensor-proxy xinput x11-xserver-utils xfconf network-manager bluez pulseaudio-utils
bash tablette/installer.sh
gsettings set org.gnome.desktop.interface toolkit-accessibility true
gsettings set org.onboard.auto-show enabled true
gsettings set org.onboard.window docking-enabled true
gsettings set org.onboard.window docking-shrink-workarea true
gsettings set org.onboard.auto-show reposition-method-docked none
```

Si le pilote `t305ca_als` est déjà installé et fournit une mesure en lux, lance `bash tablette/installer.sh --luminosite-auto` pour activer la luminosité progressive. Les raccourcis caméra, Dessin et Lumière nocturne utilisent leurs composants déjà installés.

## Gestes

- Glisse depuis le haut pour ouvrir les réglages rapides. Ils affichent le réseau Wi-Fi et les appareils Bluetooth connectés.
- Glisse vers le haut depuis le centre du bord inférieur pour afficher Fenêtres, Accueil et Retour.
- Rattache le clavier pour retrouver le bureau Xfce et sa barre des tâches.

```sh
journalctl --user -b -u t305ca-mode-tablette.service
journalctl --user -b -u t305ca-luminosite-auto.service
```
