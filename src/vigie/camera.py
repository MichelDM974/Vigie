"""Lecture de la webcam dans un fil à part : on garde seulement la dernière image.

Sous Linux, un seul programme à la fois peut filmer : la pause ferme vraiment le
périphérique (voyant éteint), pour qu'une visio puisse le prendre.
"""

import threading
import time

import cv2
import numpy as np


class Camera:
    def __init__(self, source=0, largeur=640, hauteur=480, images_par_seconde=10):
        self.source = source
        self.largeur, self.hauteur = largeur, hauteur
        # Lire à 30 images/s coûte ~50 % d'un cœur rien qu'en conversion ; la posture
        # n'est analysée que 5 fois par seconde.
        self.images_par_seconde = images_par_seconde
        self.erreur = None
        self._image = None
        self._numero = 0
        self._verrou = threading.Lock()
        self._fil = None
        self._arret = threading.Event()

    def demarrer(self):
        if self._fil and self._fil.is_alive():
            return
        self._arret.clear()
        self._fil = threading.Thread(target=self._lire, name="camera", daemon=True)
        self._fil.start()

    def arreter(self):
        self._arret.set()
        if self._fil:
            self._fil.join(timeout=3)
        with self._verrou:
            self._image = None

    def derniere(self):
        """(numéro, image BGR) de la dernière image lue, ou None."""
        with self._verrou:
            return None if self._image is None else (self._numero, self._image)

    def _ouvrir(self):
        cap = cv2.VideoCapture(self.source, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.largeur)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.hauteur)
        cap.set(cv2.CAP_PROP_FPS, self.images_par_seconde)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _lire(self):
        while not self._arret.is_set():
            cap = self._ouvrir()
            if cap is None:
                self.erreur = "caméra introuvable ou utilisée par une autre application"
                self._arret.wait(5)
                continue
            self.erreur = None
            echecs = 0
            while not self._arret.is_set() and echecs < 30:
                ok, image = cap.read()
                if not ok:
                    echecs += 1
                    time.sleep(0.1)
                    continue
                echecs = 0
                with self._verrou:
                    self._image = image
                    self._numero += 1
            cap.release()
            with self._verrou:
                self._image = None
            if echecs:
                self.erreur = "la caméra ne renvoie plus d'images (débranchée ?)"


class CameraFactice:
    """Image grise sans personne : pour lancer le service sans toucher à la vraie caméra."""

    def __init__(self, largeur=640, hauteur=480):
        self.erreur = None
        self._image = np.full((hauteur, largeur, 3), 60, np.uint8)
        self._actif = False
        self._t0 = time.monotonic()

    def demarrer(self):
        self._actif = True

    def arreter(self):
        self._actif = False

    def derniere(self):
        if not self._actif:
            return None
        # Numéro qui avance comme une vraie caméra à 30 images/s.
        return int((time.monotonic() - self._t0) * 30), self._image
