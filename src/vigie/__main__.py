"""Point d'entrée : `python -m vigie [serve|pause|reprendre|basculer|etat]`."""

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
PORT = 8030


class EcranMuet:
    """Pour une instance de test : ne jamais assombrir le vrai écran."""

    disponible = None

    def signaler(self, etat, niveau):
        pass


def servir(args):
    os.environ.setdefault("GLOG_minloglevel", "2")  # MediaPipe est bavard au chargement
    import uvicorn

    from .camera import Camera, CameraFactice
    from .detection import Detecteur
    from .ecran import Ecran
    from .moteur import Moteur
    from .stockage import Stockage
    from .web import creer_app

    stockage = Stockage(args.data / "vigie.db")
    camera = CameraFactice() if args.camera == "factice" else Camera(int(args.camera))
    moteur = Moteur(stockage, camera, Detecteur(RACINE / "models", args.modele),
                    EcranMuet() if args.sans_ecran else Ecran())
    app = creer_app(moteur, stockage)
    moteur.demarrer()
    try:
        # 127.0.0.1 seulement : l'aperçu de la caméra ne doit pas sortir de la machine.
        uvicorn.run(app, host="127.0.0.1", port=args.port, timeout_graceful_shutdown=2)
    finally:
        moteur.arreter()


def appeler(port, chemin, corps=None):
    requete = urllib.request.Request(
        f"http://127.0.0.1:{port}{chemin}",
        data=None if corps is None else json.dumps(corps).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return json.load(reponse)
    except urllib.error.URLError:
        sys.exit(f"Vigie ne répond pas sur le port {port} : le service est-il lancé ?")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vigie", description="Surveille la posture par la webcam.")
    parser.set_defaults(commande="serve", port=PORT, data=RACINE / "data", camera="0",
                        modele="full", sans_ecran=False)
    sous = parser.add_subparsers(dest="commande")
    serve = sous.add_parser("serve", help="lance le service (commande par défaut)")
    serve.add_argument("--port", type=int, default=PORT)
    serve.add_argument("--data", type=Path, default=RACINE / "data", help="dossier de la base")
    serve.add_argument("--camera", default="0", help="numéro du périphérique vidéo, ou « factice »")
    serve.add_argument("--modele", choices=["lite", "full"], default="full")
    serve.add_argument("--sans-ecran", action="store_true",
                       help="n'envoie rien à l'extension GNOME (instance de test)")
    for nom, aide in [("pause", "met la surveillance en pause et libère la caméra"),
                      ("reprendre", "reprend la surveillance"),
                      ("basculer", "pause ↔ reprise (pour un raccourci clavier)"),
                      ("etat", "affiche l'état courant")]:
        sous.add_parser(nom, help=aide).add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)

    if args.commande == "serve":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
        servir(args)
    elif args.commande == "etat":
        etat = appeler(args.port, "/api/etat")
        print(etat["etat"] + (f" ({etat['cause']})" if etat.get("cause") else ""))
    else:
        corps = {"pause": True, "reprendre": False, "basculer": None}[args.commande]
        pause = appeler(args.port, "/api/pause", {"pause": corps})["pause"]
        print("En pause, caméra libérée." if pause else "Surveillance reprise.")


if __name__ == "__main__":
    main()
