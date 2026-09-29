"""Page locale de Vigie : aperçu de la caméra, postures de référence, réglages, bilan."""

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .posture import SIGNAUX

STATIC = Path(__file__).resolve().parent.parent / "static"


class NouvellePosture(BaseModel):
    nom: str = Field(min_length=1, max_length=60)


class Pause(BaseModel):
    pause: bool | None = None  # absent : bascule


class Reglages(BaseModel):
    tolerance: float | None = None
    delai: float | None = None
    rampe: float | None = None
    niveau_max: float | None = None


def creer_app(moteur, stockage):
    app = FastAPI(title="Vigie")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def accueil():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/etat")
    def etat():
        return moteur.instantane()

    @app.get("/api/signaux")
    def signaux():
        return {nom: {"libelle": s.libelle, "cause": s.cause} for nom, s in SIGNAUX.items()}

    @app.post("/api/pause")
    def pause(demande: Pause):
        pause = not moteur.en_pause() if demande.pause is None else demande.pause
        moteur.mettre_en_pause(pause)
        return {"pause": pause}

    @app.get("/api/postures")
    def postures():
        return [{k: p[k] for k in ("id", "nom", "cree_le")} for p in stockage.postures()]

    @app.post("/api/postures", status_code=202)
    def enregistrer(demande: NouvellePosture):
        try:
            moteur.enregistrer(demande.nom.strip())
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"nom": demande.nom.strip()}

    @app.delete("/api/postures/{posture_id}", status_code=204)
    def supprimer(posture_id: int):
        if not stockage.supprimer_posture(posture_id):
            raise HTTPException(404, "Posture introuvable.")
        moteur.recharger()

    @app.get("/api/reglages")
    def reglages():
        return stockage.reglages()

    @app.put("/api/reglages")
    def modifier_reglages(demande: Reglages):
        resultat = stockage.modifier_reglages(demande.model_dump())
        moteur.recharger()
        return resultat

    @app.post("/api/test-assombrissement", status_code=204)
    def tester():
        moteur.tester_assombrissement()

    @app.post("/api/fausse-alerte")
    def fausse_alerte():
        try:
            return moteur.signaler_fausse_alerte()
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.get("/api/bilan")
    def bilan():
        return moteur.bilan()

    @app.get("/flux.mjpg", include_in_schema=False)
    async def flux():
        async def images():
            with moteur.spectateur():
                dernier = None
                while True:
                    apercu = moteur.apercu()
                    if apercu and apercu[0] != dernier:
                        dernier = apercu[0]
                        yield b"--image\r\nContent-Type: image/jpeg\r\n\r\n" + apercu[1] + b"\r\n"
                    await asyncio.sleep(0.05)

        return StreamingResponse(images(), media_type="multipart/x-mixed-replace; boundary=image")

    return app
