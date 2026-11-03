# Correctif de capture du 3 novembre 2026

## Installer cette version

Fermez le Tracker. Extrayez cette archive dans un nouveau dossier. Lancez
`installer_windows.bat`, puis `lancer_tracker.bat`. Python 3.11 ou 3.12 64 bits
avec le lanceur `py` est nécessaire. Un ancien EXE n'utilisera pas ces sources.
Les sessions existantes restent dans leur base utilisateur, hors de ce dossier.

Dans Direct : sélectionnez Brave, choisissez 25 ou 30 FPS et cliquez Démarrer.
Le compteur « Image » doit augmenter. La capture exige toujours que Brave soit
visible sans fenêtre devant. Le FPS cible ne garantit pas le FPS réellement obtenu.

## Changements

La capture ne dépend plus d'un accusé de réception de l'interface. Le worker
remplace une unique image en mémoire, récupérée par un minuteur de l'interface.
Une interface momentanément occupée ne bloque plus les acquisitions et ne crée
pas une file d'images anciennes. MSS reste exclusivement dans son thread ; seuls
les accès à cette image partagée utilisent un verrou court.

L'aperçu affiche un compteur, les FPS et l'âge de l'image. Une exception de mise
à jour est affichée au lieu de rester silencieuse. Le maximum réglable passe de
20 à 30 FPS (anciennement le code imposait aussi cette limite de 20).

## Vérification et limites

22 tests réussis sous Linux avec Qt hors écran. Le test de capture utilise un
bureau simulé dont les pixels changent à chaque acquisition. Il vérifie plusieurs
images successives, l'acquisition pendant une pause de l'interface, la reprise
sur une image récente, l'arrêt, le redémarrage et l'exécution de la capture dans
un thread distinct. Le test précédent s'arrêtait à la première image.

Le gel signalé sous Windows n'a pas été reproduit sur un bureau Windows réel.
Le mécanisme d'attente fragile a été supprimé ; la cause exacte sur la machine
de l'utilisateur n'est donc pas établie. La fluidité réelle doit être vérifiée
avec Brave sous Windows. Aucun suivi physique fiable n'est ajouté par ce correctif.
