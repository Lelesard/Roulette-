# Validation — 26 octobre 2026

## Résultats exécutés

| Vérification | Environnement | Résultat |
|---|---|---|
| Moteur, statistiques, finance, absence de fuite future, Monte-Carlo, CSV et sessions | Linux / Python 3.12.14 | 14 tests réussis |
| Suite complète avec vraie instance Tk et événements GUI | Linux / Python système 3.13.5 / Tk 8.6 / Xvfb | 17 tests réussis, zéro ignoré |
| Compilation des modules | Python 3.12.14 | Réussie |
| Inspection visuelle du tableau de bord avec 150 tirages | Tk 8.6 / écran virtuel 1920 × 1080 | Tapis, cylindre, scanner et comparateur affichés |
| Fenêtre réduite à 980 × 600 | Test GUI | Roue sans chevauchement des cases, défilement vertical disponible |
| 50 000 tirages, sept stratégies + référence aléatoire, fenêtre 50, graine 19 | Python 3.12.14 | 5,39 s pour le chargement initial |
| Ajout incrémental du 50 001e tirage | Même évaluateur | 0,0035 s pour le moteur seul |
| 10 000 séries Monte-Carlo de 200 tirages, maximum des 37 secteurs | Python 3.12.14 | 1,64 s |

Les durées sont des observations locales, pas des garanties sur d’autres machines. La durée d’ajout mesure le moteur, sans la sauvegarde JSON ni le rafraîchissement graphique.

Les tests GUI exercent la saisie, les clics tapis/cylindre, la sélection préalable enregistrée, l’annulation, le suivi virtuel activé/désactivé, le CSV, la création de session à l’import, les paramètres, le comparateur, Monte-Carlo et la confirmation d’effacement. La restauration est vérifiée par relecture du fichier sauvegardé. Les graines Monte-Carlo et la recherche du maximum des 37 secteurs sont comparées à un calcul indépendant dans les tests.

Le démarrage de l’écran virtuel depuis `/workspace/.roulette-tools/start-display.sh` a été exécuté, puis la suite complète a été relancée avec succès. Ces fichiers de support cloud sont extérieurs au programme distribué. Ils ne sont pas nécessaires sur un PC Windows.

## Limites et éléments non validés

- Aucun ancien fichier Python n’était disponible : aucune analyse ou conservation de ses modules ne peut être revendiquée.
- Aucun test sur Windows 11, aucun exécutable Windows construit ou testé. La procédure PyInstaller est documentée dans README.md pour être exécutée sur Windows.
- Le Tk 9 du Python cloud 3.12 affiche mal certains caractères avec les polices du serveur X. Tk 8.6 du Python système est utilisé pour l’interface Linux et ne présente pas ce défaut observé. Le Tk de l’installation Python Windows doit être vérifié sur le PC cible.
- Pas de test d’endurance de plusieurs jours, de concurrence entre plusieurs instances, de panne électrique réelle ou de validation dans une nouvelle tâche après publication du snapshot.
- Le JSON est enregistré atomiquement, mais il n’y a pas de verrou multi-instance ni de sauvegarde distante. Conserver une copie du dossier de données.
- Les classements sont rétrospectifs. Les tests Monte-Carlo ne corrigent pas globalement la multiplicité des mesures/fenêtres. Aucun résultat n’établit un avantage sur la roulette.
- Le logiciel fournit une application de bureau, sans serveur web ni aperçu accessible depuis un navigateur.

## Configuration cloud enregistrée

Le champ `start_skill` contient les commandes de démarrage, l’activation de l’écran virtuel, le choix de Python/Tk et les vérifications de disponibilité. Aucun script d’installation applicative n’est requis : seules les bibliothèques standard sont utilisées. Aucun secret ou changement de réseau n’a été ajouté.

L’enregistrement du brouillon est confirmé. La publication du snapshot reste une action de l’utilisateur dans les paramètres de l’environnement ; elle n’a pas été effectuée ou simulée ici.
