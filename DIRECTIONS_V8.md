# Diagnostic directions v8 — 4 novembre 2026

Le diagnostic réel de la v7 a montré une capture saine, une bille rejetée comme
perdue ou ambiguë et un rotor rejeté malgré une corrélation de 0,17. La v7
effaçait aussi immédiatement une direction dès que le mouvement cessait.

La v8 conserve les mesures récentes du rotor pendant 0,9 seconde afin qu'une ou
deux images ambiguës ne détruisent plus sa continuité. Elle attend toujours cinq
mesures concordantes et rejette une direction instable. Les limites de vitesse
restent bornées pour éviter d'accepter un saut de caméra comme une rotation.

Diagnostics distingue désormais : détails insuffisants, déplacement radial,
mouvement trop faible, saut angulaire trop rapide et direction instable. La
dernière direction reconnue de la bille et du rotor reste visible avec son âge,
y compris après la perte du candidat ou l'arrêt du mouvement. Un changement de
caméra ou un nouveau démarrage efface correctement cette mémoire.

Cette conservation sert au diagnostic et ne transforme pas une ancienne mesure
en mesure courante. Le point lumineux reste un candidat bille non validé. Aucun
numéro final n'est déduit et l'interface conserve « Aucune estimation fiable ».

Validation : 38 tests passent sous Linux avec Qt hors écran. Ils incluent les
deux sens du rotor, une interruption par images ambiguës, le rejet d'une roue
vide, la conservation des dernières directions dans l'interface, la capture et
les tests précédents de bille et de changements de caméra.
