---
name: rc-prepare-socle-prompts
description: Préparer un ou plusieurs prompts de champions du projet depuis un besoin et l’état du projet, avec domaines, interfaces communes, budget d’autonomie, critères de simplicité et preuves attendues, et entretenir l’AGENTS.md court du projet produit. Utiliser pour rédiger ou harmoniser ces mandats, sans lancer développement ni superviseur.
---

# Préparer les prompts des socles

Livre des mandats exécutables plus tard par un champion qui ne recevra que leur texte. Leur rédaction ne lance aucun développement, superviseur ou service et n’étend aucune autorisation. Un mandat court qui renvoie à l’environnement du projet vaut mieux qu’un mandat qui le recopie.

## Établir les entrées

Lis la mission, les instructions applicables, l’état projet et les sources nécessaires. Lis le [contrat d’état](../rc-coordinate-development/references/program-contract.md) comme données, sans invoquer le pilote ; ses règles communes (faits, modèles, contre-revue, filtres) s’appliquent ici. Utilise le dossier de vague fourni, sinon crée un dossier minimal autorisé (`socles/`, `evidence/`). Écris `wave.json` seulement si cette responsabilité t’est attribuée ou si tu crées le dossier sans titulaire concurrent ; sinon remets des deltas proposés. L’absence de pilote actif ne bloque pas la préparation.

## Entretenir l’environnement du projet

Le dépôt produit porte à sa racine un `AGENTS.md` court, une page au plus, que le fichier d’instructions lu par le runtime du champion (`CLAUDE.md` par exemple) importe ou cite. Vérifie-le à chaque préparation ; propose-le s’il manque, ou son delta s’il est périmé ou trompeur ; l’écriture dans le dépôt suit l’autorisation du mandat, sinon remets le delta. Il porte des conventions durables : une politique propre à une vague (commit ou non des auteurs, chemin des preuves de la vague) va dans le mandat de vague. Il donne :

- la boucle rapide de l’auteur : une commande (lint, typecheck, tests ciblés du domaine) avec un objectif local mesuré, 60 à 90 s par défaut, tout dépassement expliqué ;
- le contrôle d’acceptation, distinct, avec sa durée constatée ;
- conventions, nommage par domaine et comportement, chemins interdits ;
- où vivent les interfaces canoniques et les preuves, hors dépôt.

Les mandats y renvoient au lieu de le recopier. Propose un parallélisme que le coût réel de ces contrôles supporte.

## Écrire des mandats autonomes

Prépare autant de mandats que les résultats et dépendances le justifient. Chaque mandat se suffit : l’enfant ne voit ni l’historique du parent ni les fichiers non commités d’un autre worktree. Il porte le contenu du brief défini par la [boucle](../rc-coordinate-development/references/operating-loop.md#3-livrer-juste) et précise :

- inclus et exclus, scénario utilisateur avancé ou, pour un cycle de jardinage, friction retirée ;
- réalisation modulaire dans l’architecture existante, ports consommés, livrables, responsable d’intégration ; pour une implémentation, du code et des contrôles effectifs, jamais une interface vide ou une procédure seule ;
- interfaces consommées sous une forme que l’enfant peut lire (commit et SHA, manifeste ou chemin figé) ;
- sans mention écrite de délégation, l’enfant ne délègue pas ; conduite avec un descendant : [boucle](../rc-coordinate-development/references/operating-loop.md#5-continuer) ;
- budget d’autonomie : ce que le champion décide seul (méthodes, fixtures, tests, refactor local et choix d’implémentation dans son domaine, sans accusé ni seconde permission), la liste fermée de ce qui remonte, groupé (autre domaine ou interface partagée, effet hors mandat, dépense, donnée réelle, garantie sensible ou sécurité, décision métier manquante), et un temps ou un nombre de tours indicatif ;
- simplicité : réutiliser avant d’ajouter ; aucune abstraction sans second usage ; retirer le code rendu inutile dans son domaine ; chaque test protège un comportement ou défaut nommé, plusieurs cas discriminants restant permis ([valeur des tests](../rc-coordinate-development/references/garden.md#valeur-des-tests)) ;
- remise selon la boucle, proportionnée au risque, avec lignes ajoutées et retirées (produit et tests séparés) et une rubrique « friction » : ce qui a ralenti ou trompé l’auteur (instruction, outil, doc, exemple, boucle lente) ;
- critères d’acceptation, actions couvertes et portes restantes ; pré-revues d’auteur possibles, sans valeur d’acceptation. Un critère à deux lectures plausibles devient une question avant lancement, avec un exemple qui les départage, seulement si le choix change un effet que le mandat protège (données, contrat, droits, comportement visible) ; une forme écrite littéralement dans le mandat (format, libellé) fait foi telle quelle. Sinon, retiens la lecture littérale, consigne-la et continue.

## Raccorder avant consommation croisée

Distingue propriétaires historiques, auteurs actifs et attributions proposées. Affecte explicitement interfaces, SQL et migrations, composition, configuration, lockfiles et tests partagés : un auteur actif par fichier partagé. Migrations : [garanties de toute vague](../rc-coordinate-development/references/operating-loop.md#4-garanties-de-toute-vague).

Pour plusieurs socles, harmonise avant version finale : une définition canonique par interface partagée, dans son propre fichier versionné (producteurs, consommateurs, formes, erreurs, versions, propriétaires, preuves), rendue consommable selon la boucle avant tout usage croisé ; si la préparation est seulement documentaire, nomme l’acteur qui la publiera. Éprouve les choix de contrat contre les primitives lues et les scénarios de reprise et de concurrence : conflit sur une unité, effets indépendants, issue inconnue, perte d’accès. Une alternative sensible non tranchée reste proposée avec son test discriminant et sa revue attendue. Signale le couplage sémantique (droits, cycle de vie, configuration, comportement consommé) même sans fichier commun : il fixe le coût d’intégration.

## Exiger des preuves applicables

Lie chaque exigence à un scénario, un responsable et la preuve la moins coûteuse qui reste discriminante sur candidat identifié. Sépare implémentation, test hors ligne, raccord local et qualification externe (garanties de toute vague) ; distingue testé, échoué, non évalué et bloqué ; aucune preuve ne se transfère entre versions. Une qualification externe fermée laisse avancer l’indépendant couvert : prépare la demande concrète et suspends seulement son chemin.

## Adapter et remettre

Contre-revue documentaire et vérification des modèles suivent les règles communes du contrat ; une revue manquante reste un prérequis du lancement concerné. Applique une seule fois le filtre prescrit (contrat, « Filtres »). Remets fichiers, sources réellement lues, inconnus, couverture et non-exécuté ; une évaluation sans délégation porte « revue indépendante non exécutée ». Après harmonisation, transfère à revue les seuls deltas pertinents. Termine sur cette livraison documentaire, sans lancement.
