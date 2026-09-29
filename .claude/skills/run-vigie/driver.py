#!/usr/bin/env python3
"""Driver de Vigie : lance le service sur des données jetables, vérifie l'API, photographie
la page.

Trois sous-commandes, à lancer depuis la racine du projet avec .venv/bin/python :

    serve   démarre le service (bloquant, Ctrl-C pour arrêter) : caméra factice, aucun
            message à l'extension GNOME, base jetable
    smoke   vérifie chaque endpoint (stdlib seule)
    ui      capture la page dans chromium headless

`serve` ne touche ni à la vraie caméra (le service réel la tient), ni à l'écran (un essai
ne doit pas assombrir le bureau), ni à data/vigie.db.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
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

def chromium():
    cache = pathlib.Path.home() / ".cache" / "ms-playwright"
    candidats = sorted(cache.glob("chromium-*/chrome-linux*/chrome"), key=lambda p: int(p.parts[-3].split("-")[1]))
    if not candidats:
        sys.exit("Aucun chromium dans ~/.cache/ms-playwright (installer : playwright install chromium)")
    return candidats[-1]


def commande_ui(args):
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    png = out / "vigie.png"
    # Le flux MJPEG ne finit jamais : --virtual-time-budget borne l'attente avant la capture.
    subprocess.run(
        [str(chromium()), "--headless", "--no-sandbox", "--hide-scrollbars",
         f"--window-size={args.width},1100", "--virtual-time-budget=3000",
         f"--screenshot={png}", f"http://127.0.0.1:{args.port}/"],
        check=True, capture_output=True, timeout=60,
    )
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
