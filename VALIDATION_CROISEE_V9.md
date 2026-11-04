# Validation croisée bille et rotor v9 — 4 novembre 2026

Deux essais réels sur la Legion Go ont produit le même défaut : lors du premier,
la bille candidate et le rotor étaient tous deux annoncés antihoraires ; lors du
second, ils étaient tous deux annoncés horaires. Le candidat changeait donc de
sens avec le rotor. Il s'agissait très probablement d'un reflet ou d'un détail
du rotor, pas d'une mesure indépendante de la bille.

La v9 calcule d'abord le rotor, puis analyse les hypothèses lumineuses. Elle ne
publie une direction de bille que si le rotor possède simultanément une mesure
valide et si les deux signes angulaires sont opposés. Un flux vidéo en miroir
inverse les deux signes mais conserve cette relation d'opposition.

Les trois états sont explicites dans Diagnostics :

- rotor non mesuré : direction du candidat en attente ;
- candidat dans le même sens que le rotor : candidat rejeté et point masqué ;
- candidat dans le sens opposé : direction publiée avec la mention de
  confirmation croisée.

Cette règle élimine le faux positif observé, mais elle ne prouve toujours pas
que tout candidat opposé est la bille. Un reflet indépendant ou un mouvement de
caméra peut encore tromper le module. Aucun numéro futur n'est calculé.

La sauvegarde SQLite fournie est intègre. Elle confirme une capture demandée à
30 FPS, l'option expérimentale active et une zone de roue enregistrée pour le
profil « Table manuelle ». Elle ne stocke pas les images ni les directions.

Validation : 39 tests passent sous Linux avec Qt hors écran, dont attente du
rotor, rejet d'un candidat synchronisé et acceptation d'un candidat opposé. La
compilation Python et le démarrage Qt hors écran sont également vérifiés.
