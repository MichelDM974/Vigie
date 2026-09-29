import pytest
from fastapi.testclient import TestClient

from conftest import points_personne
from vigie.web import creer_app


@pytest.fixture
def client(banc):
    return TestClient(creer_app(banc.moteur, banc.stockage))


def test_page_d_accueil(client):
    r = client.get("/")
    assert r.status_code == 200 and "<title>Vigie</title>" in r.text
    assert client.get("/static/style.css").status_code == 200


def test_etat(client, banc):
    banc.avancer(0.2)
    assert client.get("/api/etat").json()["etat"] == "non_calibre"


def test_pause_explicite_et_bascule(client, banc):
    assert client.post("/api/pause", json={"pause": True}).json() == {"pause": True}
    assert not banc.camera.actif
    assert client.post("/api/pause", json={}).json() == {"pause": False}
    assert banc.camera.actif


def test_postures(client, banc):
    assert client.post("/api/postures", json={"nom": "  droit "}).status_code == 202
    assert client.post("/api/postures", json={"nom": "autre"}).status_code == 409
    banc.avancer(6.2)
    postures = client.get("/api/postures").json()
    assert [p["nom"] for p in postures] == ["droit"]
    assert client.delete(f"/api/postures/{postures[0]['id']}").status_code == 204
    assert client.delete(f"/api/postures/{postures[0]['id']}").status_code == 404
    assert client.post("/api/postures", json={"nom": ""}).status_code == 422


def test_reglages(client, banc):
    r = client.put("/api/reglages", json={"delai": 4, "rampe": 2, "tolerance": 1.5})
    assert r.json()["delai"] == 4 and r.json()["rampe"] == 2 and r.json()["tolerance"] == 1.5
    assert banc.moteur.alerte.reglages.delai == 4 and banc.moteur.alerte.reglages.rampe == 2
    assert client.get("/api/reglages").json()["delai"] == 4


def test_ecrans_et_leur_assombrissement_maximal(client, banc):
    client.put("/api/reglages", json={"niveau_max": 0.7, "ecrans": {"DP-1": 0.9}})
    assert client.get("/api/ecrans").json() == [
        {"connecteur": "HDMI-1", "nom": "S24D330", "niveau_max": 0.7},
        {"connecteur": "DP-1", "nom": "Odyssey G5", "niveau_max": 0.9},
    ]
    assert banc.moteur._maxima == {"*": 0.7, "DP-1": 0.9}


def test_test_assombrissement_et_bilan(client, banc):
    assert client.post("/api/test-assombrissement").status_code == 204
    assert banc.avancer(0.4)["niveau"] > 0
    assert "non_calibre" not in client.get("/api/bilan").json()


def test_fausse_alerte(client, banc):
    assert client.post("/api/fausse-alerte").status_code == 409
    banc.calibrer()
    banc.detecteur.points = points_personne(y_oreilles=0.58, y_nez=0.56)
    banc.avancer(2)
    assert client.post("/api/fausse-alerte").json()["cause"]
    banc.avancer(0.2)
    assert client.get("/api/etat").json()["fausse_alerte"]
    assert client.get("/api/bilan").json()["fausses_alertes"] == 1


def test_signaux(client):
    signaux = client.get("/api/signaux").json()
    assert signaux["proximite"]["cause"] == "trop près de l'écran"
