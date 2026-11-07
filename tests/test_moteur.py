from datetime import datetime

import pytest

from conftest import points_personne

AVACHI = points_personne(y_oreilles=0.58, y_nez=0.56)


def test_sans_reference_non_calibre(banc):
    etat = banc.avancer(1)
    assert etat["etat"] == "non_calibre" and etat["niveau"] == 0


def test_enregistrement_d_une_posture(banc):
    banc.moteur.enregistrer("droit")
    etat = banc.avancer(1)
    assert etat["enregistrement"]["phase"] == "preparation"
    etat = banc.avancer(3)
    assert etat["enregistrement"]["phase"] == "capture"
    etat = banc.avancer(2.2)
    assert etat["enregistrement"] is None
    assert etat["dernier_enregistrement"]["ok"]
    assert [p["nom"] for p in banc.stockage.postures()] == ["droit"]
    assert banc.avancer(0.2)["etat"] == "ok"


def test_enregistrement_refuse_si_deja_en_cours(banc):
    banc.moteur.enregistrer("a")
    with pytest.raises(ValueError):
        banc.moteur.enregistrer("b")


def test_enregistrement_rate_si_personne_n_est_vu(banc):
    banc.detecteur.points = None
    banc.calibrer()
    etat = banc.moteur.instantane()
    assert not etat["dernier_enregistrement"]["ok"]
    assert banc.stockage.postures() == []


def test_avachi_assombrit_apres_le_delai_puis_se_redresser_eclaire(banc):
    banc.calibrer()
    banc.detecteur.points = AVACHI
    etat = banc.avancer(9)  # délai par défaut : 10 s, médiane glissante comprise
    assert etat["etat"] == "avachi" and etat["cause"] and etat["niveau"] == 0
    assert banc.avancer(3)["niveau"] > 0
    assert banc.ecran.appels[-1][1]["*"] > 0
    banc.detecteur.points = points_personne()
    assert banc.avancer(0.2)["niveau"] > 0  # une bonne mesure isolée peut être aberrante
    etat = banc.avancer(0.2)  # la deuxième emporte la médiane glissante
    assert etat["etat"] == "ok" and etat["niveau"] == 0
    assert banc.ecran.appels[-1][1]["*"] == 0


def test_fausse_alerte_retire_le_voile_jusqu_au_redressement(banc):
    banc.calibrer()
    banc.detecteur.points = AVACHI
    assert banc.avancer(40)["niveau"] > 0
    assert banc.moteur.signaler_fausse_alerte() == {"cause": "tête en avant ou qui s'enfonce"}
    etat = banc.avancer(60)
    assert etat["etat"] == "avachi" and etat["fausse_alerte"] and etat["niveau"] == 0
    banc.moteur.signaler_fausse_alerte()  # second clic : rien de plus en base
    [notee] = banc.stockage.fausses_alertes(datetime.now().strftime("%Y-%m-%d"))
    assert notee["signal"] == "tete" and notee["niveau"] > 0 and notee["mesures"]["tete"] > 0
    assert banc.moteur.bilan()["fausses_alertes"] == 1
    banc.detecteur.points = points_personne()
    assert not banc.avancer(1.2)["fausse_alerte"]
    banc.detecteur.points = AVACHI
    assert banc.avancer(40)["niveau"] > 0  # redressé puis ré-avachi : l'alerte revient


def test_fausse_alerte_juste_apres_redressement_sinon_refusee(banc):
    banc.calibrer()
    with pytest.raises(ValueError):
        banc.moteur.signaler_fausse_alerte()  # jamais jugé avachi
    banc.detecteur.points = AVACHI
    banc.avancer(40)
    banc.detecteur.points = points_personne()
    banc.avancer(5)  # redressé par réflexe avant d'atteindre le menu
    assert banc.moteur.signaler_fausse_alerte()["cause"]
    banc.avancer(8)
    with pytest.raises(ValueError):
        banc.moteur.signaler_fausse_alerte()  # redressé depuis plus de 10 s


def test_pas_d_assombrissement_pendant_un_enregistrement(banc):
    banc.calibrer()
    banc.detecteur.points = AVACHI
    banc.avancer(40)
    banc.moteur.enregistrer("penché")
    assert banc.avancer(0.2)["niveau"] == 0


def test_pause_libere_la_camera(banc):
    banc.calibrer()
    banc.moteur.mettre_en_pause(True)
    assert not banc.camera.actif
    etat = banc.avancer(1)
    assert etat["etat"] == "pause" and etat["pause"] and etat["niveau"] == 0
    with pytest.raises(ValueError):
        banc.moteur.enregistrer("x")
    banc.moteur.mettre_en_pause(False)
    assert banc.camera.actif and banc.avancer(0.2)["etat"] == "ok"


def test_absent_et_incertain(banc):
    banc.calibrer()
    banc.detecteur.points = None
    assert banc.avancer(0.2)["etat"] == "absent"
    masque = points_personne()
    masque[11] = (0.5, 0.8, 0.1)
    banc.detecteur.points = masque
    assert banc.avancer(0.2)["etat"] == "incertain"


def test_camera_indisponible(banc):
    banc.camera.arreter()
    assert banc.avancer(0.2)["etat"] == "sans_camera"


def test_test_d_assombrissement(banc):
    banc.calibrer()
    banc.moteur.tester_assombrissement()
    assert banc.avancer(1)["niveau"] == 1
    assert banc.avancer(3)["niveau"] == 0


def test_assombrissement_maximal_propre_a_chaque_ecran(banc):
    banc.stockage.modifier_reglages({"niveau_max": 0.5, "ecrans": {"DP-1": 0.9}})
    banc.moteur.recharger()
    banc.calibrer()
    banc.moteur.tester_assombrissement()
    banc.avancer(1)
    assert banc.ecran.appels[-1] == ("ok", {"*": 0.5, "DP-1": 0.9})
    banc.avancer(3)
    assert banc.ecran.appels[-1] == ("ok", {"*": 0, "DP-1": 0})


def test_bilan_du_jour_cumule_memoire_et_base(banc):
    banc.calibrer()
    banc.avancer(70)  # dépasse la minute : une partie est écrite en base
    banc.detecteur.points = None
    banc.avancer(10)
    bilan = banc.moteur.bilan()
    assert bilan["ok"] == pytest.approx(70, abs=1)
    assert bilan["absent"] == pytest.approx(10, abs=0.5)
    assert bilan["causes"] == {}


def test_bilan_temps_avachi_par_signal_en_cause(banc):
    banc.calibrer()
    banc.detecteur.points = AVACHI
    banc.avancer(90)  # dépasse la minute : une partie est écrite en base
    bilan = banc.moteur.bilan()
    assert list(bilan["causes"]) == ["tete"]
    assert bilan["causes"]["tete"] == pytest.approx(bilan["avachi"])


def test_apercu_seulement_avec_un_spectateur(banc):
    banc.avancer(0.2)
    assert banc.moteur.apercu() is None
    with banc.moteur.spectateur():
        banc.avancer(0.4)
        numero, jpeg = banc.moteur.apercu()
    assert numero == 2 and jpeg[:2] == b"\xff\xd8"


def test_longue_absence_ralentit_puis_quelqu_un_revient(banc):
    from vigie.moteur import DECODAGE_ABSENT, DELAI_RALENTI, FREQUENCE, FREQUENCE_ABSENT

    banc.calibrer()
    banc.detecteur.points = None
    etat = banc.avancer(DELAI_RALENTI - 1)
    assert etat["etat"] == "absent" and not etat["ralenti"]
    assert banc.moteur.periode() == 1 / FREQUENCE and banc.camera.limite is None
    etat = banc.avancer(1.4)
    assert etat["ralenti"] and banc.moteur.periode() == 1 / FREQUENCE_ABSENT
    assert banc.camera.limite == DECODAGE_ABSENT
    banc.detecteur.points = points_personne()
    etat = banc.avancer(1, dt=1)  # une seule analyse au ralenti suffit à repartir
    assert etat["etat"] == "ok" and not etat["ralenti"]
    assert banc.moteur.periode() == 1 / FREQUENCE and banc.camera.limite is None


def test_absences_breves_ne_ralentissent_pas(banc):
    from vigie.moteur import DELAI_RALENTI

    banc.calibrer()
    for _ in range(3):  # le décompte repart à chaque retour, même incertain
        banc.detecteur.points = None
        banc.avancer(DELAI_RALENTI - 10)
        masque = points_personne()
        masque[11] = (0.5, 0.8, 0.1)
        banc.detecteur.points = masque
        assert banc.avancer(0.2)["etat"] == "incertain"
    assert not banc.moteur.instantane()["ralenti"]


def test_pas_de_ralenti_pendant_un_enregistrement(banc):
    from vigie.moteur import DELAI_RALENTI

    banc.detecteur.points = None
    assert banc.avancer(DELAI_RALENTI + 1)["ralenti"]
    banc.moteur.enregistrer("droit")
    assert not banc.avancer(0.2)["ralenti"]
    assert banc.camera.limite is None


def test_pause_quitte_le_ralenti(banc):
    from vigie.moteur import DELAI_RALENTI

    banc.calibrer()
    banc.detecteur.points = None
    assert banc.avancer(DELAI_RALENTI + 1)["ralenti"]
    banc.moteur.mettre_en_pause(True)
    assert not banc.avancer(0.2)["ralenti"]


def test_bilan_juste_au_ralenti(banc):
    from vigie.moteur import FREQUENCE_ABSENT

    banc.calibrer()
    banc.detecteur.points = None
    banc.avancer(30 * 60, dt=1 / FREQUENCE_ABSENT + 0.05)  # période + temps d'analyse
    assert banc.moteur.bilan()["absent"] == pytest.approx(30 * 60, abs=2)


def test_commande_reveille_la_boucle_au_ralenti(banc):
    import time

    from vigie.moteur import DELAI_RALENTI

    banc.detecteur.points = None
    assert banc.avancer(DELAI_RALENTI + 1)["ralenti"]
    banc.moteur.demarrer()
    try:
        time.sleep(0.1)  # la boucle attend maintenant une seconde entière
        banc.moteur.mettre_en_pause(True)
        time.sleep(0.3)
        assert banc.moteur.instantane()["etat"] == "pause"
    finally:
        banc.moteur.arreter()
