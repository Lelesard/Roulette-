# Analyse dynamique v5 — 4 novembre 2026

Cette version remplace l'hypothèse d'un angle fixe par un observateur de scène.
Il détecte les coupures caméra, recherche la roue à intervalles réguliers et
exige trois régions concordantes avant d'autoriser le suivi expérimental.

## États visibles

- **Changement de caméra** : cadre et suivi effacés immédiatement.
- **Roue candidate** : cadre orange, encore inutilisable pour le suivi.
- **Roue stable** : cadre vert, utilisable par le candidat bille expérimental.
- **Roue momentanément masquée** : dernier cadre conservé au maximum 1,5 seconde.
- **Autre vue ou roue non visible** : cadre retiré et suivi suspendu.

La case **Analyse automatique** est activée par défaut et son choix est mémorisé.
Le cadre dynamique n'est jamais écrit dans les profils. Les calibrages manuel et
automatique v4 restent disponibles pour le diagnostic.

## Architecture et validation

L'observateur de scène possède son propre QThread afin de ne pas bloquer la
capture ni l'interface. Une époque de caméra invalide les résultats d'analyse
retardés après une coupure. Le suivi de candidat bille peut fonctionner en Direct
uniquement lorsqu'une zone stable existe.

31 tests passent sous Linux avec Qt hors écran. Ils couvrent la stabilité,
l'occultation courte, la perte de roue, la coupure caméra, le caractère éphémère
du cadre et la réinitialisation du suivi. Sur une image synthétique 1920×1032,
l'analyse de scène prend environ 23 ms sur la machine de test et s'exécute environ
deux fois par seconde.

Limites : il s'agit d'une analyse géométrique OpenCV, pas encore d'un modèle IA
entraîné. La robustesse sur les angles réels Evolution doit être mesurée sur le
Legion Go. Aucun suivi de rotor ni estimation de résultat n'est validé.
