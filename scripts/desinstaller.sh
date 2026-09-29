#!/usr/bin/env bash
# Retire le service et l'extension. Garde data/ (postures, bilans) et l'environnement Python.
set -euo pipefail

UUID="vigie@micheldm974.github.io"
UNITE="$HOME/.config/systemd/user/vigie.service"

systemctl --user disable --now vigie.service 2>/dev/null || true
rm -f "$UNITE"
systemctl --user daemon-reload

activees="$(python3 - "$(dconf read /org/gnome/shell/enabled-extensions)" "$UUID" <<'EOF'
import ast, sys
texte, uuid = sys.argv[1].removeprefix("@as").strip(), sys.argv[2]
liste = [x for x in (ast.literal_eval(texte) if texte else []) if x != uuid]
print("[" + ", ".join(repr(x) for x in liste) + "]")
EOF
)"
dconf write /org/gnome/shell/enabled-extensions "$activees"
rm -rf "${HOME:?}/.local/share/gnome-shell/extensions/$UUID"
echo "Vigie désinstallé (données conservées dans data/). L'icône disparaît à la prochaine session."
