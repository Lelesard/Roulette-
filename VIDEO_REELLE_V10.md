# Validation sur vidéo réelle v10 — 4 novembre 2026

La vidéo fournie depuis la Legion Go dure 29,03 secondes, contient 871 images
H.264 en 1248 × 692 à 30 FPS et montre la roue sans changement de caméra. La
détection automatique retrouve une région stable d'environ 346 × 289 pixels,
avec des scores géométriques compris entre 0,88 et 0,98 sur les images sondées.

L'examen visuel montre que la bille et le rotor tournent dans le même sens sur
cette table automatique. La règle v9 exigeant des sens opposés est donc invalide
pour cette source. Elle est remplacée par une séparation de vitesses : le
candidat doit atteindre au moins 0,7 rad/s et cinq fois la vitesse du rotor.

Le passage hors ligne analyse une image sur deux, soit 436 observations. Le
rotor produit 192 mesures et le candidat bille 72 mesures. Trente-six images
possèdent simultanément les deux vitesses ; toutes dépassent le seuil de
séparation, avec un rapport bille/rotor compris entre 8,3 et 62,5. Onze images
acceptées réparties de 13,2 à 27,3 secondes ont été contrôlées visuellement : le
point superposé se trouve sur la bille visible dans les onze cas.

Ces nombres décrivent cette seule vidéo et ne constituent pas un taux de
précision général. La vidéo n'a pas d'annotations indépendantes image par image,
la bille rapide n'est pas mesurée continuellement au début du lancer et d'autres
tables ou éclairages peuvent produire des reflets différents. Le résultat futur
et la poche zéro ne sont toujours pas déterminés.

Validation logicielle : 39 tests passent sous Linux avec Qt hors écran. Les cas
testés couvrent l'attente du rotor, le rejet d'une vitesse synchronisée,
l'acceptation d'une bille plus rapide dans le même sens ou dans le sens opposé,
la continuité du rotor, les changements de caméra et la capture persistante.
