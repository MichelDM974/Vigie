# Profil de proposition : Vigie

Ce qu'est une bonne piste pour Vigie. Lu par le bouton « Proposer des
pistes » de cdc (`centre-de-controle/scripts/machine.py`) : une règle de
proposition se change ici, pas dans sa consigne.

Le bouton lit ce fichier par programme : garder les quatre titres de rubrique
tels quels et n'y écrire que des puces ; dans « Champs en plus », la forme
`` `nom` (Libellé) : ce qu'on y met ``. Ces deux paragraphes ne sont pas lus.

## Priorités

- Une posture corrigée sans gêner : détecter les vrais avachissements et
  faire baisser les fausses alertes.
- Parler au PC (#3) et les gestes (#4) sont en suspens depuis le 07/11/2026
  (choix de l'utilisateur) : ne pas les proposer comme la suite.
- Tout reste sur le PC : aucune image enregistrée, aucun service en ligne.

## Bonne piste

- Elle tourne en local sur le PC, à côté du reste, au rythme de l'analyse
  (5 images par seconde, 1 quand personne n'est là ; la caméra en livre ~5),
  sans alourdir le processeur (~25 % d'un cœur déjà pris quand on est devant).
- Elle garde les choix d'alerte : l'écran qui s'assombrit, ni notification
  ni son.
- Elle dit comment on vérifiera le gain, comme le relevé étiqueté du
  30/09/2026.

## Champs en plus

- `mesure` (Mesure) : comment on vérifie le gain (relevé étiqueté, fausses
  alertes signalées, charge du processeur) et ce qu'on en attend.
