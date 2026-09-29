"""Base SQLite de Vigie : postures de référence, réglages, temps passé dans chaque état."""

import json
import sqlite3
import threading
from datetime import datetime

REGLAGES_DEFAUT = {
    "tolerance": 1.0,  # facteur appliqué à toutes les tolérances des signaux
    "delai": 10.0,
    "niveau_max": 0.6,
}
BORNES_REGLAGES = {"tolerance": (0.3, 3.0), "delai": (0.0, 10.0), "niveau_max": (0.1, 0.9)}


def _borner(cle, valeur):
    bas, haut = BORNES_REGLAGES[cle]
    return min(haut, max(bas, float(valeur)))


class Stockage:
    def __init__(self, chemin):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(chemin, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._verrou = threading.Lock()
        with self._verrou, self._conn:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS postures (
                    id INTEGER PRIMARY KEY,
                    nom TEXT NOT NULL,
                    cree_le TEXT NOT NULL,
                    mesures TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reglages (
                    cle TEXT PRIMARY KEY,
                    valeur TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS temps (
                    minute TEXT NOT NULL,  -- heure locale, AAAA-MM-JJTHH:MM
                    etat TEXT NOT NULL,
                    secondes REAL NOT NULL,
                    PRIMARY KEY (minute, etat)
                );
                CREATE TABLE IF NOT EXISTS causes (
                    minute TEXT NOT NULL,  -- comme temps
                    signal TEXT NOT NULL,  -- signal qui dépasse le plus pendant « avachi »
                    secondes REAL NOT NULL,
                    PRIMARY KEY (minute, signal)
                );
                CREATE TABLE IF NOT EXISTS fausses_alertes (
                    id INTEGER PRIMARY KEY,
                    quand TEXT NOT NULL,  -- heure locale, AAAA-MM-JJTHH:MM:SS
                    reference INTEGER,  -- posture de référence la plus proche
                    signal TEXT,  -- signal qui dépassait le plus
                    niveau REAL NOT NULL,  -- assombrissement à ce moment
                    mesures TEXT NOT NULL,  -- JSON, lissées : de quoi recaler les tolérances
                    ecarts TEXT NOT NULL  -- JSON, normalisés avec la tolérance générale du moment
                );
            """)

    def postures(self):
        with self._verrou:
            lignes = self._conn.execute("SELECT * FROM postures ORDER BY id").fetchall()
        return [dict(ligne, mesures=json.loads(ligne["mesures"])) for ligne in lignes]

    def ajouter_posture(self, nom, mesures):
        cree_le = datetime.now().isoformat(timespec="seconds")
        with self._verrou, self._conn:
            cur = self._conn.execute(
                "INSERT INTO postures (nom, cree_le, mesures) VALUES (?, ?, ?)",
                (nom, cree_le, json.dumps(mesures)),
            )
        return cur.lastrowid

    def supprimer_posture(self, posture_id):
        with self._verrou, self._conn:
            cur = self._conn.execute("DELETE FROM postures WHERE id = ?", (posture_id,))
        return cur.rowcount > 0

    def reglages(self):
        with self._verrou:
            lignes = self._conn.execute("SELECT cle, valeur FROM reglages").fetchall()
        enregistres = {l["cle"]: json.loads(l["valeur"]) for l in lignes}
        return {cle: _borner(cle, enregistres.get(cle, defaut))
                for cle, defaut in REGLAGES_DEFAUT.items()}

    def modifier_reglages(self, changements):
        """Enregistre les réglages connus, ramenés dans leurs bornes ; renvoie l'ensemble."""
        with self._verrou, self._conn:
            for cle, valeur in changements.items():
                if cle not in REGLAGES_DEFAUT or valeur is None:
                    continue
                self._conn.execute(
                    "INSERT OR REPLACE INTO reglages (cle, valeur) VALUES (?, ?)",
                    (cle, json.dumps(_borner(cle, valeur))),
                )
        return self.reglages()

    def ajouter_temps(self, cumuls, causes=None):
        """Ajoute des secondes par (minute, état) : {("2026-09-29T19:40", "ok"): 12.5, ...},
        et le temps avachi par (minute, signal en cause), de même forme."""
        with self._verrou, self._conn:
            self._conn.executemany(
                """INSERT INTO temps (minute, etat, secondes) VALUES (?, ?, ?)
                   ON CONFLICT (minute, etat) DO UPDATE SET secondes = secondes + excluded.secondes""",
                [(minute, etat, s) for (minute, etat), s in cumuls.items()],
            )
            self._conn.executemany(
                """INSERT INTO causes (minute, signal, secondes) VALUES (?, ?, ?)
                   ON CONFLICT (minute, signal) DO UPDATE SET secondes = secondes + excluded.secondes""",
                [(minute, signal, s) for (minute, signal), s in (causes or {}).items()],
            )

    def bilan(self, jour):
        """Secondes passées dans chaque état le jour donné (AAAA-MM-JJ)."""
        with self._verrou:
            lignes = self._conn.execute(
                "SELECT etat, SUM(secondes) AS s FROM temps WHERE minute LIKE ? GROUP BY etat",
                (jour + "T%",),
            ).fetchall()
        return {l["etat"]: l["s"] for l in lignes}

    def ajouter_fausse_alerte(self, reference, signal, niveau, mesures, ecarts):
        quand = datetime.now().isoformat(timespec="seconds")
        with self._verrou, self._conn:
            self._conn.execute(
                """INSERT INTO fausses_alertes (quand, reference, signal, niveau, mesures, ecarts)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (quand, reference, signal, niveau, json.dumps(mesures), json.dumps(ecarts)),
            )

    def fausses_alertes(self, jour):
        """Fausses alertes signalées le jour donné (AAAA-MM-JJ), dans l'ordre."""
        with self._verrou:
            lignes = self._conn.execute(
                "SELECT * FROM fausses_alertes WHERE quand LIKE ? ORDER BY id", (jour + "T%",)
            ).fetchall()
        return [dict(l, mesures=json.loads(l["mesures"]), ecarts=json.loads(l["ecarts"]))
                for l in lignes]

    def causes(self, jour):
        """Secondes avachi par signal en cause le jour donné (AAAA-MM-JJ)."""
        with self._verrou:
            lignes = self._conn.execute(
                "SELECT signal, SUM(secondes) AS s FROM causes WHERE minute LIKE ? GROUP BY signal",
                (jour + "T%",),
            ).fetchall()
        return {l["signal"]: l["s"] for l in lignes}
