import pytest

from vigie import posture


def points_personne(cx=0.5, y_epaules=0.8, largeur=0.3, y_oreilles=0.5, y_nez=0.48,
                    ecart_yeux=0.08, pente=0.0, visibilite=0.99):
    """33 points façon MediaPipe (x, y, visibilité) d'une personne face caméra, image 4:3.

    Les x sont en fraction de largeur d'image : `largeur` et `ecart_yeux` sont convertis
    pour valoir ces distances en unités de hauteur d'image.
    """
    ratio = 4 / 3
    pts = [(0.5, 0.5, 0.0)] * 33
    demi = largeur / 2 / ratio
    pts[posture.EPAULE_G] = (cx + demi, y_epaules + pente / 2, visibilite)
    pts[posture.EPAULE_D] = (cx - demi, y_epaules - pente / 2, visibilite)
    pts[posture.OREILLE_G] = (cx + 0.1, y_oreilles, visibilite)
    pts[posture.OREILLE_D] = (cx - 0.1, y_oreilles, visibilite)
    pts[posture.OEIL_G] = (cx + ecart_yeux / 2 / ratio, y_nez - 0.04, visibilite)
    pts[posture.OEIL_D] = (cx - ecart_yeux / 2 / ratio, y_nez - 0.04, visibilite)
    pts[posture.NEZ] = (cx, y_nez, visibilite)
    return pts


def mesures_personne(**kw):
    return posture.mesurer(points_personne(**kw), 640, 480)


@pytest.fixture
def droit():
    return mesures_personne()
