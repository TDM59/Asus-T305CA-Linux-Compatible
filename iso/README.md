# Support de réinstallation

Prépare une ISO officielle **Linux Mint 22.3 Xfce 64 bits** et le dossier de sauvegarde T305CA validé. La recette vérifie leurs sommes et ajoute le kit à l’ISO.

```sh
sudo apt install xorriso
bash iso/construire.sh linuxmint-22.3-xfce-64bit.iso /chemin/vers/le/kit T305CA-restauration.iso
```

Installe Mint normalement, puis suis le [guide du kit](LIRE-MOI.txt) depuis le système installé.
