# Capture corrigée v3 — 3 novembre 2026

## Installation

Fermez toutes les fenêtres du Tracker. Extrayez ce ZIP dans un nouveau dossier.
Exécutez installer_windows.bat puis lancer_tracker.bat. Le titre doit indiquer
« Tracker Roulette — capture corrigée v3 ». Un ancien EXE ne chargera pas ces
sources. Les sessions restent dans la base utilisateur habituelle.

## Erreur identifiée

La trace Windows fournie montre les attributs srcdc et bmp manquants dans
threading.local à la capture et à la fermeture de MSS. Les ressources GDI de MSS
ne peuvent pas être partagées entre contextes de thread Python. Le premier appel
direct fonctionne mais les callbacks Qt suivants peuvent utiliser un état de
thread Python transitoire. Vérifier seulement l'identifiant natif du thread ne
suffit donc pas à vérifier la conservation de ces ressources.

## Correction

Une boucle dans un threading.Thread permanent possède MSS durant toute la session.
La création, toutes les acquisitions et la fermeture ont lieu dans cette même
pile Python, sans callbacks QTimer pour les acquisitions. L'interface conserve
son minuteur de présentation et la boîte d'une seule image récente. L'arrêt
réveille la boucle via Event et attend sa fermeture ; les erreurs de fermeture
sont signalées sans masquer la panne d'origine ni conserver l'objet cassé.
Le journal et l'export depuis Diagnostics sont conservés.

## Vérification

25 tests passent sous Linux, plus le test de lancement hors écran. Le nouveau
test modélise les handles srcdc/bmp avec threading.local, vérifie plusieurs
captures, la fermeture dans le thread de création, les redémarrages et la
récupération après une panne simulée. Aucun essai réel de capture Windows n'a été
exécuté ici. La trace utilisateur établit le problème de ressources de thread ;
la fluidité et la disparition du gel restent à confirmer sur son PC.
