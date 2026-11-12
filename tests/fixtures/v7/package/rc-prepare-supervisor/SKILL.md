---
name: rc-prepare-supervisor
description: "Préparer le mandat de supervision d’une vague Radio Chantier, tenu par le pilote ou exceptionnellement par un superviseur séparé, à partir d’une vague cadrée et de retours d’expérience sourcés. Produit le mandat ou son delta et ses réserves ; ne lance aucun acteur ni travail produit."
---

# Préparer la supervision

Rédige `supervisor.txt` dans le dossier de vague autorisé : les garanties propres à cette vague et ce qui change depuis la précédente. Par défaut, le pilote qui a cadré la vague la supervise lui-même avec ce mandat ; un superviseur séparé reste une exception (annexe relais du pilote). La conduite générique (choix, revues, continuité, interruptions, décisions) est dans [la boucle de pilotage](../rc-coordinate-development/references/operating-loop.md) : référence-la, ne la recopie pas. Ce skill ne lance rien.

## Rattacher les entrées

Lis le [contrat d'état](../rc-coordinate-development/references/program-contract.md) comme données, sans appeler le pilote. Lis `wave.json`, son titulaire, l’entrée de programme, les mandats et interfaces, puis les instructions projet utiles. Injecte dans le mandat les chemins constatés de l’index, du registre, du contrat et de la boucle, et le droit d’écriture réel. Sans droit d’écriture, remets les deltas au titulaire. Titulaire nul ou registre absent : prépare le mandat et un état proposé sans attendre un pilote fictif.

Relève projet, base, autorisation, périmètre, exclusions et ressources réellement disponibles. Les valeurs historiques restent historiques ; les références runtime inconnues restent inconnues. Une pièce manquante suspend son dépendant ; prépare le reste.

## Réutiliser plutôt que réécrire

Pour une vague suivante du même programme, produis seulement le delta : nouveaux lots, interfaces, ressources, risques et enseignements, avec référence au mandat précédent encore applicable. Un statut qui change ne justifie ni réécriture complète ni nouveau cycle de revue.

Choisis les remises, rapports bruts et décisions des vagues précédentes pertinents pour le risque courant. Pour chaque enseignement retenu : source/plage/version, observation, cause établie ou inconnue, décision proposée, invariant préservé. Sépare runtime, procédure et code : un réveil absent n’est pas un défaut de prompt démontré, ni une hypothèse une cause certaine. Conserve ce qui a aidé (attributions, contrats consommables, revues discriminantes, transfert de couverture) ; retire les permissions répétées et les contrôles sans risque identifié. Aucun gain mesuré n’est déduit de l’historique.

## Composer le mandat

Utilise le [gabarit](references/supervisor-template.md) en remplaçant ses champs et en supprimant les clauses sans objet. Fixe l’enveloppe de revue de la vague selon son risque et le dispositif d’intégration selon le couplage réel. Ne fixe aucun nombre universel de socles, agents, tours ou contrôles. Dans le skill, ne fige ni identifiant, branche, chemin ou allocation historiques ; dans le mandat, injecte les valeurs constatées.

Pour un nouveau mandat ou un delta sensible, fais faire la contre-revue prévue par un nouvel acteur, puis dispose ses constats ; une mission différente prime. Délégation interdite ou indisponible : livre le mandat et nomme la revue non faite comme prérequis du lancement concerné.

## Vérifier et remettre

Applique une fois le filtre prescrit par la mission et le parent (contrat commun), sans réoptimisation récursive. Relis exigences, autorisations, interfaces, reprise et critères observables. Livre le mandat ou son delta, sources examinées, adaptations, inconnus, revues réellement faites et non-exécuté, avec version et empreinte du fichier ; aucun lancement implicite.
