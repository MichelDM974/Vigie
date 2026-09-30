"""Mesures de posture tirées des points du corps, et comparaison aux postures de référence.

La caméra est face à l'utilisateur : on ne voit pas la courbure du dos, seulement ses
conséquences (tête qui descend, qui avance, buste qui se rapproche de l'écran, épaules de
travers). Chaque signal est un rapport sans unité, pour ne pas dépendre de la résolution.
"""

import math
import statistics
from dataclasses import dataclass

# Indices des points de MediaPipe Pose utilisés.
NEZ, OEIL_G, OEIL_D, OREILLE_G, OREILLE_D, EPAULE_G, EPAULE_D = 0, 3, 6, 7, 8, 11, 12
POINTS_REQUIS = (NEZ, OEIL_G, OEIL_D, OREILLE_G, OREILLE_D, EPAULE_G, EPAULE_D)
VISIBILITE_MIN = 0.5


@dataclass(frozen=True)
class Signal:
    libelle: str
    tolerance: float  # écart à la référence jugé significatif (tolérance réglée à 1)
    sens: int  # +1 : seule une hausse est mauvaise, -1 : seule une baisse, 0 : les deux
    cause: str  # affiché quand ce signal est celui qui dépasse le plus


# Tolérances calées le 29/09/2026 sur une séance réelle (2 min 30 de travail normal, puis
# affaissé, tête en avant, penché sur le côté, tête baissée) : juste au-dessus du pire
# écart en posture correcte. La hauteur est le seul signal sans marge nette (0.083 au
# pire en posture correcte, 0.085 affaissé la tête relevée) : 0.075 privilégie la détection.
# Tête et nez resserrés le 30/09/2026 (0.12 → 0.07, 0.20 → 0.14) : de face, la tête qui
# avance ne s'approche que de 2 à 3 cm, elle se voit surtout parce qu'elle descend vers les
# épaules (« visage » ne bouge presque pas). Tête légèrement avancée ≈ 0.056 sur « tete » ;
# 80 % détectée sur un relevé étiqueté, au prix de fausses alertes possibles en baissant
# les yeux (clavier, téléphone), à juger par les fausses alertes signalées.
SIGNAUX = {
    "tete": Signal("Tête au-dessus des épaules", 0.07, -1, "tête en avant ou qui s'enfonce"),
    "nez": Signal("Nez au-dessus des épaules", 0.14, -1, "tête penchée vers le bas"),
    "hauteur": Signal("Hauteur dans l'image", 0.075, +1, "affaissé sur la chaise"),
    "proximite": Signal("Proximité de l'écran", 0.12, +1, "trop près de l'écran"),
    "visage": Signal("Tête en avant du buste", 0.06, +1, "tête en avant"),
    "epaules": Signal("Inclinaison des épaules", 12.0, 0, "penché sur le côté"),
}


@dataclass(frozen=True)
class Evaluation:
    etat: str  # "ok" ou "avachi"
    ecart: float  # plus grand écart normalisé à la référence la plus proche (> 1 : avachi)
    signal: str | None  # signal qui dépasse le plus, si avachi
    cause: str | None
    reference: int | None  # id de la référence la plus proche
    ecarts: dict[str, float]  # écart normalisé de chaque signal à cette référence


def mesurer(points, largeur, hauteur):
    """Signaux d'une image, ou None si un point nécessaire est masqué ou hors champ.

    `points` : suite de (x, y, visibilite), x et y normalisés sur [0, 1] comme MediaPipe.
    """
    for i in POINTS_REQUIS:
        x, y, vis = points[i]
        if vis < VISIBILITE_MIN or not (0 <= x <= 1 and 0 <= y <= 1):
            return None
    ratio = largeur / hauteur

    def pt(i):  # en unités de hauteur d'image, pour que les distances soient isotropes
        return points[i][0] * ratio, points[i][1]

    eg, ed = pt(EPAULE_G), pt(EPAULE_D)
    largeur_epaules = math.dist(eg, ed)
    if largeur_epaules < 1e-3:
        return None
    y_epaules = (eg[1] + ed[1]) / 2
    y_oreilles = (pt(OREILLE_G)[1] + pt(OREILLE_D)[1]) / 2
    # Épaule gauche de la personne = côté droit de l'image : on oriente l'angle de sorte
    # qu'une personne droite donne ~0°, quel que soit l'ordre des points.
    gauche, droite = sorted((eg, ed))
    angle = math.degrees(math.atan2(droite[1] - gauche[1], droite[0] - gauche[0]))
    return {
        "tete": (y_epaules - y_oreilles) / largeur_epaules,
        "nez": (y_epaules - pt(NEZ)[1]) / largeur_epaules,
        "hauteur": y_oreilles,
        "proximite": math.log(largeur_epaules),
        "visage": math.dist(pt(OEIL_G), pt(OEIL_D)) / largeur_epaules,
        "epaules": angle,
    }


def lisser(historique):
    """Médiane signal par signal : une image aberrante ne fait pas basculer l'état."""
    return {nom: statistics.median(m[nom] for m in historique) for nom in historique[0]}


def ecarts(mesures, reference, facteur=1.0):
    """Écart normalisé de chaque signal ; seuls comptent les écarts dans le mauvais sens."""
    resultat = {}
    for nom, signal in SIGNAUX.items():
        delta = mesures[nom] - reference[nom]
        if signal.sens:
            delta = max(0.0, signal.sens * delta)
        resultat[nom] = abs(delta) / (signal.tolerance * facteur)
    return resultat


def evaluer(mesures, references, facteur=1.0):
    """Compare aux postures de référence (dict id -> mesures) : la plus proche fait foi.

    `facteur` élargit (> 1) ou resserre (< 1) toutes les tolérances à la fois.
    """
    meilleure = None
    for ref_id, reference in references.items():
        detail = ecarts(mesures, reference, facteur)
        pire = max(detail.values())
        if meilleure is None or pire < meilleure[1]:
            meilleure = (ref_id, pire, detail)
    ref_id, pire, detail = meilleure
    avachi = pire > 1.0
    signal = max(detail, key=detail.get) if avachi else None
    cause = SIGNAUX[signal].cause if avachi else None
    return Evaluation("avachi" if avachi else "ok", pire, signal, cause, ref_id, detail)
