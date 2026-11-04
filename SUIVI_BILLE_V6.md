# Suivi bille expérimental v6 — 4 novembre 2026

Cette version ajoute la case **Bille expérimentale** dans Direct. Le traitement
ne démarre que lorsque l'analyse dynamique v5 a confirmé une zone de roue stable.

L'ancien algorithme exigeait un unique point blanc et abandonnait dès qu'un reflet
était présent. La v6 conserve jusqu'à 24 trajectoires candidates, les associe par
angle, rayon et vitesse, puis ajuste une trajectoire angulaire. Les candidats
immobiles et incohérents sont rejetés. Deux images manquantes peuvent être
traversées sans produire de fausse position. Une coupure caméra invalide les
résultats en attente et réinitialise le suivi.

Validation dans l'environnement Linux : tests avec bille synthétique, plusieurs
reflets fixes, perte de deux images, reprise, mesure de vitesse et changement de
caméra. La suite complète et le démarrage Qt hors écran doivent passer avant
publication.

Limites : aucune vidéo réelle n'a pu être importée à cause de la limite de 32 Mio.
Un point suivi reste un candidat lumineux. Les reflets mobiles et les éléments du
rotor peuvent produire un faux suivi. Aucun rotor ni résultat final ne sont
mesurés ; aucune estimation fiable n'est produite.
