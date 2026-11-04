# Calibrage automatique v4 — 4 novembre 2026

Cette version ajoute le bouton **Détecter le cylindre** dans les pages Direct et
Vidéos et tests. Le détecteur recherche des ellipses concentriques dans l'image
la plus récente, affiche le cadre proposé en vert et demande une confirmation
avant de modifier le profil actif.

Le détecteur refuse les images trop petites, sans ellipse assez nette ou dont le
score géométrique est insuffisant. Un refus de l'utilisateur conserve le calibrage
précédent. Le calibrage manuel reste disponible pour les vues obliques, partielles
ou encombrées.

Le score mesure seulement la cohérence géométrique du cadre. Il ne valide ni la
bille, ni le rotor, ni une estimation de secteur. Le suivi expérimental existant
reste limité aux vidéos enregistrées.

Validation dans l'environnement Linux : 28 tests réussis et démarrage Qt hors
écran réussi. Les tests couvrent une roue elliptique synthétique à anneaux
concentriques, le refus d'images invalides et la confirmation obligatoire dans
l'interface. La vidéo réelle fournie dépassait la limite d'import de 32 Mio ; le
calibrage doit donc encore être évalué sur ses images réelles sous Windows.
