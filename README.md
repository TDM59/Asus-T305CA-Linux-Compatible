# ASUS Transformer 3 T305CA sous Linux Mint

## Correctifs de démarrage

Le dossier [demarrage](demarrage/) contient la récupération du clavier détachable, l’extinction de son rétroéclairage à l’arrêt complet, un contrôle matériel avant LightDM et une alerte à l’ouverture de session. Le menu GRUB peut être masqué séparément.

Ces réglages ont été utilisés sur un ASUS T305CA avec Linux Mint 22.3 Xfce et le noyau 7.0.0-42-generic. Le contrôle détecte notamment les interfaces du clavier, le tactile, le stylet, les capteurs, l’audio, les caméras et les contrôleurs réseau. Un clavier détaché est traité comme un état normal. La détection des caméras utilise les pilotes et la version de libcamera déjà installés sur la machine. Sur un Mint neuf, les caméras et le capteur de lumière peuvent être signalés tant que leurs pilotes ne sont pas installés.

### Réinstallation

Depuis le dossier du dépôt, sur le T305CA, installe `usbutils` et `zenity` si ces paquets sont absents. Installe ensuite les services système et ajoute le lanceur à la session Xfce.

```sh
sudo apt install usbutils zenity
sudo bash demarrage/installer.sh
install -Dm644 demarrage/t305ca-alerte-materiel.desktop \
  "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/t305ca-alerte-materiel.desktop"
```

L’alerte doit pouvoir lire le journal système. Sur le compte administrateur Mint, l’accès est généralement fourni par le groupe `adm`. Le contrôle affiche une alerte distincte si le journal n’a pas produit de bilan complet.

Après un redémarrage, consulte les résultats avec ces commandes.

```sh
journalctl -b -u asus-t305ca-verifier-materiel.service
journalctl -b -t t305ca-alerte-materiel
```

Le contrôle matériel vérifie la détection et l’initialisation. Les essais d’usage comme l’écoute du son, la lecture d’empreinte ou la capture d’une image se font en session.

### Menu GRUB masqué

Le script suivant s’applique si l’installation démarre déjà sur l’entrée personnalisée `t305ca-ov13850-7`. Cette entrée et ses pilotes sont des prérequis de ce réglage. Le script vérifie la configuration générée et conserve une copie de l’ancienne dans `/var/backups`. **Échap** permet d’ouvrir le menu pendant les deux secondes de démarrage masqué.

```sh
sudo bash demarrage/masquer-grub.sh
```

## Construire le support de réinstallation

Le dossier [iso](iso/) permet d’ajouter le kit ASUS à une image d’installation officielle de Linux Mint 22.3 Xfce. Cette reconstruction est destinée à un usage local et requiert l’image Mint vérifiée ainsi que le dossier de sauvegarde T305CA validé, avec ses archives, ses scripts et ses paquets. Le dépôt contient la recette de construction.

```sh
sudo apt install xorriso
bash iso/construire.sh linuxmint-22.3-xfce-64bit.iso \
  /chemin/vers/le/kit-valide T305CA-restauration.iso
```

Le script vérifie la somme SHA-256 de l’ISO source et les sommes du kit. Il préserve l’amorçage de l’image officielle et y ajoute le dossier `T305CA`. Après l’installation standard de Mint, suivre `T305CA/LIRE-MOI.txt` pour appliquer les correctifs. L’application à un T305CA physique se vérifie ensuite sur le matériel.
