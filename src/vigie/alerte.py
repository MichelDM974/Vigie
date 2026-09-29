"""Quand et combien assombrir l'écran, d'après la suite des états de posture."""

from dataclasses import dataclass


@dataclass
class ReglagesAlerte:
    delai: float = 10.0  # secondes de mauvaise posture avant d'assombrir
    rampe: float = 3.0  # secondes pour passer d'un écran normal à l'assombrissement maximal


class Alerte:
    """Compte le temps passé avachi et en déduit le niveau d'assombrissement, de 0 (rien) à
    1 (assombrissement maximal, propre à chaque écran).

    Un bref redressement ne remet pas le compte à zéro (il décroît deux fois plus vite
    qu'il ne monte) : se redresser une seconde pour repartir aussitôt ne suffit pas.
    En revanche l'écran s'éclaircit dès que la posture redevient bonne.
    """

    def __init__(self, reglages=None):
        self.reglages = reglages or ReglagesAlerte()
        self.mauvais = 0.0
        self.niveau = 0.0

    def avancer(self, etat, dt):
        r = self.reglages
        if etat == "avachi":
            self.mauvais += dt
        elif etat == "ok":
            # Plafonné au délai : après un redressement, une rechute ré-assombrit plus vite
            # qu'au premier avertissement, mais pas instantanément.
            self.mauvais = max(0.0, min(self.mauvais, r.delai) - 2 * dt)
        elif etat != "incertain":  # absent, en pause, sans référence, sans caméra
            self.mauvais = 0.0

        if etat == "avachi" and self.mauvais > r.delai:
            progression = (self.mauvais - r.delai) / r.rampe if r.rampe > 0 else 1.0
            self.niveau = min(1.0, progression)
        elif etat != "incertain":  # une main devant le visage ne rallume pas l'écran
            self.niveau = 0.0
        return self.niveau
