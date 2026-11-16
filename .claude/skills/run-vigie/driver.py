#!/usr/bin/env python3
"""Driver de Vigie : lance le service sur des données jetables, vérifie l'API, photographie
la page.

Trois sous-commandes, à lancer depuis la racine du projet avec .venv/bin/python :

    serve   démarre le service (bloquant, Ctrl-C pour arrêter) : caméra factice, aucun
            message à l'extension GNOME, base jetable
    smoke   vérifie chaque endpoint (stdlib seule)
    ui      capture la page dans chromium headless, piloté par DevTools sur un tube

`serve` ne touche ni à la vraie caméra (le service réel la tient), ni à l'écran (un essai
ne doit pas assombrir le bureau), ni à data/vigie.db.
"""
import argparse
import base64
import fcntl
import json
import os
import pathlib
import select
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

RACINE = pathlib.Path(__file__).resolve().parents[3]
PORT_DEFAUT = 8031
PORT_REEL = 8030


def commande_serve(args):
    env = dict(os.environ, PYTHONPATH=str(RACINE / "src"))
    commande = [sys.executable, "-m", "vigie", "serve", "--port", str(args.port),
                "--camera", "factice", "--sans-ecran", "--data", args.data]
    return subprocess.call(commande, env=env, cwd=RACINE)


# --- smoke -----------------------------------------------------------

def requete(port, chemin, methode="GET", corps=None, timeout=10):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{chemin}", method=methode,
        data=None if corps is None else json.dumps(corps).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            brut = r.read()
            type_ = r.headers.get("Content-Type", "")
            return r.status, json.loads(brut) if "json" in type_ and brut else brut.decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def commande_smoke(args):
    if args.port == PORT_REEL:
        sys.exit(f"Refusé : {PORT_REEL} est le vrai service (smoke enregistre une posture et "
                 "bascule la pause). Viser un `serve` du driver.")
    echecs = 0

    def verifier(nom, ok, detail=""):
        nonlocal echecs
        echecs += not ok
        print(f"[{'ok ' if ok else 'KO '}] {nom}{' — ' + str(detail) if detail else ''}")

    try:
        code, page = requete(args.port, "/")
    except urllib.error.URLError:
        sys.exit(f"ECHEC : rien ne répond sur le port {args.port} (lancer `serve` d'abord)")
    verifier("page d'accueil", code == 200 and "<title>Vigie</title>" in page, code)
    for fichier in ("style.css", "app.js", "favicon.svg"):
        verifier(f"static/{fichier}", requete(args.port, f"/static/{fichier}")[0] == 200)

    code, etat = requete(args.port, "/api/etat")
    verifier("état", code == 200 and etat.get("etat") in ("absent", "non_calibre", "demarrage"),
             etat.get("etat") if code == 200 else code)
    code, signaux = requete(args.port, "/api/signaux")
    verifier("signaux", code == 200 and len(signaux) == 6, ", ".join(signaux) if code == 200 else code)

    _, avant = requete(args.port, "/api/reglages")
    code, apres = requete(args.port, "/api/reglages", "PUT", {"delai": 7})
    verifier("réglages", code == 200 and apres["delai"] == 7, apres)
    requete(args.port, "/api/reglages", "PUT", avant)
    code, ecrans = requete(args.port, "/api/ecrans")
    verifier("écrans", code == 200 and isinstance(ecrans, list), ecrans)  # vide : --sans-ecran

    code, r = requete(args.port, "/api/pause", "POST", {"pause": True})
    time.sleep(0.6)
    verifier("pause", code == 200 and r["pause"] and requete(args.port, "/api/etat")[1]["etat"] == "pause")
    code, r = requete(args.port, "/api/pause", "POST", {})
    verifier("reprise (bascule)", code == 200 and not r["pause"])

    code, _ = requete(args.port, "/api/postures", "POST", {"nom": "smoke"})
    verifier("enregistrement lancé", code == 202, code)
    verifier("second enregistrement refusé", requete(args.port, "/api/postures", "POST", {"nom": "x"})[0] == 409)
    time.sleep(6.8)
    resultat = requete(args.port, "/api/etat")[1].get("dernier_enregistrement") or {}
    # Caméra factice : personne à l'image, l'enregistrement doit échouer proprement.
    verifier("enregistrement sans personne refusé", resultat.get("ok") is False, resultat.get("message"))

    code, postures = requete(args.port, "/api/postures")
    verifier("postures", code == 200 and isinstance(postures, list), len(postures) if code == 200 else code)
    code, bilan = requete(args.port, "/api/bilan")
    verifier("bilan", code == 200 and isinstance(bilan, dict), bilan)
    verifier("test d'assombrissement", requete(args.port, "/api/test-assombrissement", "POST")[0] == 204)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/flux.mjpg", timeout=5) as r:
            debut = r.read(64)
        verifier("flux de l'aperçu", debut.startswith(b"--image"), debut[:40])
    except OSError as e:
        verifier("flux de l'aperçu", False, e)

    print("\nsmoke : " + ("OK" if not echecs else f"{echecs} échec(s)"))
    return 1 if echecs else 0


# --- ui --------------------------------------------------------------

# Le chromium que `playwright install chromium` met en cache ; à défaut, son
# chrome-headless-shell, qui suffit aussi.
CHROMIUMS = (sorted(pathlib.Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux*/chrome"))
             or sorted(pathlib.Path.home().glob(
                 ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux*/chrome-headless-shell")))
# Le trousseau GNOME, verrouillé au démarrage, figerait chromium sans `basic`.
OPTIONS_CHROMIUM = [
    "--headless", "--no-sandbox", "--hide-scrollbars", "--mute-audio", "--force-color-profile=srgb",
    "--no-first-run", "--no-default-browser-check", "--password-store=basic",
    "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
]


class Chromium:
    """Le chromium en cache, piloté sans playwright ni `--screenshot` (qui se
    fige) : le protocole DevTools passe par un tube (`--remote-debugging-pipe` :
    du JSON terminé par un octet nul, lu sur son fd 3, écrit sur son fd 4), la
    stdlib suffit. Réduit à ce dont `ui` se sert."""

    def __init__(self, binaire, options=()):
        self.profil = tempfile.TemporaryDirectory(prefix="vigie-chromium-")
        self.journal = pathlib.Path(self.profil.name) / "chromium.log"
        lecture, self.vers = os.pipe()
        self.depuis, ecriture = os.pipe()
        # Recopiés au-dessus de 4 : les dup2 de l'enfant vers 3 et 4 ne
        # peuvent plus s'écraser l'un l'autre.
        enfant = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 5) for fd in (lecture, ecriture)]
        os.close(lecture)
        os.close(ecriture)
        with open(self.journal, "wb") as journal:
            self.processus = subprocess.Popen(
                [str(binaire), *OPTIONS_CHROMIUM, *options, f"--user-data-dir={self.profil.name}",
                 "--remote-debugging-pipe", "about:blank"],
                stdout=journal, stderr=journal, close_fds=False,
                preexec_fn=lambda: (os.dup2(enfant[0], 3), os.dup2(enfant[1], 4)))
        for fd in enfant:
            os.close(fd)
        self.tampon, self.numero, self.reponses, self.pages = b"", 0, {}, {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.profil is None:
            return
        try:
            self._ecrire({"id": 0, "method": "Browser.close"})
            self.processus.wait(10)
        except (OSError, subprocess.TimeoutExpired):
            self.processus.kill()
            self.processus.wait()
        os.close(self.vers)
        os.close(self.depuis)
        self.profil.cleanup()
        self.profil = None

    def _ecrire(self, message):
        donnees = json.dumps(message).encode() + b"\0"
        while donnees:
            donnees = donnees[os.write(self.vers, donnees):]

    def _lire(self, delai):
        """Le prochain message de chromium, ou None passé `delai` secondes."""
        fin = time.monotonic() + delai
        while b"\0" not in self.tampon:
            if not select.select([self.depuis], [], [], max(0, fin - time.monotonic()))[0]:
                return None
            morceau = os.read(self.depuis, 1 << 20)
            if not morceau:
                raise RuntimeError("chromium s'est arrêté : " + self.journal.read_text(errors="replace")[-500:])
            self.tampon += morceau
        message, _, self.tampon = self.tampon.partition(b"\0")
        return json.loads(message)

    def attendre(self, condition, secondes):
        """Traite ce qu'envoie chromium jusqu'à ce que `condition()` soit
        vraie ; faux si elle ne l'est pas au bout de `secondes`."""
        fin = time.monotonic() + secondes
        while not condition():
            reste = fin - time.monotonic()
            if reste <= 0:
                return False
            message = self._lire(reste)
            if message is None:
                continue
            if "id" in message:
                self.reponses[message["id"]] = message
            elif message.get("sessionId") in self.pages:
                self.pages[message["sessionId"]].evenement(message["method"])
        return True

    def commande(self, methode, session=None, **params):
        self.numero += 1
        numero = self.numero
        self._ecrire({"id": numero, "method": methode, "params": params, **({"sessionId": session} if session else {})})
        if not self.attendre(lambda: numero in self.reponses, 30):
            raise RuntimeError(f"{methode} : pas de réponse de chromium en 30 s")
        reponse = self.reponses.pop(numero)
        if "error" in reponse:
            raise RuntimeError(f"{methode} : {reponse['error'].get('message')}")
        return reponse.get("result", {})

    def new_page(self, largeur, hauteur):
        cible = self.commande("Target.createTarget", url="about:blank")["targetId"]
        session = self.commande("Target.attachToTarget", targetId=cible, flatten=True)["sessionId"]
        page = self.pages[session] = Page(self, session)
        page.cdp("Page.enable")
        page.cdp("Runtime.enable")
        page.cdp("Emulation.setDeviceMetricsOverride", width=largeur, height=hauteur,
                 deviceScaleFactor=1, mobile=False)
        return page


class Page:
    def __init__(self, nav, session):
        self.nav, self.session = nav, session
        self.dom_pret = 0  # événements DOMContentLoaded du document principal

    def cdp(self, methode, **params):
        return self.nav.commande(methode, self.session, **params)

    def evenement(self, methode):
        # Pas Page.loadEventFired : le flux MJPEG de l'aperçu ne finit jamais, « load » ne vient pas.
        if methode == "Page.domContentEventFired":
            self.dom_pret += 1

    def js(self, expression):
        resultat = self.cdp("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in resultat:
            details = resultat["exceptionDetails"]
            raise RuntimeError("script : " + (details.get("exception", {}).get("description") or details.get("text")))
        return resultat["result"].get("value")

    def wait_for_timeout(self, ms):
        self.nav.attendre(lambda: False, ms / 1000)

    def capture(self, chemin):
        donnees = self.cdp("Page.captureScreenshot", format="png")["data"]
        pathlib.Path(chemin).write_bytes(base64.b64decode(donnees))


BUDGET = 3.0  # secondes au plus entre la navigation et la capture


def commande_ui(args):
    if not CHROMIUMS:
        sys.exit("Aucun chromium ni chrome-headless-shell dans ~/.cache/ms-playwright "
                 "(installer : playwright install chromium)")
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    png = out / "vigie.png"
    url = f"http://127.0.0.1:{args.port}/"
    with Chromium(CHROMIUMS[-1]) as nav:
        page = nav.new_page(args.width, 1100)
        fin = time.monotonic() + BUDGET
        resultat = page.cdp("Page.navigate", url=url)
        if resultat.get("errorText"):
            sys.exit(f"ECHEC : {url} : {resultat['errorText']} (lancer `serve` d'abord)")
        nav.attendre(lambda: page.dom_pret > 0, max(0, fin - time.monotonic()))
        # Puis le badge sorti de « Démarrage… » (premier état reçu), dans le même budget.
        badge = "(document.getElementById('etat-badge') || {}).textContent || ''"
        while time.monotonic() < fin and (page.dom_pret == 0 or "Démarrage" in page.js(badge)):
            page.wait_for_timeout(100)
        page.wait_for_timeout(200)  # le temps de peindre l'état reçu
        page.capture(png)
    print(f"  capture : {png} — à regarder : badge « Démarrage… » ou « Service arrêté » = échec")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="commande", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=PORT_DEFAUT)
    s.add_argument("--data", default="/tmp/vigie-driver")
    s = sub.add_parser("smoke")
    s.add_argument("--port", type=int, default=PORT_DEFAUT)
    s = sub.add_parser("ui")
    s.add_argument("--port", type=int, default=PORT_DEFAUT)
    s.add_argument("--out", default="/tmp/vigie-captures")
    s.add_argument("--width", type=int, default=1400)
    args = p.parse_args()
    return {"serve": commande_serve, "smoke": commande_smoke, "ui": commande_ui}[args.commande](args)


if __name__ == "__main__":
    sys.exit(main())
