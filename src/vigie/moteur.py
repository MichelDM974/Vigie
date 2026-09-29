"""Boucle principale : image → points du corps → posture → assombrissement de l'écran."""

import collections
import contextlib
import logging
import threading
import time
from datetime import datetime

import cv2

from . import posture
from .alerte import Alerte, ReglagesAlerte

FREQUENCE = 5  # analyses par seconde : assez pour une posture, léger pour le processeur
DUREE_PREPARATION = 3.0  # compte à rebours avant d'enregistrer une posture
DUREE_CAPTURE = 3.0
MESURES_MIN = 5  # images exploitables exigées pendant la capture
ETATS_COMPTES = ("ok", "avachi", "absent", "pause")  # temps cumulés pour le bilan
# Une fausse alerte signalée juste après s'être redressé (par réflexe, le temps d'atteindre
# le menu) vise encore le dernier moment jugé avachi.
SOUVENIR_AVACHI = 10.0

COULEURS = {"ok": (12, 163, 12), "avachi": (103, 103, 230)}  # BGR : --good, --danger
GRIS = (170, 170, 170)
SEGMENTS = [
    (posture.EPAULE_G, posture.EPAULE_D),
    (posture.OREILLE_G, posture.OREILLE_D),
    (posture.OEIL_G, posture.OEIL_D),
]
log = logging.getLogger(__name__)


class Moteur:
    def __init__(self, stockage, camera, detecteur, ecran, horloge=time.monotonic):
        self.stockage = stockage
        self.camera = camera
        self.detecteur = detecteur
        self.ecran = ecran
        self.horloge = horloge
        self.alerte = Alerte()
        self._verrou = threading.Lock()
        self._arret = threading.Event()
        self._fil = None
        self._pause = False
        self._historique = collections.deque(maxlen=FREQUENCE)  # ~1 s de mesures
        self._enregistrement = None
        self._dernier_enregistrement = None
        self._test_jusqua = float("-inf")
        self._fausse_alerte = False  # voile retenu jusqu'au prochain redressement
        self._dernier_avachi = None  # (instant, état) du dernier moment jugé avachi
        self._precedent = None
        self._apercu = None  # (numéro, JPEG)
        self._spectateurs = 0
        self._cumuls = collections.Counter()
        self._causes = collections.Counter()  # temps avachi par (minute, signal en cause)
        self._dernier_vidage = horloge()
        self._etat = {"etat": "demarrage"}
        self.recharger()

    # --- Commandes (appelées depuis le serveur web) ---

    def recharger(self):
        """Relit postures et réglages après une modification."""
        references = {p["id"]: p["mesures"] for p in self.stockage.postures()}
        reglages = self.stockage.reglages()
        with self._verrou:
            self._references = references
            self._facteur = reglages["tolerance"]
            self.alerte.reglages = ReglagesAlerte(delai=reglages["delai"], rampe=reglages["rampe"])
            # Opacité maximale du voile par écran, « * » pour ceux sans réglage propre.
            self._maxima = {"*": reglages["niveau_max"]} | reglages["ecrans"]

    def mettre_en_pause(self, pause):
        with self._verrou:
            self._pause = pause
            if pause:
                self._enregistrement = None
                self._apercu = None
        # Fermer le périphérique pour de bon : une visio peut alors prendre la caméra.
        if pause:
            self.camera.arreter()
        else:
            self.camera.demarrer()

    def en_pause(self):
        with self._verrou:
            return self._pause

    def enregistrer(self, nom):
        """Lance l'enregistrement d'une posture de référence (compte à rebours puis capture)."""
        with self._verrou:
            if self._pause:
                raise ValueError("Vigie est en pause : reprends la surveillance d'abord.")
            if self._enregistrement:
                raise ValueError("Un enregistrement est déjà en cours.")
            debut = self.horloge() + DUREE_PREPARATION
            self._enregistrement = {
                "nom": nom, "debut": debut, "fin": debut + DUREE_CAPTURE, "mesures": [],
            }
            self._dernier_enregistrement = None

    def tester_assombrissement(self, duree=3.0):
        with self._verrou:
            self._test_jusqua = self.horloge() + duree

    def signaler_fausse_alerte(self):
        """L'utilisateur se dit droit alors que Vigie le juge avachi : on note la posture du
        moment (pour recaler les tolérances) et on n'assombrit plus avant son redressement."""
        with self._verrou:
            dernier = self._dernier_avachi
            if dernier is None or self.horloge() - dernier[0] > SOUVENIR_AVACHI:
                raise ValueError("Rien à signaler : tu n'es pas compté avachi en ce moment.")
            deja, self._fausse_alerte = self._fausse_alerte, True
        etat = dernier[1]
        if not deja:
            self.stockage.ajouter_fausse_alerte(etat["reference"], etat["signal"], etat["niveau"],
                                                etat["mesures"], etat["ecarts"])
        return {"cause": etat["cause"]}

    def instantane(self):
        with self._verrou:
            return dict(self._etat)

    def apercu(self):
        with self._verrou:
            return self._apercu

    @contextlib.contextmanager
    def spectateur(self):
        """Tant qu'une page affiche l'aperçu, on dessine et encode les images (sinon non)."""
        with self._verrou:
            self._spectateurs += 1
        try:
            yield
        finally:
            with self._verrou:
                self._spectateurs -= 1

    def bilan(self, jour=None):
        """Secondes passées dans chaque état ce jour-là, y compris la minute pas encore écrite,
        sous "causes" le temps avachi par signal en cause, et le nombre de fausses alertes."""
        jour = jour or datetime.now().strftime("%Y-%m-%d")
        bilan = collections.Counter(self.stockage.bilan(jour))
        causes = collections.Counter(self.stockage.causes(jour))
        with self._verrou:
            for (minute, etat), secondes in self._cumuls.items():
                if minute.startswith(jour):
                    bilan[etat] += secondes
            for (minute, signal), secondes in self._causes.items():
                if minute.startswith(jour):
                    causes[signal] += secondes
        return dict(bilan, causes=dict(causes),
                    fausses_alertes=len(self.stockage.fausses_alertes(jour)))

    # --- Boucle ---

    def demarrer(self):
        if not self.en_pause():
            self.camera.demarrer()
        self._arret.clear()
        self._fil = threading.Thread(target=self._boucle, name="moteur", daemon=True)
        self._fil.start()

    def arreter(self):
        self._arret.set()
        if self._fil:
            self._fil.join(timeout=5)
        self.camera.arreter()
        self._vider_cumuls()
        self.ecran.signaler("arret", {"*": 0.0})

    def _boucle(self):
        periode = 1 / FREQUENCE
        while not self._arret.is_set():
            debut = time.monotonic()
            try:
                self.etape()
            except Exception:
                log.exception("Étape d'analyse en échec")
            self._arret.wait(max(0.0, periode - (time.monotonic() - debut)))

    def etape(self):
        maintenant = self.horloge()
        dt = 0.0 if self._precedent is None else min(maintenant - self._precedent, 1.0)
        self._precedent = maintenant
        with self._verrou:
            pause, references, facteur = self._pause, self._references, self._facteur
            enregistrement, spectateurs = self._enregistrement, self._spectateurs

        image = points = mesures = evaluation = None
        if pause:
            etat = "pause"
        elif (lue := self.camera.derniere()) is None:
            etat = "sans_camera"
        else:
            image = lue[1]
            points = self.detecteur.detecter(image, maintenant)
            brutes = None if points is None else posture.mesurer(points, image.shape[1], image.shape[0])
            if points is None:
                etat = "absent"
                self._historique.clear()
            elif brutes is None:
                etat = "incertain"
            else:
                self._historique.append(brutes)
                mesures = posture.lisser(self._historique)
                if enregistrement and maintenant >= enregistrement["debut"]:
                    enregistrement["mesures"].append(brutes)
                if references:
                    evaluation = posture.evaluer(mesures, references, facteur)
                    etat = evaluation.etat
                else:
                    etat = "non_calibre"

        suivi = self._suivre_enregistrement(enregistrement, maintenant) if enregistrement else None
        with self._verrou:
            if etat == "ok":
                self._fausse_alerte = False
            fausse_alerte = self._fausse_alerte
        # Pendant un enregistrement on pose devant la caméra : pas question d'assombrir.
        niveau = self.alerte.avancer("pause" if suivi or fausse_alerte else etat, dt)
        with self._verrou:
            if maintenant < self._test_jusqua:
                niveau = 1.0
            maxima = self._maxima
        self.ecran.signaler(etat, {ecran: niveau * maximum for ecran, maximum in maxima.items()})
        self._compter(etat, evaluation.signal if evaluation else None, dt, maintenant)
        if image is not None and spectateurs:
            self._dessiner(image, points, etat)

        with self._verrou:
            self._etat = {
                "etat": etat,
                "signal": evaluation.signal if evaluation else None,
                "cause": evaluation.cause if evaluation else None,
                "ecart": evaluation.ecart if evaluation else None,
                "ecarts": evaluation.ecarts if evaluation else None,
                "reference": evaluation.reference if evaluation else None,
                "mesures": mesures,
                "niveau": niveau,  # de 0 à 1 : part de l'assombrissement maximal de chaque écran
                "pause": pause,
                "camera_erreur": None if pause else self.camera.erreur,
                "extension": self.ecran.disponible,
                "extensions_desactivees": self.ecran.extensions_desactivees,
                "enregistrement": suivi,
                "dernier_enregistrement": self._dernier_enregistrement,
                "fausse_alerte": fausse_alerte,
            }
            if etat == "avachi":
                self._dernier_avachi = (maintenant, self._etat)

    def _suivre_enregistrement(self, enregistrement, maintenant):
        """Phase de l'enregistrement en cours, ou None une fois terminé (et sauvegardé)."""
        if maintenant < enregistrement["debut"]:
            return {"nom": enregistrement["nom"], "phase": "preparation",
                    "restant": enregistrement["debut"] - maintenant}
        if maintenant < enregistrement["fin"]:
            return {"nom": enregistrement["nom"], "phase": "capture",
                    "restant": enregistrement["fin"] - maintenant}
        nom, captees = enregistrement["nom"], enregistrement["mesures"]
        if len(captees) >= MESURES_MIN:
            self.stockage.ajouter_posture(nom, posture.lisser(captees))
            resultat = {"ok": True, "message": f"Posture « {nom} » enregistrée."}
        else:
            resultat = {"ok": False, "message": "Tu n'as pas été assez bien vu pendant la "
                        "capture : recommence, tête et épaules dans le cadre."}
        with self._verrou:
            self._enregistrement = None
            self._dernier_enregistrement = resultat
        self.recharger()
        return None

    def _compter(self, etat, signal, dt, maintenant):
        if etat in ETATS_COMPTES and dt:
            minute = datetime.now().strftime("%Y-%m-%dT%H:%M")
            with self._verrou:
                self._cumuls[(minute, etat)] += dt
                if signal:
                    self._causes[(minute, signal)] += dt
        if maintenant - self._dernier_vidage >= 60:
            self._vider_cumuls()
            self._dernier_vidage = maintenant

    def _vider_cumuls(self):
        with self._verrou:
            cumuls, self._cumuls = self._cumuls, collections.Counter()
            causes, self._causes = self._causes, collections.Counter()
        if cumuls:
            self.stockage.ajouter_temps(cumuls, causes)

    def _dessiner(self, image, points, etat):
        image = image.copy()
        if points:
            h, w = image.shape[:2]
            couleur = COULEURS.get(etat, GRIS)
            xy = {i: (round(points[i][0] * w), round(points[i][1] * h)) for i in posture.POINTS_REQUIS}
            for a, b in SEGMENTS:
                cv2.line(image, xy[a], xy[b], couleur, 2, cv2.LINE_AA)
            milieu = ((xy[posture.EPAULE_G][0] + xy[posture.EPAULE_D][0]) // 2,
                      (xy[posture.EPAULE_G][1] + xy[posture.EPAULE_D][1]) // 2)
            cv2.line(image, milieu, xy[posture.NEZ], couleur, 2, cv2.LINE_AA)
            for x, y in xy.values():
                cv2.circle(image, (x, y), 4, couleur, -1, cv2.LINE_AA)
        # Effet miroir : on se voit comme dans une glace.
        ok, jpeg = cv2.imencode(".jpg", cv2.flip(image, 1), [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            with self._verrou:
                numero = self._apercu[0] + 1 if self._apercu else 1
                self._apercu = (numero, jpeg.tobytes())
