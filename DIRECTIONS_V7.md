# Directions bille et rotor v7 — 4 novembre 2026

Cette version affiche séparément le sens du candidat bille et celui du rotor.
Les libellés **horaire à l’écran** et **antihoraire à l’écran** décrivent les
pixels reçus par le Tracker. Si le casino diffuse une image en miroir, le sens
physique réel est inversé.

## Bille

Le suivi multi-hypothèses de la v6 déroule l'angle de chaque candidat lumineux.
Le signe de sa vitesse angulaire donne le sens uniquement après une trajectoire
continue et cohérente. Le point reste un candidat non validé : un reflet mobile
peut encore être suivi à la place de la bille.

## Rotor

La zone de roue est transformée en image polaire. Le module utilise la bande
centrale contenant les repères des poches, retire l'éclairage lent et compare le
déplacement angulaire entre images. Il attend cinq mesures concordantes, rejette
les décalages radiaux importants et affiche un score de confiance. Une roue
immobile, uniforme ou ambiguë ne produit aucun sens.

Le rotor est mesuré indépendamment du candidat bille, mais cette v7 ne reconnaît
pas la poche zéro et ne connaît pas l'angle absolu du rotor. Elle ne déduit aucun
numéro futur et conserve **Aucune estimation fiable**.

## Vérification

La suite contient 36 tests. Les tests de direction font tourner une texture de
rotor asymétrique dans les deux sens et vérifient le signe mesuré. Une image
immobile vide doit être rejetée. Les tests précédents couvrent aussi la bille,
les reflets fixes, les images manquantes, les changements de caméra, les threads
Qt et la capture persistante. La vidéo fournie dépasse la limite de transfert de
32 Mio de l'environnement ; la qualité sur cette vidéo et sous Windows doit donc
être vérifiée sur la Legion Go.
