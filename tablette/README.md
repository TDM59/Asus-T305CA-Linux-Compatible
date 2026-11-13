# Mode tablette ASUS T305CA

Pour Linux Mint 22.3 Xfce sous X11. Le mode s’active quand le clavier ASUS est détaché. Il gère la rotation de l’écran et du tactile, l’accueil, les applications par catégorie et le clavier virtuel.

## Installation

Depuis la racine du dépôt, dans la session Xfce du T305CA.

```sh
sudo apt install python3-gi python3-gi-cairo python3-pyudev gir1.2-gtk-3.0 gir1.2-wnck-3.0 onboard iio-sensor-proxy xinput x11-xserver-utils xfconf network-manager bluez pulseaudio-utils power-profiles-daemon
bash tablette/installer.sh
gsettings set org.gnome.desktop.interface toolkit-accessibility true
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

## Réglages rapides

Le panneau propose trois colonnes quand l’écran est assez large. Tu peux modifier les six favoris de l’accueil, verrouiller la rotation ou passer en Économie. Le mode Lecture fixe l’écran en portrait et adoucit l’éclairage. Le mode Dessin garde le stylet actif et ignore la paume. Le menu des applications inclut une recherche.

## Noyau et mises à jour

- **7.0.0-42-generic** est la version validée pour les deux caméras. Garde son entrée ASUS dans GRUB et ses paquets installés si tu testes un autre noyau.
- **7.0.0-43-generic** est prêt pour un essai du capteur de lumière. Le pilote compile et ses dépendances sont reconnues. Les deux caméras et leurs voyants restent à valider avec la chaîne complète sur ce noyau.
- Le fichier `t305ca-zswap.conf` correspond à la configuration qui réactive zswap au démarrage. Pour l’appliquer sur un système dont le noyau expose zswap, copie-le dans `/etc/tmpfiles.d/` puis exécute `sudo systemd-tmpfiles --create /etc/tmpfiles.d/t305ca-zswap.conf`.

Les sources du capteur sont dans [capteur](capteur/). Pour le compiler pour un noyau donné, installe les en-têtes correspondants puis utilise `make -C /lib/modules/VERSION/build M="$PWD/tablette/capteur" modules` depuis la racine du dépôt, en remplaçant `VERSION` par la version exacte.

Les fichiers dans [cameras](cameras/) complètent le kit ASUS. Le service utilisateur attend le module v4l2loopback, les périphériques vidéo 60 et 61, ainsi que la version ASUS de libcamera, ses profils et son plugin GStreamer installés par le kit. Le service fournit les flux orientés avec correction de lumière sur la caméra avant. Ces fichiers seuls ne suffisent pas à faire fonctionner les capteurs sur une installation neuve.
