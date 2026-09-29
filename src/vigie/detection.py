"""Points du corps par MediaPipe Pose (modèle téléchargé au premier lancement)."""

import logging
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

URL_MODELE = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_{nom}/float16/latest/pose_landmarker_{nom}.task"
)
log = logging.getLogger(__name__)


def chemin_modele(dossier, nom):
    chemin = dossier / f"pose_landmarker_{nom}.task"
    if not chemin.exists():
        dossier.mkdir(parents=True, exist_ok=True)
        log.info("Téléchargement du modèle de pose %s…", nom)
        partiel = chemin.with_suffix(".part")
        urllib.request.urlretrieve(URL_MODELE.format(nom=nom), partiel)
        partiel.rename(chemin)
    return chemin


class Detecteur:
    def __init__(self, dossier_modeles, nom="full"):
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(chemin_modele(dossier_modeles, nom))),
            running_mode=vision.RunningMode.VIDEO,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._dernier_ms = -1

    def detecter(self, image_bgr, maintenant):
        """Liste de (x, y, visibilité) des 33 points, ou None si personne n'est visible."""
        # Le mode vidéo exige des horodatages strictement croissants.
        ms = max(int(maintenant * 1000), self._dernier_ms + 1)
        self._dernier_ms = ms
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        resultat = self._landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms
        )
        if not resultat.pose_landmarks:
            return None
        return [(p.x, p.y, p.visibility) for p in resultat.pose_landmarks[0]]

    def fermer(self):
        self._landmarker.close()
