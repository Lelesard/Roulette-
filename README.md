# Tracker Roulette local — Windows 11

Application de bureau en français : Python 3.11/3.12, PySide6, OpenCV, NumPy, MSS et SQLite. Source et traitements locaux, sans abonnement. Aucune connexion applicative au casino, aucun identifiant demandé, aucune mise automatique.

Le **Lot A est implémenté**. Les ajouts OCR, recherche de candidat bille et modèle physique sont **expérimentaux et partiels**. La capture Win32 est codée mais n’a pas été essayée sur Windows dans cet environnement Linux. Aucun taux de prédiction réel n’est établi. Voir `VALIDATION_TRACKER.md` pour le périmètre exact.

## Calibrage automatique du cylindre

Dans **Direct** ou **Vidéos et tests**, affichez une image où la roue est entière,
puis cliquez sur **Détecter le cylindre**. Le Tracker cherche plusieurs contours
elliptiques concentriques et affiche sa proposition en vert. Vérifiez que le cadre
contient toute la roue avant de confirmer. Une proposition refusée n'écrase pas le
calibrage existant. Si la caméra coupe la roue, si elle est trop petite ou si le
score est insuffisant, attendez une autre vue ou utilisez **Calibrer le cylindre**.

Le score affiché mesure uniquement la qualité géométrique du cadre. Il ne prouve
pas que la bille ou le rotor sont détectés. Le suivi expérimental doit être
validé séparément.

## Directions expérimentales de la bille et du rotor

La case **Bille expérimentale** dans Direct active un suivi multi-hypothèses
uniquement lorsqu'une zone de roue stable existe. Le module compare jusqu'à
24 trajectoires lumineuses, favorise le mouvement cohérent et écarte les points
immobiles. Il tolère jusqu'à trois images manquantes, sans inventer de position
pendant ces images, et repart de zéro après une coupure caméra.

Le point affiché reste un **candidat lumineux non validé**. Les reflets mobiles,
les repères du rotor ou les éléments de l'interface peuvent encore être choisis.
Le score est une cohérence de trajectoire, pas une probabilité que le point soit
la bille. Lorsque la trajectoire est continue, l'interface affiche son sens.

Le même worker déroule en coordonnées polaires la bande centrale du cylindre et
mesure le déplacement de ses détails entre deux images. Après cinq mesures
concordantes, il affiche séparément le sens du rotor et son score de corrélation.
Les mesures récentes survivent aux images momentanément ambiguës. Diagnostics
conserve la dernière direction reconnue avec son âge, même lorsque la roue vient
de s'arrêter, et explique précisément pourquoi la mesure courante est rejetée.
Les sens **horaire** et **antihoraire** décrivent l'image affichée. Un flux mis en
miroir inverse leur relation avec la roulette physique. Cette mesure ne fournit
ni position absolue de la poche zéro, ni numéro ou secteur final.

Une direction de bille n'est publiée que lorsqu'une direction de rotor est
disponible sur la même image et que leurs sens sont opposés. Cette validation
croisée rejette le cas observé sur la Legion Go où un reflet ou un repère du
rotor était suivi comme bille et changeait de sens exactement avec lui. Sans
rotor indépendant, le candidat reste visible mais sa direction demeure en
attente. Cette règle réduit ce faux positif précis sans valider l'identité de la
bille face à tous les autres reflets possibles.

## Analyse dynamique des changements de caméra

La case **Analyse automatique** active un observateur de scène dans Direct. Il
analyse une image environ toutes les 550 ms dans un thread séparé. Une zone de
roue ne devient exploitable qu'après trois observations concordantes. Le cadre
orange signale une proposition en cours ; le cadre vert signale une roue stable.

Une coupure caméra réinitialise immédiatement le suivi. Lorsque la roue est
momentanément masquée, le dernier cadre est conservé pendant 1,5 seconde, puis
retiré si elle ne réapparaît pas. Ces cadres dynamiques ne sont pas enregistrés
dans le profil et ne remplacent pas un calibrage manuel. Le suivi expérimental de
candidat bille et la mesure du rotor peuvent utiliser une zone dynamique stable
en direct, mais leur identité physique reste non validée.

## Démarrage Windows

1. Installer Python **3.11 ou 3.12, 64 bits**, avec le lanceur `py`.
2. Extraire le projet dans un dossier accessible en écriture.
3. Double-cliquer sur `installer_windows.bat`. Internet est nécessaire pour télécharger les dépendances à cette étape.
4. Double-cliquer sur `lancer_tracker.bat`. L’application fonctionne ensuite localement.

Installation équivalente dans PowerShell, depuis le dossier du projet :

```powershell
py -3.12 -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install -r requirements-tracker.txt
.\.venv-windows\Scripts\python.exe tracker_main.py
```

Le script d’installation et le script de compilation essaient Python 3.11 si Python 3.12 est absent. Le code a été exécuté ici avec Python 3.12 ; la configuration 3.11 reste à vérifier.

## Utilisation

### Sessions et profils

Les neuf onglets sont Direct, Racetrack, Historique, Bankroll, Statistiques, Vidéos et tests, Tables et profils, Paramètres et Diagnostics. Les pages peuvent défiler sur un petit écran. Les boutons principaux ont une hauteur adaptée à une utilisation tactile ; l’ergonomie sur Legion Go doit être confirmée sur l’appareil.

Créer une session pour chaque table et période de travail. Les profils Deutsches Roulette et VIP Roulette sont précréés. Un profil contient les régions calibrées, le sens de lecture OCR et une note ; **aucun calibrage physique de ces tables n’est fourni**. Le nom de table d’une session ne change pas après création. Pour changer de table, créer une autre session. Les mises en attente de chaque session sont conservées séparément.

### Direct : capture visible de Brave

Sur Windows, ouvrir Brave avec la table visible, cliquer sur **Actualiser Brave**, choisir la fenêtre et démarrer. L’identification vérifie le processus `brave.exe`, pas seulement son titre. La capture MSS lit les pixels du bureau dans la zone cliente de la fenêtre. Elle ne lit ni le réseau ni le contenu interne du navigateur.

Garder Brave visible à côté du tracker et entièrement dans les écrans. Une autre fenêtre placée devant Brave sera présente dans la capture. Une fenêtre minimisée, fermée ou hors écran arrête la capture. Une vidéo protégée peut produire une image noire : aucune tentative de contournement n’est prévue. FPS et latence concernent la capture logicielle, pas le délai de diffusion du casino.

Cliquer sur **Calibrer le cylindre** puis tracer un rectangle sur l’aperçu. Pour le module vidéo expérimental, ce rectangle doit encadrer précisément l’ellipse du cylindre, sans marges inutiles. Calibrer séparément le panneau des résultats. Les régions sont sauvegardées par profil, en coordonnées relatives. **Recalibrer après un changement de caméra, de zoom ou de disposition, et lors du passage entre vidéo et Brave.** Un rectangle ne corrige pas une perspective projective complexe.

Le tableau de bord affiche derniers résultats, bankroll, jeton, mises en attente et dernier règlement déclaré. Le sens expérimental du candidat bille et celui du rotor sont affichés lorsqu'ils deviennent stables. La fermeture des mises et le résultat futur ne sont pas mesurés. Le message reste **« Aucune estimation fiable »**.

### Racetrack, jetons et règlement

L’ordre des 37 cases est celui de la roulette européenne, zéro en haut, progression horaire. Cliquer sur un numéro pour choisir ses 9, 15 ou 19 voisins contigus. Cyan : sélection manuelle ; ◆ : plein déclaré ; ● : dernier résultat. Une sélection manuelle n’est pas une estimation.

Valeurs proposées : 0,10 €, 0,50 € et 1 €. Toute valeur positive au centime est acceptée. Le nombre de jetons s’applique à chaque cible. Chaque ajout fige son montant en centimes : changer ensuite le jeton ne modifie pas les mises précédentes. Ajouter un plein, toute une zone, une chance simple, une douzaine ou une colonne. Les mises du casino restent à effectuer manuellement.

Saisir le résultat observé puis **Enregistrer et régler le tour**. Le retour brut d’un plein gagnant est 36 fois sa mise ; celui d’une chance simple 2 fois ; celui d’une douzaine ou colonne 3 fois. Le profit net du tour est la somme des retours bruts moins toutes les mises du tour. Le zéro perd sur toutes les chances simples, douzaines et colonnes ; les variantes « partage » et « prison » ne sont pas prises en charge.

Sans mise déclarée, l’ajout d’un résultat ne crée aucun mouvement financier. Le solde affiché est celui des tours réglés ; les mises en attente sont affichées séparément. Le règlement du tour et la suppression des mises en attente sont atomiques en SQLite. La fermeture conserve les mises non réglées pour la prochaine ouverture.

### Historique et statistiques

Historique paginé par 100 résultats, correction, suppression, import et export CSV/JSON. Corriger un résultat recalcule son règlement actif ; le supprimer annule ce règlement. L’audit conserve la modification. L’export ajoute couleur, parité, manque/passe (`hauteur`), douzaine, colonne et position dans le cylindre (0 à 36). La position dans le cylindre est une propriété descriptive, pas une zone prédite.

CSV : en-tête `number`, `numero` ou `numéro`. JSON : liste d’objets avec `number`. Le champ `created` est facultatif ; s’il est présent, il doit être au format ISO 8601 avec fuseau. Les exports préservent les dates lors d’une réimportation. Si la date manque, l’heure d’import UTC est utilisée. Tout le fichier est validé avant écriture. Les imports manuels sont additifs : **réimporter le même fichier crée des répétitions**. Les mises et opérations financières ne font pas partie des exports de résultats.

Statistiques : effectifs, fréquences, histogramme, séries actuelles et longueurs maximales par propriété. Le Racetrack permet de consulter les voisins. Les fréquences historiques ne prédisent pas une roulette équilibrée.

### Bankroll et sauvegarde

Enregistrer le capital initial, puis les dépôts, retraits ou ajustements signés. Ces flux n’entrent pas dans le bénéfice des tours ni dans le ROI. L’affichage distingue engagé, retours bruts, résultat net, sommes des tours bénéficiaires et pertes nettes des tours déficitaires. Le graphique montre le solde après chaque opération. Les opérations annulées restent visibles sans contribuer au solde. Pour corriger une opération de trésorerie, l’annuler puis saisir son remplacement avec un motif.

Le cumul additionne les soldes des sessions : **ne pas ressaisir plusieurs fois le même capital pour représenter une bankroll unique**. La limite de perte nette par session se règle en euros dans Paramètres ; zéro la désactive. Une alerte colore le solde et apparaît dans Diagnostics. Elle ne bloque pas les saisies.

Données Windows : `%LOCALAPPDATA%\RouletteTracker\tracker.sqlite3`. Sous Linux : `~/.local/share/RouletteTracker/tracker.sqlite3`. Écritures validées à chaque action. **Diagnostics → Sauvegarder toute la base SQLite** réalise une sauvegarde cohérente incluant sessions, mises en attente, profils, paramètres, historique, annotations et audit. Pour restaurer, fermer l’application, conserver une copie de la base actuelle puis remplacer celle-ci par la sauvegarde. Ne pas partager une base entre plusieurs instances.

### Vidéos et tests

Ouvrir MP4/AVI/MOV/MKV, lire, mettre en pause, choisir 0,25×, 0,5×, 1× ou 2×, avancer d’une image ou déplacer le curseur temporel. Le décodage se fait dans un QThread, avec un seul décodage demandé à la fois. Les recherches dépendent des codecs OpenCV. Les annotations sont enregistrées au temps de la vidéo et retrouvées au même chemin de fichier. Déplacer le curseur désactive l’OCR pour éviter une réimportation involontaire du passé.

### OCR facultatif — Lot B expérimental

Installer séparément Tesseract OCR sur Windows, puis indiquer `tesseract.exe` dans Paramètres ou le rendre accessible par le PATH. Aucune langue supplémentaire n’est nécessaire pour les chiffres. Tesseract n’est pas inclus dans l’EXE. Calibrer uniquement les numéros du panneau, sans compte à rebours ni montants. Indiquer le sens de lecture puis activer l’analyse.

L’outil exige au moins trois nombres distinctement segmentés, chacun avec un score OCR d’au moins 85 %, et deux lectures concordantes espacées. Ce score n’est pas une probabilité de lecture correcte. Par défaut, valider la proposition dans Paramètres. Un mode d’ajout automatique est activable pour la session de travail.

Les nouveaux numéros sont déduits d’un recoupement d’au moins trois positions avec le panneau précédent ; le curseur de dédoublonnage est sauvegardé avec les ajouts. Un panneau inchangé n’ajoute rien. Des résultats identiques consécutifs sont préservés si le décalage du reste du panneau est identifiable. Une répétition parfaitement indiscernable, un recoupement ambigu ou un échec OCR n’est jamais inventé : vérifier et saisir manuellement. Si l’historique de session contient déjà des résultats, ils servent de référence au premier recoupement. **L’OCR reste sujet à des erreurs et omissions sur les vrais panneaux**. Il ne règle pas les mises en attente ; un résultat OCR n’est pas une preuve de gain.

### Candidat bille et modèle — Lots C et D partiels

Activer **Bille expérimentale** dans Direct. Le traitement fonctionne sur la capture et sur les vidéos lorsque la roue est calibrée ou reconnue comme stable. Un détecteur léger cherche un point clair contrasté dans l’anneau extérieur, compare plusieurs trajectoires, ajuste l’angle déroulé dans le temps et affiche vitesse, accélération et sens du candidat retenu. En parallèle, la bande centrale du cylindre est déroulée pour mesurer le sens et la vitesse apparente du rotor par corrélation. Les scores mesurent la continuité et la corrélation, pas l'identité physique. Reflets, mouvements de caméra, perspective et aliasing restent des causes d’échec. Une coupure, une recherche temporelle, une perte ou un changement de dimensions réinitialise les mesures.

Aucun détecteur IA ni détection de fermeture des mises n’est implémenté. La mesure du rotor ne repère pas la poche zéro et ne constitue donc pas un angle absolu exploitable par le modèle physique. `tracker/evaluation.py` contient un modèle hors ligne exigeant cet angle et des paramètres préalablement calibrés. Il refuse les états insuffisants ou postérieurs à la fermeture. **Ce modèle n’est pas branché sur une recommandation en direct**. Son principe et son protocole sont décrits dans `VALIDATION_TRACKER.md`.

## Tests et compilation Windows

```powershell
.\.venv-windows\Scripts\python.exe -m unittest discover -s tests_tracker -v
.\.venv-windows\Scripts\python.exe tracker_main.py --smoke-test
```

`build_windows.bat` installe les dépendances, exécute les tests, construit avec PyInstaller puis ouvre et ferme l’application générée avec une base temporaire. Résultat attendu : `dist\RouletteTracker\RouletteTracker.exe`. **Distribuer tout le dossier `RouletteTracker`**, pas uniquement l’EXE. Construction sur Windows obligatoire ; aucun EXE Windows n’a été compilé depuis Linux. L’exécutable n’est pas signé. Le fichier `.github/workflows/tracker-windows.yml` propose également un build Windows à déclenchement manuel ; il n’a pas été lancé ici.

Sous Linux, pour le développement vidéo et comptable :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-tracker.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests_tracker -v
QT_QPA_PLATFORM=offscreen .venv/bin/python tracker_main.py --smoke-test
```

## Architecture extensible

- `domain.py` : ordre, voisins, propriétés, monnaie en centimes et paiements.
- `storage.py` : transactions, sessions, mises, opérations, audit, profils et curseurs OCR.
- `gui.py`, `widgets.py`, `live.py` : interface Qt, aperçus, sélection de régions et graphiques.
- `video.py` : décodage asynchrone OpenCV.
- `capture.py` : identification Brave Win32, capture visible MSS, contrôle de débit.
- `ocr.py` : Tesseract dans un worker et recoupement de panneaux.
- `vision.py` : contrat d’extension `OfflineAnalyzer` / `Observation`, détecteur neutre par défaut.
- `experimental.py` : candidat bille et sens du rotor expérimentaux.
- `evaluation.py` : modèle physique gardé et évaluation chronologique de secteurs.
- `benchmark.py` : mesures de localisation sur frames annotées indépendamment.

Les traitements vidéo, capture, OCR et analyse ont chacun leur QThread. Les retours graphiques passent par des slots Qt de la fenêtre ; SQLite reste dans le fil de l’interface. Les files de travail sont bornées à une demande en cours par traitement. Les nouvelles caméras et détecteurs peuvent être ajoutés sans changer les règles financières.
