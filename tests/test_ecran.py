import subprocess

import pytest

from vigie import ecran
from vigie.ecran import Ecran


@pytest.fixture
def commandes(monkeypatch):
    """Remplace gdbus et dconf : `reponses` fixe leur sortie, `lancees` garde les appels."""

    class Faux:
        reponses = {"gdbus": 0, "dconf": "false\n"}
        lancees = []

        @classmethod
        def run(cls, commande, **kw):
            cls.lancees.append(commande[0])
            reponse = cls.reponses[commande[0]]
            if isinstance(reponse, int):
                return subprocess.CompletedProcess(commande, reponse, "", "")
            return subprocess.CompletedProcess(commande, 0, reponse, "")

    Faux.lancees = []
    monkeypatch.setattr(ecran.subprocess, "run", Faux.run)
    return Faux


def test_extension_qui_repond(commandes):
    e = Ecran()
    e.signaler("ok", 0.0)
    assert e.disponible is True and e.extensions_desactivees is None
    assert commandes.lancees == ["gdbus"]  # dconf n'est lu qu'en cas de silence


def test_extensions_utilisateur_desactivees_par_gnome(commandes):
    commandes.reponses = {"gdbus": 1, "dconf": "true\n"}
    e = Ecran()
    e.signaler("ok", 0.0)
    assert e.disponible is False and e.extensions_desactivees is True


def test_extension_muette_mais_extensions_actives(commandes):
    commandes.reponses = {"gdbus": 1, "dconf": ""}  # clé jamais écrite : défaut false
    e = Ecran()
    e.signaler("ok", 0.0)
    assert e.disponible is False and e.extensions_desactivees is False
