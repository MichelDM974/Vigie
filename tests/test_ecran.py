import json
import subprocess

import pytest

from vigie import ecran
from vigie.ecran import Ecran


@pytest.fixture
def commandes(monkeypatch):
    """Remplace gdbus, dconf et busctl : `reponses` fixe leur sortie, `lancees` garde les
    programmes appelés et `derniere` la dernière commande complète."""

    class Faux:
        reponses = {"gdbus": 0, "dconf": "false\n", "busctl": ""}
        lancees = []
        derniere = None

        @classmethod
        def run(cls, commande, **kw):
            cls.lancees.append(commande[0])
            cls.derniere = commande
            reponse = cls.reponses[commande[0]]
            if isinstance(reponse, int):
                return subprocess.CompletedProcess(commande, reponse, "", "")
            return subprocess.CompletedProcess(commande, 0, reponse, "")

    Faux.lancees = []
    monkeypatch.setattr(ecran.subprocess, "run", Faux.run)
    return Faux


def test_extension_qui_repond(commandes):
    e = Ecran()
    e.signaler("ok", {"*": 0.0})
    assert e.disponible is True and e.extensions_desactivees is None
    assert commandes.lancees == ["gdbus"]  # dconf n'est lu qu'en cas de silence


def test_extensions_utilisateur_desactivees_par_gnome(commandes):
    commandes.reponses = {"gdbus": 1, "dconf": "true\n"}
    e = Ecran()
    e.signaler("ok", {"*": 0.0})
    assert e.disponible is False and e.extensions_desactivees is True


def test_extension_muette_mais_extensions_actives(commandes):
    commandes.reponses = {"gdbus": 1, "dconf": ""}  # clé jamais écrite : défaut false
    e = Ecran()
    e.signaler("ok", {"*": 0.0})
    assert e.disponible is False and e.extensions_desactivees is False


def test_niveau_de_chaque_ecran_et_renvoi_au_changement(commandes):
    horloge = iter([0.0, 0.5, 1.0]).__next__
    e = Ecran(horloge=horloge)
    e.signaler("avachi", {"*": 0.5, "DP-1": 0.9})
    assert commandes.derniere[-2:] == ["'avachi'", "{'*': 0.500, 'DP-1': 0.900}"]
    e.signaler("avachi", {"*": 0.51, "DP-1": 0.9})  # écart négligeable, avant le battement
    e.signaler("avachi", {"*": 0.5, "DP-1": 0.95})
    assert commandes.lancees == ["gdbus", "gdbus"]


def test_liste_des_ecrans_de_gauche_a_droite(commandes):
    etat = [1, [[["DP-1", "SAM", "Odyssey G5", "HK7"], [], {}],
                [["HDMI-1", "SAM", "S24D330", "0x5a"], [], {}]],
            [[1920, 0, 1.0, 0, False, [["DP-1", "SAM", "Odyssey G5", "HK7"]], {}],
             [0, 0, 1.0, 0, True, [["HDMI-1", "SAM", "S24D330", "0x5a"]], {}]], {}]
    commandes.reponses["busctl"] = json.dumps({"type": "ua(ssss)", "data": etat})
    assert Ecran().lister() == [{"connecteur": "HDMI-1", "nom": "S24D330"},
                                {"connecteur": "DP-1", "nom": "Odyssey G5"}]
    commandes.reponses["busctl"] = ""  # Mutter injoignable
    assert Ecran().lister() == []
