from vigie.stockage import REGLAGES_DEFAUT, Stockage


def test_postures(tmp_path):
    s = Stockage(tmp_path / "v.db")
    pid = s.ajouter_posture("droit", {"tete": 1.0})
    assert s.postures()[0]["mesures"] == {"tete": 1.0}
    assert s.supprimer_posture(pid) and not s.supprimer_posture(pid)
    assert s.postures() == []


def test_reglages_bornes_et_persistants(tmp_path):
    s = Stockage(tmp_path / "v.db")
    assert s.reglages() == REGLAGES_DEFAUT
    s.modifier_reglages({"delai": 1, "niveau_max": 0.5, "inconnu": 3, "tolerance": None})
    assert Stockage(tmp_path / "v.db").reglages() == dict(REGLAGES_DEFAUT, delai=5.0, niveau_max=0.5)


def test_temps_cumules_par_jour(tmp_path):
    s = Stockage(tmp_path / "v.db")
    s.ajouter_temps({("2026-09-29T10:00", "ok"): 30, ("2026-09-29T10:01", "avachi"): 5})
    s.ajouter_temps({("2026-09-29T10:00", "ok"): 12, ("2026-09-30T00:00", "ok"): 60})
    assert s.bilan("2026-09-29") == {"ok": 42, "avachi": 5}


def test_causes_cumulees_par_jour(tmp_path):
    s = Stockage(tmp_path / "v.db")
    s.ajouter_temps({("2026-09-29T10:01", "avachi"): 5}, {("2026-09-29T10:01", "hauteur"): 5})
    s.ajouter_temps({}, {("2026-09-29T10:01", "hauteur"): 2, ("2026-09-29T10:02", "tete"): 3,
                         ("2026-09-30T00:00", "tete"): 60})
    assert s.causes("2026-09-29") == {"hauteur": 7, "tete": 3}
