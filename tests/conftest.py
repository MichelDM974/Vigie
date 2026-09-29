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


class HorlogeTest:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class CameraTest:
    def __init__(self):
        import numpy as np

        self.image = np.zeros((480, 640, 3), np.uint8)
        self.erreur = None
        self.actif = False
        self.numero = 0

    def demarrer(self):
        self.actif = True

    def arreter(self):
        self.actif = False

    def derniere(self):
        self.numero += 1
        return (self.numero, self.image) if self.actif else None


class DetecteurTest:
    def __init__(self):
        self.points = points_personne()

    def detecter(self, image, maintenant):
        return self.points


class EcranTest:
    disponible = True
    extensions_desactivees = None

    def __init__(self):
        self.appels = []
        self.ecrans = [{"connecteur": "HDMI-1", "nom": "S24D330"},
                       {"connecteur": "DP-1", "nom": "Odyssey G5"}]

    def signaler(self, etat, niveaux):
        self.appels.append((etat, niveaux))

    def lister(self):
        return self.ecrans


class Banc:
    """Moteur branché sur des doublures, qu'on fait avancer pas à pas."""

    def __init__(self, chemin_db):
        from vigie.moteur import Moteur
        from vigie.stockage import Stockage

        self.horloge = HorlogeTest()
        self.camera = CameraTest()
        self.detecteur = DetecteurTest()
        self.ecran = EcranTest()
        self.stockage = Stockage(chemin_db)
        self.moteur = Moteur(self.stockage, self.camera, self.detecteur, self.ecran, self.horloge)
        self.camera.demarrer()

    def avancer(self, secondes, dt=0.2):
        for _ in range(round(secondes / dt)):
            self.horloge.t += dt
            self.moteur.etape()
        return self.moteur.instantane()

    def calibrer(self, nom="droit"):
        self.moteur.enregistrer(nom)
        self.avancer(6.2)


@pytest.fixture
def banc(tmp_path):
    return Banc(tmp_path / "vigie.db")
