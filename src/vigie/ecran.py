"""Messages à l'extension GNOME Shell de Vigie (voile d'assombrissement et icône d'état).

L'extension remet l'écran à la normale si elle n'a plus de nouvelles depuis quelques
secondes : un service planté ne laisse jamais l'écran sombre. D'où le battement régulier.
"""

import subprocess
import time

DESTINATION = "org.gnome.Shell"
CHEMIN = "/io/github/micheldm974/Vigie"
INTERFACE = "io.github.micheldm974.Vigie"


class Ecran:
    def __init__(self, battement=2.0, horloge=time.monotonic):
        self.battement = battement
        self.horloge = horloge
        self.disponible = None  # inconnu tant qu'aucun message n'est parti
        self._dernier = None
        self._dernier_envoi = float("-inf")

    def signaler(self, etat, niveau):
        """Envoie l'état et le niveau s'ils ont changé, ou au moins à chaque battement."""
        maintenant = self.horloge()
        if (
            self._dernier
            and self._dernier[0] == etat
            and abs(self._dernier[1] - niveau) < 0.02
            and maintenant - self._dernier_envoi < self.battement
        ):
            return
        self._dernier = (etat, niveau)
        self._dernier_envoi = maintenant
        self.disponible = self._envoyer(etat, niveau)

    def _envoyer(self, etat, niveau):
        commande = [
            "gdbus", "call", "--session", "--dest", DESTINATION, "--object-path", CHEMIN,
            "--method", f"{INTERFACE}.Signaler", repr(etat), f"{niveau:.3f}",
        ]
        try:
            return subprocess.run(commande, capture_output=True, timeout=2).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
