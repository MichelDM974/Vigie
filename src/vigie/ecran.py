"""Messages à l'extension GNOME Shell de Vigie (voile d'assombrissement et icône d'état).

L'extension remet l'écran à la normale si elle n'a plus de nouvelles depuis quelques
secondes : un service planté ne laisse jamais l'écran sombre. D'où le battement régulier.
"""

import json
import subprocess
import time

DESTINATION = "org.gnome.Shell"
CHEMIN = "/io/github/micheldm974/Vigie"
INTERFACE = "io.github.micheldm974.Vigie"
DISPLAY_CONFIG = ("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                  "org.gnome.Mutter.DisplayConfig")
# Mise à true par GNOME après un plantage de GNOME Shell au démarrage
# (org.gnome.Shell-disable-extensions.service), et jamais remise à false par lui.
CLE_DESACTIVATION = "/org/gnome/shell/disable-user-extensions"


class Ecran:
    def __init__(self, battement=2.0, horloge=time.monotonic):
        self.battement = battement
        self.horloge = horloge
        self.disponible = None  # inconnu tant qu'aucun message n'est parti
        self.extensions_desactivees = None  # lu seulement quand l'extension se tait
        self._dernier = None
        self._dernier_envoi = float("-inf")

    def signaler(self, etat, niveaux):
        """Envoie l'état et l'opacité du voile de chaque écran (connecteur -> niveau, « * »
        pour les autres) s'ils ont changé, ou au moins à chaque battement."""
        maintenant = self.horloge()
        if (
            self._dernier
            and self._dernier[0] == etat
            and self._dernier[1].keys() == niveaux.keys()
            and all(abs(self._dernier[1][e] - n) < 0.02 for e, n in niveaux.items())
            and maintenant - self._dernier_envoi < self.battement
        ):
            return
        self._dernier = (etat, niveaux)
        self._dernier_envoi = maintenant
        self.disponible = self._envoyer(etat, niveaux)
        self.extensions_desactivees = None if self.disponible else self._lire_desactivation()

    def lister(self):
        """Écrans branchés, de gauche à droite : [{"connecteur": "DP-1", "nom": "Odyssey G5"}]."""
        commande = ["busctl", "--user", "--json=short", "call", *DISPLAY_CONFIG, "GetCurrentState"]
        try:
            sortie = subprocess.run(commande, capture_output=True, text=True, timeout=2)
            _serie, moniteurs, logiques, _proprietes = json.loads(sortie.stdout)["data"]
            modeles = {moniteur[0][0]: moniteur[0][2] for moniteur in moniteurs}
            # Écran logique : (x, y, échelle, rotation, principal, [(connecteur, …)], …).
            return [{"connecteur": branche[0], "nom": modeles.get(branche[0], branche[0])}
                    for logique in sorted(logiques, key=lambda l: (l[0], l[1]))
                    for branche in logique[5]]
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, TypeError):
            return []

    def _envoyer(self, etat, niveaux):
        dictionnaire = "{" + ", ".join(f"{e!r}: {n:.3f}" for e, n in niveaux.items()) + "}"
        commande = [
            "gdbus", "call", "--session", "--dest", DESTINATION, "--object-path", CHEMIN,
            "--method", f"{INTERFACE}.Signaler", repr(etat), dictionnaire,
        ]
        try:
            return subprocess.run(commande, capture_output=True, timeout=2).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _lire_desactivation(self):
        try:
            sortie = subprocess.run(["dconf", "read", CLE_DESACTIVATION],
                                    capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return sortie.stdout.strip() == "true"
