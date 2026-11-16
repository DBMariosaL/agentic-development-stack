---
name: rc-prepare-supervisor
description: "Préparer le mandat d’un superviseur séparé imposé pour une vague de développement, à partir d’une vague cadrée et de retours d’expérience sourcés. Produit le mandat ou son delta et ses réserves ; ne lance aucun acteur ni travail produit. Quand le pilote supervise lui-même, aucun mandat de supervision n’est rédigé."
---

# Préparer une supervision séparée

Rédige `supervisor.txt` seulement quand le mandat ou le runtime impose un superviseur distinct du pilote ([annexe relais](../rc-coordinate-development/references/separate-relay.md)). Quand le pilote supervise lui-même, cas par défaut, il n’y a ni `supervisor.txt` ni contre-revue de supervision : remets-lui seulement, s’il le demande, les lignes `decisions` propres à la vague (dispositif d’intégration, approbations et leurs octets, chemin des preuves, ressources réservées). La conduite commune est dans [la boucle de pilotage](../rc-coordinate-development/references/operating-loop.md) : référence-la, ne la recopie pas. Ce skill ne lance rien.

## Rattacher les entrées

Lis le [contrat d’état](../rc-coordinate-development/references/program-contract.md) comme données, sans appeler le pilote ; ses règles communes s’appliquent ici. Lis `wave.json`, son titulaire, l’entrée de programme, les mandats et interfaces, l’`AGENTS.md` du projet et les instructions utiles. Injecte dans le mandat les chemins constatés de l’index, du registre, du contrat, de la boucle et de l’annexe relais, et le droit d’écriture réel. Sans droit d’écriture, remets les deltas au titulaire. Titulaire nul ou registre absent : prépare le mandat et un état proposé sans attendre un pilote fictif.

Relève projet, base, autorisation, périmètre, exclusions, accords préparés et ressources réellement disponibles. Une pièce manquante suspend son dépendant ; prépare le reste.

## Réutiliser plutôt que réécrire

Pour une vague suivante du même programme, produis seulement le delta : nouveaux lots, interfaces, ressources, risques et enseignements, avec référence au mandat précédent encore applicable. Un statut qui change ne justifie ni réécriture complète ni nouveau cycle de revue.

Choisis les remises, rapports bruts et décisions précédents pertinents pour le risque courant. Pour chaque enseignement retenu : source, plage et version, observation, cause établie ou inconnue, décision proposée, invariant préservé. Sépare runtime, procédure et code : un réveil absent n’est pas un défaut de prompt démontré, ni une hypothèse une cause certaine. Conserve ce qui a aidé (attributions, contrats consommables, revues discriminantes) ; retire les permissions répétées et les contrôles sans risque identifié. Aucun gain mesuré ne se déduit de l’historique. Un incident confirmé se traite par [désherbage à la source](../rc-coordinate-development/references/garden.md#désherber-à-la-source).

## Composer le mandat

Utilise le [gabarit](references/supervisor-template.md) en remplaçant ses champs et en supprimant les clauses sans objet. Fixe l’enveloppe de revue selon le risque et le dispositif d’intégration selon le couplage réel ; ne fixe aucun nombre universel de socles, agents, tours ou contrôles. Dans le skill, ne fige ni identifiant, branche, chemin ou allocation historiques ; dans le mandat, injecte les valeurs constatées.

La contre-revue du mandat suit les règles communes du contrat ; délégation interdite ou indisponible : livre le mandat et nomme la revue non faite comme prérequis du lancement concerné.

## Vérifier et remettre

Applique une fois le filtre prescrit (contrat, « Filtres »). Relis exigences, autorisations, interfaces, reprise, réveil et critères observables. Livre le mandat ou son delta, sources examinées, adaptations, inconnus, revues réellement faites et non-exécuté, avec version et empreinte du fichier ; aucun lancement implicite.
