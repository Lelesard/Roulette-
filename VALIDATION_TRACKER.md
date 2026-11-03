# Validation du Tracker Roulette

État de livraison au 3 novembre 2026. Environnement de développement : Linux x86-64, Python 3.12.14, PySide6 6.8.3, OpenCV 4.11, NumPy 2.2.6. Vérifications exécutées : **22/22 tests du tracker réussis**, **17/17 tests du programme existant réussis** (interface existante sous Xvfb), contrôle statique des symboles Python réussi et lancement/fermeture Qt avec base temporaire réussi. Aucune étape Windows n’a été exécutée.

## Périmètre réel

| Lot | Implémentation livrée | Vérification restante |
| --- | --- | --- |
| A | Neuf onglets Qt, lecture vidéo asynchrone, capture visible Brave Win32/MSS, régions manuelles, profils, Racetrack, mises et bankroll, historique paginé, import/export, SQLite, sauvegarde, scripts Windows | Capture sur Brave Windows réel, construction et démarrage EXE Windows, matériel Legion Go |
| B | Tesseract local facultatif, deux lectures stables, propositions/corrections via historique, ajout automatique activable, recoupement persistant | Lisibilité et erreurs sur les panneaux Evolution réels ; déduplication impossible pour certaines répétitions indiscernables |
| C | Candidat clair sur anneau elliptique manuel, angle/vitesse/accélération, score de continuité, rejet d’ambiguïtés, remise à zéro heuristique, point superposé, outil de benchmark | Identification bille/reflets sur vrais lancers ; suivi du rotor, géométrie automatique et traitement robuste des perspectives non implémentés |
| D | Modèle physique hors ligne gardé, journal JSON fourni par l’appelant, évaluateur avec chronologie et référence aléatoire, intervalle Wilson | Fermeture des mises non détectée ; calibration et incertitude empirique absentes ; aucune estimation en direct ; aucune performance réelle établie |
| E | Pages défilantes, contrôles agrandis, travail asynchrone borné, build et test de démarrage scriptés | Optimisation et mesures sur Legion Go, tests de stabilité prolongés, EXE Windows final à générer et vérifier |

Les vidéos « Deutsches Roulette » (~672,5 s) et « VIP Roulette (1) » (~648 s), annoncées en 640 × 360 à 30 FPS, **ne sont pas jointes**. Nombre de lancers réels évaluables : **0**. Taux de détection, faux positifs, suivi continu, précision des secteurs et avantage financier sur ces vidéos : **non mesurés**, et non zéro pour cent. Aucune prédiction gagnante n’est annoncée.

## Tests logiciels

La suite `tests_tracker` couvre paiements et zéro, voisins et bouclage, montants invalides, opérations et corrections, séparation des sessions, reprise après fermeture, règlement atomique des mises, annulations auditées, import invalide atomique, exports et dates, pagination, interface réelle Qt hors écran, lecture/recherche d’une vidéo synthétique, annotations, sélection manuelle de régions, persistance des profils, capture avec source simulée, retours entre QThreads, rejet des réponses périmées, OCR avec Tesseract sur un panneau synthétique, doublons et résultats répétés, suivi d’un point synthétique et perte/coupe caméra, garde-fous du modèle et de l’évaluateur, benchmark sans taux inventé.

Une image synthétique lisible ne représente pas un panneau Evolution réel. Un point blanc synthétique ne démontre pas l’identification de la bille. La capture simulée teste le chemin logiciel et les fils d’exécution, pas les appels Win32 sur une vraie fenêtre. Les tests d’interface interceptent également les exceptions asynchrones Qt pour éviter un faux succès du runner.

## Modèle physique expérimental

Le modèle travaille dans le plan du cylindre rectifié ; angles en radians, sens horaire. Le rotor doit fournir l’angle réel de la poche zéro et sa vitesse indépendamment de la bille. Les paramètres de libération, de vol et de rebond doivent être calibrés sur un jeu de développement séparé.

Pendant la phase de décélération, `θb(t) = θb0 + ωb0 t + 0,5 αb t²`. L’instant de libération est le premier instant positif auquel la vitesse atteint la vitesse de libération calibrée. Une durée de vol calibrée est ensuite ajoutée avec vitesse angulaire de libération constante, puis un décalage moyen de rebond. Le rotor suit `θr(t) = θr0 + ωr t`. L’angle relatif final est converti en position dans l’ordre européen ; le secteur retourné contient 9, 15 ou 19 numéros autour de cette position.

Ce modèle simplifie fortement la dynamique : il ne résout pas le contact avec les déflecteurs, le mouvement radial, une accélération variable du rotor ou la distribution multimodale des rebonds. L’incertitude est **fournie par une calibration externe**, pas déduite artificiellement du score de continuité. Elle doit englober erreurs de mesure, extrapolation et rebonds.

`estimate()` refuse notamment une calibration absente, un score inférieur à 0,90, un dernier échantillon âgé de plus de 100 ms, des horodatages futurs ou postérieurs à la fermeture, une décélération de signe incohérent, une libération hors horizon ou une incertitude supérieure à la demi-largeur du secteur. Ces règles ne valident ni les paramètres ni le modèle. L’interface n’appelle pas ce modèle car le rotor et les paramètres calibrés font défaut.

## Protocole sur les deux vidéos

1. Vérifier dimensions, cadence et durée des fichiers réels. Définir des lancers complets et identifier coupes, zooms, visibilité de la bille, repère rotor, fermeture des mises et résultat. Vérifier manuellement les horodatages.
2. Séparer les lancers de développement et de validation **avant** le réglage des seuils ou du modèle. Garder des lancers complets dans un seul ensemble ; ne pas mélanger des frames adjacentes d’un même lancer entre ensembles.
3. Annoter une vérité terrain indépendante : centre de bille lorsqu’elle est visible, absence lorsqu’elle ne l’est pas, angle du repère rotor si observable. Définir à l’avance la tolérance de localisation et les critères de lancer évaluable. Inclure des frames avec reflets et sans bille visible.
4. Exécuter le benchmark sans retoucher les paramètres sur la validation. Rapporter rappel de localisation, précision, faux positifs, plus longue durée continue, latence p50/p95 et nombre d’images annotées. Les périodes non annotées ne doivent pas compter comme succès.
5. Enregistrer une prédiction par lancer **avant** la fermeture, avec le maximum des temps de toutes les images utilisées, l’heure de création, le secteur et la version des paramètres. Sauvegarder les fichiers et leurs empreintes avant de lire les résultats ; le rapport JSON seul ne peut pas prouver l’absence de fuite temporelle.
6. Ajouter indépendamment fermeture et résultat après coup. Rapporter lancers inclus/exclus, raisons d’exclusion, taux de couverture et taux de succès par taille de secteur. Comparer à `9/37 = 24,32 %`, `15/37 = 40,54 %`, `19/37 = 51,35 %`. Ne pas choisir le meilleur secteur a posteriori.
7. Publier aussi les échecs et intervalles d’incertitude. Une proportion observée supérieure à la référence sur peu de lancers ne démontre pas d’avantage. Un calcul de ROI exige les mises réellement déclarées.

## Benchmark de localisation

Créer un manifeste, par exemple `validation-deutsches.json` :

```json
{
  "video": "Deutsches Roulette.mp4",
  "split": "validation",
  "wheel_roi": [0.1, 0.1, 0.8, 0.8],
  "tolerance_pixels": 8,
  "frames": [
    {"frame": 120, "ball_xy": [310, 72]},
    {"frame": 121, "ball_xy": [317, 73]},
    {"frame": 122, "ball_xy": null}
  ]
}
```

**Cet exemple est factice.** Remplacer toutes les coordonnées et annotations par une vérité terrain réelle. Les `ball_xy` sont en pixels de l’image vidéo entière ; `null` signifie bille non visible. La région est normalisée. Les chemins relatifs sont résolus par rapport au manifeste. Les frames sont indexées à partir de zéro.

```powershell
.\.venv-windows\Scripts\python.exe -m tracker.benchmark validation-deutsches.json --output rapport-localisation.json
```

Le seuil de score est fixé à 0,80 pour ce benchmark ; un candidat sans vitesse estimable ne compte pas comme localisation acceptée. Une localisation fausse ou hors tolérance compte comme faux positif ; une bille annotée non correctement localisée compte comme manquée. Le suivi continu ne cumule que des frames consécutives correctement localisées. La latence mesure le recadrage et l’analyse, hors décodage ; le débit global inclut le décodage. Les métriques sur le rotor ne sont pas disponibles.

## Évaluation des secteurs

L’évaluateur consomme une liste JSON de lancers indépendants. Exemple de structure **factice**, à ne pas utiliser comme donnée réelle :

```json
[
  {
    "video": "nom-video.mp4",
    "spin_id": "lancer-001",
    "split": "validation",
    "closes_at": 30.0,
    "result_seconds": 45.0,
    "result": 32,
    "prediction": {
      "last_frame_seconds": 28.0,
      "created_seconds": 28.05,
      "center": 0,
      "size": 9,
      "numbers": [12, 35, 3, 26, 0, 32, 15, 19, 4]
    }
  }
]
```

```powershell
.\.venv-windows\Scripts\python.exe -m tracker.evaluation lancers-validation.json --output rapport-secteurs.json
```

Le code exige `dernier échantillon ≤ création < fermeture ≤ résultat`, rejette les doublons de lancer et les données non étiquetées validation, vérifie l’ordre et le contenu du secteur. Il donne effectifs, succès, référence et intervalle de Wilson à 95 %. Zéro lancer produit un taux `null`, jamais un succès inventé. Les déclarations de temps et de résultats doivent être auditées sur les vidéos sources.

## Recette Windows / Legion Go à réaliser

- Installer dans un dossier comportant des espaces et accents ; exécuter les tests puis `build_windows.bat`.
- Exécuter le dossier compilé sur Windows 11 sans Python ; vérifier lecture MP4, fermeture et reprise, banque, import/export et sauvegarde/restauration.
- Capturer une vraie fenêtre Brave avec mise à l’échelle Windows 100 %, 150 % et 200 %, déplacement entre écrans, minimisation, fermeture, occultation et vidéo noire. Vérifier les messages et refaire le calibrage.
- Mesurer CPU, mémoire, FPS capturés et latence lors de sessions prolongées, sur batterie et secteur. Comparer les cibles de capture 5, 10 et 20 FPS.
- Vérifier le toucher, les barres de défilement, les petites cibles et le clavier à l’écran, en orientations paysage et portrait.

Aucun résultat de cette recette n’est revendiqué ici. Le build Windows et ses dépendances tierces ne sont pas signés par ce projet ; l’archive source n’inclut aucun logiciel propriétaire de roulette.
