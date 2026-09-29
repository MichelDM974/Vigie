#!/usr/bin/env bash
# Installe (ou met à jour) Vigie pour l'utilisateur courant : environnement Python,
# extension GNOME Shell, service systemd lancé à chaque ouverture de session.
# Relançable sans risque après une mise à jour du code.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UUID="vigie@micheldm974.github.io"
EXTENSION="$HOME/.local/share/gnome-shell/extensions/$UUID"
UNITE="$HOME/.config/systemd/user/vigie.service"

echo "1/4 Environnement Python"
[ -x "$RACINE/.venv/bin/python" ] || python3.14 -m venv "$RACINE/.venv"
"$RACINE/.venv/bin/pip" install -q -r "$RACINE/requirements.txt" -c "$RACINE/constraints.txt"

echo "2/4 Extension GNOME Shell"
mkdir -p "$(dirname "$EXTENSION")"
rm -rf "${EXTENSION:?}"
cp -r "$RACINE/gnome-extension/$UUID" "$EXTENSION"
# dconf plutôt que gsettings : lancé depuis le terminal de VS Code (snap), gsettings
# prend les schémas et modules GIO du snap, et peut échouer ou n'écrire nulle part.
activees="$(python3 - "$(dconf read /org/gnome/shell/enabled-extensions)" "$UUID" <<'EOF'
import ast, sys
texte, uuid = sys.argv[1].removeprefix("@as").strip(), sys.argv[2]
liste = ast.literal_eval(texte) if texte else []
if uuid not in liste:
    liste.append(uuid)
print("[" + ", ".join(repr(x) for x in liste) + "]")
EOF
)"
dconf write /org/gnome/shell/enabled-extensions "$activees"

echo "3/4 Service systemd utilisateur"
mkdir -p "$(dirname "$UNITE")"
cat > "$UNITE" <<EOF
# Généré par scripts/installer.sh : modifier le script, pas ce fichier.
[Unit]
Description=Vigie : surveillance de la posture par la webcam
After=graphical-session.target
PartOf=graphical-session.target

[Service]
WorkingDirectory=$RACINE
Environment="PYTHONPATH=$RACINE/src"
ExecStart="$RACINE/.venv/bin/python" -m vigie serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
EOF
systemctl --user daemon-reload
systemctl --user enable vigie.service
systemctl --user restart vigie.service

echo "4/4 Vérification"
for _ in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8030/api/etat > /dev/null; then
        echo
        echo "Vigie tourne : http://127.0.0.1:8030 (enregistre-y tes postures de référence)."
        echo "Première installation de l'extension : ferme puis rouvre ta session une fois,"
        echo "GNOME ne charge une nouvelle extension qu'à l'ouverture de session sous Wayland."
        exit 0
    fi
    sleep 1
done
echo "Le service ne répond pas : journalctl --user -u vigie.service -n 50" >&2
exit 1
