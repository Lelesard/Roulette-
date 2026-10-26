# ROULETTE ANALYZER 19 PRO — ÉDITION PROFESSIONNELLE

Application de bureau en français pour la roulette européenne. Python, Tkinter/ttk, bibliothèque standard uniquement. Utilisable hors connexion ; aucune connexion à un casino, aucune mise réelle.

Le dépôt initial était vide et aucun ancien programme Python n’a été fourni. Cette version est une nouvelle implémentation du cahier des charges, sans prétendre avoir repris un logiciel existant.

## Lancer sous Windows 11

1. Installer **Python 3.12** depuis python.org, avec le lanceur Python et Tcl/Tk (inclus dans l’installation standard).
2. Extraire **tout** le ZIP dans un dossier accessible en écriture. Ne pas lancer le programme à l’intérieur de l’archive.
3. Double-cliquer sur `Lancer_Roulette.bat`, ou ouvrir un terminal dans ce dossier :

```powershell
py -3.12 main.py
```

Aucun `pip install` n’est nécessaire. Vérifier Tkinter en cas de problème : `py -3.12 -m tkinter` doit ouvrir une petite fenêtre.

Sous Linux, utiliser un Python disposant de Tkinter et une session graphique : `python3 main.py`. Dans l’environnement cloud fourni, `/usr/bin/python3 main.py` utilise Tk 8.6 ; le Python 3.12 fourni par le runtime utilise Tk 9 et présente un défaut de rendu des polices/caractères sur ce serveur X. Les calculs sont testés avec les deux interpréteurs. Tk 8.6 est donc préféré pour l’affichage Linux. Le logiciel reste destiné à Python 3.12/Tkinter sous Windows.

## Tableau de bord

- Cliquer sur le tapis ou sur une case du cylindre, ou saisir un entier **0–36** puis Entrée. Chaque clic ajoute un tirage ; utiliser **Annuler** en cas de doublon accidentel.
- Le tapis suit la disposition européenne : colonnes 1/2/3 à 34/35/36 et zéro sur trois rangées. La roue respecte l’ordre réel des 37 cases.
- Le contour cyan désigne les 19 numéros sélectionnés pour le prochain tour. Le point orange sur le tapis et le grand numéro central repèrent le dernier résultat. L’anneau orange désigne le secteur historique maximal ; les indications × signalent les répétitions sur les 20 derniers tours.
- Choisir la stratégie dans le scanner ou cliquer sur sa ligne dans le comparateur.
- **Fenêtre de sélection** : 20, 50, 100 ou 200 résultats précédents utilisés pour calculer les sélections. Avant que la fenêtre soit remplie, tous les résultats disponibles sont utilisés.
- **Période évaluée** : 20, 50, 100, 200 derniers tours, ou toute la session. Le contexte plus ancien est conservé pour sélectionner les numéros de chacun des tours évalués.
- Modifier la mise par numéro, puis Entrée. Le comparateur est un **rejeu historique à mise constante**, recalculé avec les paramètres actuels. Les séries et le drawdown sont réinitialisés au début de la période évaluée ; ils ne se prolongent pas en dehors de celle-ci.
- Cocher **Enregistrer les mises virtuelles** pour journaliser, avant chaque nouvelle saisie, la stratégie choisie, la fenêtre, les 19 numéros et la mise du moment. Désactiver cette option suspend uniquement ce journal ; les analyses historiques restent disponibles. Changer les paramètres ne réécrit pas le journal. Annuler un tirage retire son éventuelle mise. Un import CSV n’invente pas de mises passées.
- Le panneau **Analyses détaillées** contient les 37 secteurs, les absences/intervalles, Monte-Carlo et le journal virtuel. C’est un instantané à l’ouverture ; fermer et rouvrir pour actualiser les tableaux détaillés. Monte-Carlo prend un nouvel instantané au lancement.
- Les trois zones principales restent côte à côte. Sur un petit écran, faire défiler verticalement le tableau de bord pour accéder au comparateur et aux informations du bas. Largeur minimale : 980 pixels.

## Règles reproductibles des sept stratégies

L’ordre du cylindre est le départage commun, en commençant par le zéro. Chaque sélection contient toujours exactement 19 numéros distincts.

| Stratégie | Définition |
|---|---|
| 19 voisins fixes | Les 19 cases dans le sens de l’ordre du cylindre, zéro inclus au départ. |
| 19 chauds | Fréquences décroissantes dans la fenêtre. |
| 19 froids | Fréquences croissantes, y compris les numéros non observés. |
| 10 chauds + 9 froids | Dix premiers chauds, puis neuf premiers froids qui n’y figurent pas. |
| 19 voisins fréquents | Maximum des 37 secteurs de 19 cases ; égalité départagée par l’ordre de leur case de départ. |
| 19 retours rapides | Moyenne des intervalles de réapparition croissante. Un numéro sans au moins deux apparitions a un score infini ; il complète la sélection après les numéros documentés. Aucune périodicité prédictive n’est supposée. |
| 19 voisins du dernier | Dernier résultat, ses neuf voisins de chaque côté. Sans résultat : secteur fixe partant du zéro. |

Historique vide : les sept stratégies retournent le secteur fixe. Fréquences égales ou intervalles moyens égaux : ordre du cylindre. La référence aléatoire sélectionne 19 cases sans remise à chaque tour, avec la graine fixe 19037. C’est une seule trajectoire de comparaison, pas une distribution de significativité.

## Calculs et absence de données futures

Pour le tour `i`, la sélection est calculée uniquement sur les résultats **strictement antérieurs** à `i`. Le résultat `i` est ensuite évalué et ajouté à l’historique. Les sélections de chaque stratégie sont conservées par l’évaluateur en mémoire ; le journal des saisies conserve aussi les paramètres originaux sur disque.

Une mise de `m` euros par numéro engage `19m` : touche = `+17m` nets, raté = `−19m`. Le ROI est `100 × solde / mises cumulées`, zéro s’il n’y a pas de mises. Le drawdown maximal est la plus forte baisse depuis un sommet du solde, en incluant le capital de départ zéro. Le capital est virtuel et peut devenir négatif ; aucune contrainte de bankroll ou progression de mises n’est simulée.

À roulette équitable, P(touche) = 19/37 et l’espérance est −1/37 des sommes engagées (environ −2,70 %). Une sélection historique ne garantit pas le résultat suivant.

Le scanner de répétitions utilise la session entière :

- Une réapparition est comptée une fois par nouveau résultat à partir de sa précédente apparition. Les retours ≤ 5 et ≤ 10 incluent les répétitions immédiates.
- L’intervalle compte les tours entre les indices de deux apparitions : deux résultats consécutifs ont un intervalle de 1.
- Une absence est le nombre de tours depuis la dernière apparition : zéro pour le dernier résultat. « Jamais observé » est une durée censurée égale à la taille de la session.
- Une série sans répétition est une suite contiguë de numéros tous différents.
- Les cycles affichent les intervalles constatés, leur moyenne et leur écart-type population ; aucun modèle périodique n’est inféré.

Les secteurs affichent comptes, fréquences et écarts en points par rapport à 19/37. Les horizons 20/50/100/200 sont tronqués si la session est plus courte ; les dénominateurs sont affichés.

## Comparaison Monte-Carlo

Choisir une mesure, la fenêtre ou la session entière, 500/2 000/10 000 simulations et une graine entière. Chaque simulation génère une série uniforme indépendante de même taille et applique la même mesure. **Le maximum parmi les 37 secteurs est recalculé pour chaque série** : il ne s’agit pas de tester un secteur choisi après coup comme s’il était fixé à l’avance.

Mesures disponibles : concentration maximale, répétitions immédiates, retours ≤ 5/10, plus grand intervalle, plus longue série sans répétition, absence maximale et faible diversité sur les 37 derniers résultats. Sont affichés observation, moyenne simulée, percentile avec demi-poids des égalités, compte des cas au moins aussi extrêmes et p Monte-Carlo `(cas + 1)/(simulations + 1)`. La faible diversité utilise la queue inférieure ; les autres mesures la queue supérieure. Le minimum observable de cette p dépend du nombre de simulations.

Les simulations peuvent être annulées ; aucun résultat partiel n’est présenté. Le fil de calcul ne manipule aucun widget. Les mesures non testées restent descriptives. Il n’y a pas de correction globale pour l’exploration de plusieurs mesures ou fenêtres, ni d’intervalle de confiance pour la p estimée. Une rareté ne suffit pas à démontrer un biais et ne fournit pas de signal pour miser. Une confirmation sur une nouvelle série indépendante est nécessaire.

## Sessions, sauvegardes et CSV

Sauvegarde automatique après chaque modification et à la fermeture :

- Windows : `%LOCALAPPDATA%\RouletteAnalyzer19Pro\sessions.json`.
- Linux : `~/.local/share/RouletteAnalyzer19Pro/sessions.json`.
- Emplacement personnalisable par `ROULETTE19_DATA_DIR`.

Les noms de session, résultats et journaux de mises sont conservés. Les paramètres d’affichage reviennent à leurs valeurs par défaut au lancement. La sauvegarde JSON utilise un fichier temporaire, un flush disque et un remplacement atomique. Le logiciel ne doit être ouvert qu’en **une instance par dossier de données** : pas de fusion ou de verrou interprocessus.

Une sauvegarde corrompue n’est pas écrasée automatiquement : le démarrage échoue avec une explication. Sauvegarder le fichier endommagé ailleurs puis restaurer une copie connue ou le déplacer pour repartir d’une session vide. Sauvegarder régulièrement tout le dossier de données sur un autre support.

Le journal d’erreurs `errors.log` se trouve dans le même dossier (rotation 2 Mo, deux copies). Une erreur d’écriture est signalée ; exporter alors les tirages en CSV avant de quitter.

**CSV** : UTF-8 avec ou sans BOM, une seule colonne, en-tête facultatif `numero`, `numéro` ou `number`, ordre du plus ancien au plus récent. Un entier de 0 à 36 par ligne. L’import est entièrement validé avant de créer une nouvelle session, sans toucher aux sessions existantes. L’export contient les tirages, pas le journal ni les paramètres ; sauvegarder le JSON pour tout conserver. **Effacer** nécessite une confirmation et vide uniquement la session active.

Exemple :

```csv
numero
0
32
15
19
36
```

## Tests

Dans le dossier du projet :

```powershell
py -3.12 -m unittest discover -v
```

Sous Linux : `python3 -m unittest discover -v`. Les tests de l’interface sont explicitement ignorés si aucun écran n’est disponible. Avec Xvfb : `xvfb-run -a /usr/bin/python3 -m unittest discover -v`.

Les tests vérifient l’ordre réel des cases, les sept sélections, les égalités/historiques vides, gains/ROI/drawdown/séries, l’absence de fuite future, les annulations/recalculs, scanners/secteurs, CSV, sauvegarde/restauration et corruption, Monte-Carlo et graines reproductibles. Les tests GUI exercent saisie/clics, journal préalable, import/export, sessions, confirmation d’effacement, paramètres, simulation en arrière-plan et redimensionnement.

Voir `VALIDATION.md` pour les résultats observés et les limites de validation. Aucun test Windows ni exécutable Windows n’a été réalisé dans ce conteneur Linux.

## Fabriquer un exécutable Windows

À faire **sur Windows 11**, dans le dossier du projet, avec Python 3.12. PyInstaller est une dépendance de construction facultative ; l’application elle-même n’en a pas besoin.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name RouletteAnalyzer19Pro main.py
```

Le résultat sera `dist\RouletteAnalyzer19Pro.exe`. Tester manuellement sur Windows : lancement, clics/saisie, fermeture/réouverture, CSV accentué, sessions, écran plus petit, Monte-Carlo/annulation et permissions de sauvegarde. Le fichier n’est pas signé ; une distribution publique peut nécessiter une signature et un installateur. Aucun `.exe` n’est livré ou présenté comme testé ici.

## Organisation

- `main.py` et `Lancer_Roulette.bat` : lancement.
- `roulette19/gui.py` : interface, événements et files de communication des calculs.
- `roulette19/engine.py` : stratégies, scanner, secteurs, comparateur et Monte-Carlo.
- `roulette19/storage.py` : sessions et CSV.
- `tests/` : tests standard `unittest`.

Aucun fichier de données personnelles n’est livré. Aucun module du programme n’exige un accès Internet.
