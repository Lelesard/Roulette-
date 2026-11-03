# Capture diagnostic v2

Le premier correctif n'a pas résolu le gel signalé sur le PC Windows. Cette
version instrumente la capture pour établir la cause ; elle ne prétend pas la
résoudre sans le journal du PC concerné.

1. Fermez toutes les anciennes fenêtres du Tracker.
2. Extrayez le ZIP dans un nouveau dossier.
3. Exécutez installer_windows.bat puis lancer_tracker.bat de ce dossier.
4. Vérifiez le titre : « Tracker Roulette — capture diagnostic v2 ».
5. Démarrez la capture Brave. Après le gel, attendez au moins 5 secondes.
6. Dans Diagnostics, cliquez « Exporter le journal de capture ».
7. Joignez le fichier capture-diagnostic.txt à la conversation.

Le journal enregistre l'étape de capture, la publication et la réception des
images, les erreurs avec leur trace et les interruptions de plus de 3 secondes.
Il contient le chemin local du programme, mais aucune image, URL ni titre Brave.
Il est limité à deux fichiers de 2 Mo. La capture ne redémarre pas automatiquement
une opération Windows bloquée. Si l'interface entière ne répond plus, récupérez
le journal via Win+R : %LOCALAPPDATA%\RouletteTracker puis capture-diagnostic.log.

Validation Linux avec capture simulée : 24 tests, dont l'alerte de gel, la reprise
après une alerte et la journalisation d'une erreur d'affichage. La capture réelle
Windows nécessite toujours le journal de votre machine.
