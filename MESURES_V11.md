# Enregistreur de lancers v11 — 4 novembre 2026

La v11 transforme les mesures temporaires de la v10 en séries exportables. Un
lancer commence à la première direction de bille validée par une vitesse
indépendante du rotor. Les deux secondes précédentes sont ajoutées pour conserver
le démarrage du rotor. Le lancer se termine après cinq secondes sans bille
validée, lors d'un changement de caméra, d'un arrêt de capture, d'une fin
manuelle ou de la fermeture de l'application.

Chaque échantillon contient : temps relatif et temps source, session, type de
source, époque caméra, direction/vitesse/accélération/confiance de la bille,
point candidat, direction/vitesse/confiance du rotor et messages de diagnostic.
Les images, URL, titres de fenêtre et identifiants casino ne sont pas stockés.

L'enregistrement actif est sauvegardé environ chaque seconde dans
`%LOCALAPPDATA%\RouletteTracker\roulette-measurements-v11.json`. Une interruption
de l'application est marquée au prochain démarrage. Diagnostics permet de
terminer manuellement le lancer et d'exporter un JSON partageable. Un résultat
saisi manuellement est lié au dernier lancer sans résultat de la même session.

Sur la vidéo réelle de 29,03 secondes, le passage hors ligne crée un seul lancer
de 17,8 secondes avec 268 échantillons, dont 36 mesures bille validées et 135
mesures rotor. Le préhistorique commence à 11,2 secondes et l'enregistrement se
prolonge jusqu'à la fin de la vidéo. Ces nombres valident le chemin logiciel sur
cette source ; ils ne constituent pas une précision générale.

Validation : 41 tests réussissent sous Linux avec Qt hors écran. Les nouveaux
tests couvrent préhistorique, fin automatique, résultat manuel, séparation des
sessions et caméras, export sans données internes et reprise après interruption.
La compilation Python et le démarrage Qt hors écran sont également vérifiés.
