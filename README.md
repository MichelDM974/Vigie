# Vigie

Surveillance de la posture par la webcam, sur un bureau Linux (GNOME) : quand on reste
avachi trop longtemps, l'écran s'assombrit peu à peu, et redevient normal dès qu'on se
redresse.

## Le concept

Une remarque ou une notification s'ignore vite ; un écran qui baisse, beaucoup moins.
Vigie tourne en tâche de fond dès l'ouverture de session et compare en permanence la
posture à des **postures de référence que l'utilisateur enregistre lui-même** : droit au
clavier, adossé en lisant, tourné vers le second écran… Tant qu'on ressemble à l'une
d'elles, rien ne se passe. Au-delà de quelques secondes d'écart continu (10 au plus), un
voile sombre descend sur l'écran, et il se lève dès que la posture redevient correcte.

## Approche technique

- **Points du corps** : [MediaPipe Pose](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker)
  (modèle *full*, sur le processeur) repère le nez, les yeux, les oreilles et les
  épaules, 5 fois par seconde.
- **Signaux de posture** : une caméra de face ne voit pas la courbure du dos, seulement
  ses conséquences. Vigie en tire six rapports sans unité : tête et nez au-dessus des
  épaules, hauteur de la tête dans l'image, proximité de l'écran, tête en avant du buste,
  inclinaison des épaules. Ils sont lissés par une médiane glissante sur 1 s.
- **Comparaison** : chaque signal est ramené à sa tolérance. La posture de référence la
  plus proche fait foi, et seuls comptent les écarts dans le mauvais sens : se tenir plus
  droit que sa référence n'est jamais puni.
- **Alerte** : il faut 10 s d'écart continu (réglable de 0 à 10 s) avant que le voile ne
  descende, en 3 s (réglable de 0 à 10 s). Un redressement d'une seconde ne remet pas le compte à zéro, mais éclaircit
  aussitôt l'écran.
- **Assombrissement** : sous Wayland, une application ne peut pas se placer au-dessus de
  tout, et le rétroéclairage des écrans externes ne se règle pas par logiciel. Une petite
  extension GNOME Shell pose donc un voile sur tous les écrans. Les clics le traversent,
  et il couvre aussi les fenêtres plein écran. Le service lui parle par D-Bus. Si
  l'extension reste 6 s sans nouvelles, elle retire le voile : un service planté ne laisse
  jamais l'écran sombre.

Côté code : un service Python (FastAPI, OpenCV, MediaPipe) lancé par systemd à
l'ouverture de session, une page HTML/JS sans framework, la base SQLite `data/vigie.db`,
et l'extension en JavaScript (GJS, GNOME Shell 49-50).

## Fonctionnalités

- Page locale (http://127.0.0.1:8030) :
  - aperçu de la caméra en miroir avec les points suivis ;
  - état en direct et écart de chaque signal ;
  - enregistrement des postures de référence (compte à rebours, puis 3 s de capture) ;
  - bilan du jour : temps passé droit, avachi, absent et en pause, et temps avachi
    réparti par cause (le signal qui dépassait le plus).
- Icône dans la barre du haut : état, interrupteur de surveillance, ouverture de la page.
- Fausse alerte : écran assombri alors qu'on se tient droit → un clic (menu de l'icône,
  page ou commande) retire le voile jusqu'au prochain redressement et note les mesures
  du moment, de quoi recaler les tolérances sur les vraies erreurs.
- Pause qui libère vraiment la caméra, pour les visios (sous Linux, une seule application
  peut filmer à la fois).
- Réglages : tolérance générale, délai avant d'assombrir, durée d'assombrissement,
  assombrissement maximal, bouton de test.
- Vie privée : aucune image n'est enregistrée (seulement les mesures des postures de
  référence et des fausses alertes, et le temps passé dans chaque état). La page n'écoute que sur 127.0.0.1.

## Installation

Prérequis : Linux avec GNOME Shell 49 ou 50 (Wayland), Python 3.14, une webcam.

```bash
scripts/installer.sh
```

Le script :

1. crée l'environnement Python et y installe les dépendances aux versions figées de
   `constraints.txt` ;
2. copie et active l'extension GNOME, et réactive les extensions utilisateur si GNOME
   les a toutes coupées (il le fait après un plantage de GNOME Shell au démarrage) ;
3. installe le service systemd utilisateur `vigie.service` et le démarre.

À la première installation, fermer puis rouvrir la session une fois : sous Wayland, GNOME
ne charge une nouvelle extension qu'à l'ouverture de session. Ouvrir ensuite
http://127.0.0.1:8030 et enregistrer au moins une posture de référence.

Le script est relançable après une mise à jour. `scripts/desinstaller.sh` retire le
service et l'extension, mais garde `data/`.

Commandes utiles, par exemple pour un raccourci clavier GNOME :

```bash
PYTHONPATH=src .venv/bin/python -m vigie basculer   # pause ↔ reprise
PYTHONPATH=src .venv/bin/python -m vigie fausse-alerte   # « je suis droit »
PYTHONPATH=src .venv/bin/python -m vigie etat
```

Développement :

```bash
.venv/bin/pip install -r requirements-dev.txt -c constraints.txt
.venv/bin/pytest -q
```
