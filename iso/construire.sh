#!/bin/bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo 'Usage : construire.sh ISO_OFFICIEL KIT_T305CA ISO_DE_SORTIE' >&2
    exit 2
fi
original=$(realpath -e -- "$1")
kit=$(realpath -e -- "$2")
destination=$(realpath -m -- "$3")
ici=$(dirname "$(realpath "$0")")
[[ ! -e "$destination" && -d "$(dirname "$destination")" ]] || {
    echo 'Choisis une nouvelle image dans un dossier existant.' >&2
    exit 1
}
hash_attendu=45a835b5dddaf40e84d776549e0b19b3fbd49673b6cc6434ebddbfcd217df776
printf '%s  %s\n' "$hash_attendu" "$original" | sha256sum --check --status || {
    echo 'L’image source ne correspond pas à la version Mint Xfce 22.3 prévue.' >&2
    exit 1
}
(cd "$kit"; sha256sum --check --quiet SHA256SUMS.txt)

outil=${XORRISO:-xorriso}
preparation=$(mktemp -d "$(dirname "$destination")/.t305ca-iso.XXXXXX")
trap 'find "$preparation" -depth -delete' EXIT
payload="$preparation/T305CA"
mkdir -p "$payload/paquets" "$payload/demarrage"
for fichier in restaurer-systeme.sh restaurer-session.sh correctifs-systeme.tar.gz correctifs-session.tar.gz; do
    install -m 644 "$kit/$fichier" "$payload/$fichier"
done
install -m 644 "$kit"/paquets/*.deb "$payload/paquets/"
install -m 644 "$ici/../demarrage/"* "$payload/demarrage/"
install -m 755 "$ici/installer-correctifs.sh" "$payload/"
install -m 644 "$ici/LIRE-MOI.txt" "$payload/"
(
    cd "$payload"
    find . -type f -print0 | sort -z | xargs -0 sha256sum > "$preparation/SHA256SUMS.txt"
)
install -m 644 "$preparation/SHA256SUMS.txt" "$payload/SHA256SUMS.txt"
"$outil" -indev "$original" -outdev "$preparation/resultat.iso" \
    -map "$payload" /T305CA -boot_image any replay -commit -end
"$outil" -indev "$preparation/resultat.iso" -ls /T305CA -- -end
mv -T --no-clobber "$preparation/resultat.iso" "$destination"
[[ ! -e "$preparation/resultat.iso" ]] || exit 1
sha256sum -- "$destination"
