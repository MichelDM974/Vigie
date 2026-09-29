import pytest

from vigie.alerte import Alerte, ReglagesAlerte


def avancer(alerte, etat, secondes, dt=0.1):
    for _ in range(round(secondes / dt)):
        niveau = alerte.avancer(etat, dt)
    return niveau


@pytest.fixture
def alerte():
    return Alerte(ReglagesAlerte(delai=30, rampe=20, niveau_max=0.6))


def test_rien_avant_le_delai(alerte):
    assert avancer(alerte, "avachi", 29.9) == 0


def test_rampe_puis_plafond(alerte):
    avancer(alerte, "avachi", 30)
    assert avancer(alerte, "avachi", 10) == pytest.approx(0.3, abs=0.01)
    assert avancer(alerte, "avachi", 60) == pytest.approx(0.6)


def test_se_redresser_eclaircit_aussitot(alerte):
    avancer(alerte, "avachi", 45)
    assert alerte.avancer("ok", 0.1) == 0


def test_bref_redressement_ne_remet_pas_a_zero(alerte):
    avancer(alerte, "avachi", 20)
    avancer(alerte, "ok", 1)
    assert avancer(alerte, "avachi", 12) > 0


def test_rechute_apres_redressement_reassombrit_plus_vite(alerte):
    avancer(alerte, "avachi", 50)
    avancer(alerte, "ok", 5)  # compte plafonné au délai (30) puis -10
    assert avancer(alerte, "avachi", 9.5) == 0
    assert avancer(alerte, "avachi", 1) > 0


def test_long_redressement_remet_a_zero(alerte):
    avancer(alerte, "avachi", 50)
    avancer(alerte, "ok", 15)
    assert alerte.mauvais == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("etat", ["absent", "pause", "non_calibre", "sans_camera"])
def test_absence_ou_pause_remet_a_zero(alerte, etat):
    avancer(alerte, "avachi", 45)
    assert alerte.avancer(etat, 0.1) == 0 and alerte.mauvais == 0


def test_incertain_garde_l_etat(alerte):
    niveau = avancer(alerte, "avachi", 40)
    assert avancer(alerte, "incertain", 5) == niveau
    assert alerte.mauvais == pytest.approx(40)


def test_delai_nul_assombrit_des_la_premiere_mesure():
    alerte = Alerte(ReglagesAlerte(delai=0, rampe=20, niveau_max=0.6))
    assert alerte.avancer("avachi", 0.2) > 0
    assert alerte.avancer("ok", 0.2) == 0 and alerte.mauvais == 0
