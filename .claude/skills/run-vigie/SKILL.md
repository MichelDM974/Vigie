---
name: run-vigie
description: Lancer, piloter, tester et photographier Vigie (surveillance de la posture par la webcam — service Python FastAPI + MediaPipe, page locale, extension GNOME Shell). À utiliser pour démarrer le service, vérifier qu'un changement fonctionne dans l'appli réelle, prendre une capture de la page, tester l'extension, ou lancer les tests.
---

# Lancer et piloter Vigie

Service Python (`src/vigie/`, entrée `python -m vigie`) qui lit la webcam,
évalue la posture avec MediaPipe Pose et sert une page locale
(`src/static/`) ; une extension GNOME Shell
(`gnome-extension/vigie@micheldm974.github.io/`) reçoit l'état par D-Bus et
assombrit l'écran. Pas de Docker (caméra, bus de session et ouverture de
session : cf. décisions du journal).

Tous les chemins ci-dessous sont relatifs à `Vigie/`.

## Prérequis

```bash
.venv/bin/python -c "import mediapipe, cv2, fastapi; print('ok')"
```

S'il manque (machine neuve) :

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt -c constraints.txt
```

Le modèle de pose (`models/pose_landmarker_full.task`, non versionné) se
télécharge au premier lancement du service.

## Lancer (chemin agent)

```bash
.venv/bin/python .claude/skills/run-vigie/driver.py serve &      # port 8031
.venv/bin/python .claude/skills/run-vigie/driver.py smoke
```

`serve` tourne avec une **caméra factice** (image grise, personne), **sans
message à l'extension** et sur une base jetable (`--data`, défaut
`/tmp/vigie-driver`) : il ne dispute pas la webcam au vrai service et
n'assombrit jamais le bureau. `smoke` (stdlib seule, code 1 au moindre
échec) enregistre une posture, bascule la pause, etc. : il refuse de
viser le port 8030 du vrai service.

Arrêter : `fuser -k 8031/tcp`.

## Capture d'écran

```bash
.venv/bin/python .claude/skills/run-vigie/driver.py ui --out /tmp/vigie-captures
```

Chromium de `~/.cache/ms-playwright` en `--screenshot`. **La regarder** :
un badge « Démarrage… » ou « Service arrêté » = échec. Ne jamais
photographier la page du vrai service sans le demander : l'aperçu montre
l'utilisateur.

## Lancer (chemin humain — vraie caméra, vraies données)

"Lance Vigie" = ce chemin-ci. Le service tourne en permanence sous systemd
utilisateur, lancé à chaque ouverture de session :

```bash
systemctl --user status vigie.service            # tourne-t-il ?
systemctl --user restart vigie.service           # appliquer un changement de code Python
journalctl --user -u vigie.service -n 50
curl -s localhost:8030/api/etat
```

Page : http://127.0.0.1:8030 (écoute sur 127.0.0.1 seulement). Écrit dans
`data/vigie.db` (postures de référence, réglages, bilans par minute).

Installation ou mise à jour de l'unité et de l'extension :
`scripts/installer.sh` (relançable) ; `scripts/desinstaller.sh` garde
`data/`. Pause pour une visio : icône de la barre du haut, bouton de la
page, ou `.venv/bin/python -m vigie basculer` (PYTHONPATH=src).

## Tester l'extension sans se déconnecter

Une extension neuve ou modifiée ne se recharge qu'à l'ouverture de session
(Wayland). Pour l'éprouver avant : GNOME Shell headless dans une session
D-Bus isolée (aucun effet sur le bureau réel), la copie de l'extension
dans un `XDG_DATA_HOME` temporaire, puis `gdbus call … Signaler`.
Ingrédients qui ont fait marcher le test du 29/09/2026 :

- `dbus-run-session -- env -u DISPLAY -u WAYLAND_DISPLAY -u GSETTINGS_SCHEMA_DIR -u GTK_PATH -u GIO_MODULE_DIR GSETTINGS_BACKEND=keyfile XDG_DATA_DIRS="$XDG_DATA_DIRS_VSCODE_SNAP_ORIG" HOME=… XDG_DATA_HOME=… XDG_CONFIG_HOME=… XDG_RUNTIME_DIR=/run/user/1000/vigie-test …`
- dans cette session : `gsettings set org.gnome.shell enabled-extensions "['vigie@micheldm974.github.io']"`
  puis `gnome-shell --headless --wayland --no-x11 --virtual-monitor 1280x720 --wayland-display=vigie-test` ;
- attendre `GetExtensionInfo` → `state` = 1 (6 = chargée mais pas activée) ;
- captures : `org.gnome.Shell.Screenshot` n'accepte que les appelants qui
  possèdent `org.gnome.SettingsDaemon.MediaKeys` (ou le portail GNOME) :
  un petit script gjs qui prend ce nom sur le bus isolé.

## Tests

```bash
.venv/bin/pytest -q
```

Sans caméra ni modèle : le moteur est testé avec des doublures
(`tests/conftest.py`, classe `Banc`).

## Pièges

- **Une seule appli à la fois peut filmer** : tant que le service tourne,
  une visio (ou Snapshot, ou un script de test) ne trouve pas la caméra, et
  réciproquement le service affiche « caméra indisponible ». La pause
  ferme vraiment le périphérique. `fuser /dev/video0` montre qui la tient
  (PipeWire l'a toujours ouverte sans filmer : sans effet).
- **Snap de VS Code** : son terminal exporte `GSETTINGS_SCHEMA_DIR`,
  `GIO_MODULE_DIR`, `XDG_DATA_DIRS`… de la snap. `gsettings` y lit de
  mauvais schémas ou n'écrit nulle part ; `gnome-shell` y plante. L'installeur
  passe par `dconf` ; pour un test, nettoyer l'environnement (ci-dessus).
- **`pkill -f` sur un motif présent dans sa propre commande tue le shell** :
  arrêter une instance par son port (`fuser -k 8031/tcp`).
- **Chemin de socket Wayland limité à 108 octets** : un
  `XDG_RUNTIME_DIR` dans le scratchpad est trop long, prendre
  `/run/user/1000/<nom>` et le supprimer après.
- **Lecture caméra à 30 images/s = ~50 % d'un cœur** en conversion seule :
  la caméra est réglée à 10 images/s (`Camera(images_par_seconde=…)`).
  Service complet ≈ 20 % d'un cœur.
- **Pièce sombre** : MediaPipe ne voit personne, état « absent », aucune
  alerte. Diagnostiquer par la luminosité moyenne d'une image (un nombre),
  pas en regardant l'image.
- **Tolérances des signaux** (`posture.SIGNAUX`) : calées sur une séance
  réelle (commentaire au-dessus). Premier indice du signal trop serré :
  `causes` de `/api/bilan` (temps avachi par signal qui dépassait le plus,
  table `causes` minute par minute, comptée depuis le 29/09/2026 23:30).
  Pour recaler, ne pas lire la page à l'œil :
  relever `mesures` de `/api/etat` (~5/s) pendant des phases étiquetées
  (correct plusieurs minutes, puis chaque façon de s'avachir), et recalculer
  hors ligne les écarts bruts aux postures de `data/vigie.db` (lecture seule)
  pour tester plusieurs jeux de tolérances sur les mêmes données. La hauteur
  est le signal le plus serré : elle dépend aussi de la place de la caméra
  et de la chaise (les déplacer = ré-enregistrer les postures).

## Dépannage

| Symptôme | Cause et correctif |
|---|---|
| Bandeau « extension GNOME ne répond pas » | Extension pas encore chargée : fermer et rouvrir la session après `installer.sh`. Vérifier `gnome-extensions info vigie@micheldm974.github.io`. |
| Bandeau « GNOME a désactivé les extensions utilisateur » | `disable-user-extensions` à `true` : mis par `org.gnome.Shell-disable-extensions.service` après un plantage du Shell au démarrage (arrivé le 02/09/2026), jamais remis à `false` par GNOME. `dconf write /org/gnome/shell/disable-user-extensions false` (ou relancer `installer.sh`) : effet immédiat si le Shell connaît déjà l'extension, sinon rouvrir la session. |
| « Caméra indisponible » | Une autre appli filme (`fuser /dev/video0`), ou webcam débranchée. Le service réessaie toutes les 5 s. |
| L'écran reste sombre | Impossible par conception (retrait après 6 s sans signal) ; sinon désactiver l'extension : `gnome-extensions disable vigie@micheldm974.github.io`. |
| `smoke` : `rien ne répond` | `serve` non lancé ou autre `--port`. |
| `ui` : `Aucun chromium` | Cache playwright vide : `playwright install chromium` depuis un venv jetable. |
| Port 8031 déjà pris | Un `serve` traîne : `fuser -k 8031/tcp`. |
