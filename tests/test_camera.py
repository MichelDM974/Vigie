import numpy as np
import pytest

from vigie import camera as module_camera
from vigie.camera import Camera


class CapTest:
    """VideoCapture factice : chaque saisie avance une horloge factice de 0,2 s (~5 images/s,
    comme la vraie caméra) ; `apres(n, action)` agit sur la caméra à la n-ième saisie."""

    def __init__(self, camera, saisies, decodage_ok=True):
        self.camera, self.max, self.decodage_ok = camera, saisies, decodage_ok
        self.t = 0.0
        self.saisies, self.decodees = 0, []
        self.actions = {}
        self.ouvertures = 0

    def grab(self):
        self.saisies += 1
        self.t += 0.2
        if action := self.actions.get(self.saisies):
            action()
        if self.saisies >= self.max:
            self.camera._arret.set()
        return True

    def retrieve(self):
        if not self.decodage_ok:
            return False, None
        self.decodees.append(self.saisies)
        return True, np.zeros((4, 4, 3), np.uint8)

    def release(self):
        pass


@pytest.fixture
def lire(monkeypatch):
    def lancer(camera, cap):
        monkeypatch.setattr(module_camera.time, "monotonic", lambda: cap.t)
        monkeypatch.setattr(module_camera.time, "sleep", lambda s: None)
        def ouvrir():
            cap.ouvertures += 1
            return cap

        camera._ouvrir = ouvrir
        camera._lire()  # dans ce fil-ci : déterministe
    return lancer


def test_decode_chaque_image_sans_limite(lire):
    camera = Camera()
    cap = CapTest(camera, 20)
    lire(camera, cap)
    assert cap.decodees == list(range(1, 21))


def test_limite_ne_decode_que_la_cadence_demandee(lire):
    camera = Camera()
    camera.limiter(2)  # au plus une image par 0,5 s : une saisie sur trois à 0,2 s
    cap = CapTest(camera, 30)
    lire(camera, cap)
    assert cap.saisies == 30  # le flux est toujours vidé : l'image reste fraîche
    assert cap.decodees == list(range(1, 31, 3))


def test_limite_levee_en_pleine_lecture_redecode_tout(lire):
    camera = Camera()
    camera.limiter(1)
    cap = CapTest(camera, 20)
    cap.actions[10] = lambda: camera.limiter(None)
    lire(camera, cap)
    assert cap.decodees[:2] == [1, 6]
    assert cap.decodees[2:] == list(range(10, 21))  # dès la saisie qui suit la levée


def test_decodage_toujours_en_echec_rouvre_la_camera(lire):
    camera = Camera()
    cap = CapTest(camera, 35, decodage_ok=False)
    lire(camera, cap)
    assert cap.ouvertures == 2  # 30 échecs d'affilée : périphérique relâché puis rouvert
    assert camera.erreur and "plus d'images" in camera.erreur
