import math

import pytest

from conftest import mesures_personne, points_personne
from vigie import posture


def test_mesures_d_une_personne_droite(droit):
    assert droit["tete"] == pytest.approx(0.3 / 0.3)
    assert droit["nez"] == pytest.approx(0.32 / 0.3)
    assert droit["hauteur"] == pytest.approx(0.5)
    assert droit["proximite"] == pytest.approx(math.log(0.3))
    assert droit["visage"] == pytest.approx(0.08 / 0.3)
    assert droit["epaules"] == pytest.approx(0.0, abs=1e-9)


def test_point_masque_ou_hors_champ_donne_none():
    pts = points_personne()
    pts[posture.EPAULE_D] = (0.3, 0.8, 0.2)
    assert posture.mesurer(pts, 640, 480) is None
    assert posture.mesurer(points_personne(y_epaules=1.05), 640, 480) is None


def test_inclinaison_independante_de_l_ordre_des_epaules():
    penche = mesures_personne(pente=0.05)
    assert penche["epaules"] > 5
    pts = points_personne(pente=0.05)
    pts[posture.EPAULE_G], pts[posture.EPAULE_D] = pts[posture.EPAULE_D], pts[posture.EPAULE_G]
    assert posture.mesurer(pts, 640, 480)["epaules"] == pytest.approx(penche["epaules"])


def test_meme_posture_est_ok(droit):
    ev = posture.evaluer(droit, {1: droit})
    assert ev.etat == "ok" and ev.ecart == 0 and ev.signal is ev.cause is None and ev.reference == 1


def test_tete_qui_s_enfonce_est_avachie(droit):
    affaisse = mesures_personne(y_oreilles=0.56, y_nez=0.54)
    ev = posture.evaluer(affaisse, {1: droit})
    assert ev.etat == "avachi"
    assert ev.signal == "tete" and ev.cause == "tête en avant ou qui s'enfonce"


def test_trop_pres_de_l_ecran(droit):
    # Tout grossit de 20 % : seule la proximité change, pas les rapports.
    plus_pres = mesures_personne(largeur=0.36, ecart_yeux=0.096, y_oreilles=0.44, y_nez=0.416)
    ev = posture.evaluer(plus_pres, {1: droit})
    assert ev.etat == "avachi" and ev.cause == "trop près de l'écran"


def test_se_tenir_plus_droit_que_la_reference_n_est_pas_puni(droit):
    redresse = mesures_personne(y_oreilles=0.44, y_nez=0.42, largeur=0.27, ecart_yeux=0.072)
    assert posture.evaluer(redresse, {1: droit}).ecart == 0


def test_la_reference_la_plus_proche_fait_foi(droit):
    lecture = mesures_personne(y_oreilles=0.58, y_nez=0.56)
    ev = posture.evaluer(lecture, {1: droit, 2: lecture})
    assert ev.etat == "ok" and ev.reference == 2


def test_facteur_de_tolerance(droit):
    leger = mesures_personne(y_oreilles=0.52, y_nez=0.50)
    assert posture.evaluer(leger, {1: droit}).etat == "ok"
    assert posture.evaluer(leger, {1: droit}, facteur=0.5).etat == "avachi"


def test_lissage_par_mediane(droit):
    aberrante = dict(droit, hauteur=0.9)
    lisse = posture.lisser([droit, aberrante, droit])
    assert lisse == droit
