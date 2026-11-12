---
name: rc-prepare-socle-prompts
description: Préparer un ou plusieurs prompts de champions Radio Chantier depuis un besoin et l’état du projet, avec domaines, interfaces communes et preuves attendues. Utiliser pour rédiger ou harmoniser ces mandats, sans lancer développement ni superviseur.
---

# Préparer les prompts des socles

Livre des mandats exécutables plus tard par un champion qui ne recevra que leur texte. Leur rédaction ne lance aucun développement, superviseur ou service et n’étend aucune autorisation.

## Établir les entrées

Lis la mission, les instructions applicables, l’état projet et les sources métier/techniques nécessaires. Distingue état observé, référence historique et hypothèse ; ne déduis ni le prochain socle de son numéro, ni une capacité d’un ancien lancement.

Lis le [contrat d'état compagnon](../rc-coordinate-development/references/program-contract.md) comme données, sans invoquer le pilote. Utilise le dossier de vague fourni ; sinon crée un dossier minimal autorisé (prompts sous `socles/`, preuves sous `evidence/`). Écris `wave.json` seulement si cette responsabilité t’est attribuée ou si tu crées le dossier sans titulaire concurrent ; sinon remets des deltas proposés. L’absence de pilote actif ne bloque pas la préparation.

## Écrire des mandats autonomes

Prépare autant de mandats que les résultats et dépendances le justifient. Chaque mandat se suffit : l’enfant ne voit ni l’historique du parent, ni les fichiers non commités d’un autre worktree. Il précise :

- résultat concret, base et sources accessibles par chemin, inclus/exclus ;
- réalisation modulaire dans l’architecture existante, ports consommés, livrables ;
- domaine propre de code **et de tests**, fichiers partagés attribués, ressources, responsable d’intégration ;
- interfaces consommées sous une forme réellement disponible pour l’enfant (commit et SHA, manifeste ou chemin figé) ;
- délégation : autorisée avec ses bornes, ou interdite ; sans mention écrite, l’enfant ne délègue pas ;
- conduite avec un descendant : l’attendre avec le mode d’attente de l’outil, ou remettre une remise partielle qui le nomme ; pas de remise finale avec un descendant nécessaire actif ;
- actions couvertes et portes restantes, critères d’acceptation, preuves, point et forme de remise ;
- pré-revues d’auteur possibles, distinctes de la revue d’acceptation mandatée par le pilote.

Demande du code et des contrôles effectifs quand le mandat couvre une implémentation ; une interface vide ou une procédure ne satisfait pas ce résultat.

## Raccorder avant consommation croisée

Distingue propriétaires historiques, auteurs actifs et attributions proposées. Affecte explicitement interfaces, SQL/migrations, composition, configuration, lockfiles et tests partagés : un auteur actif par fichier partagé. N’invente ni réservation ni numéro de migration ; respecte l’immuabilité des migrations appliquées.

Pour plusieurs socles, harmonise avant version finale. Garde une définition canonique par interface partagée, dans son propre fichier versionné : producteurs, consommateurs, formes, erreurs, versions, propriétaires, preuves. Le producteur la rend consommable (commit et SHA pour un consommateur en worktree) avant l’usage croisé ; seul le chemin consommateur attend. Une préparation documentaire n’autorise pas un commit produit : nomme alors l’acteur qui publiera.

Éprouve les choix de contrat contre les primitives lues et les scénarios de reprise/concurrence : conflit sur une unité, effets indépendants, issue inconnue, perte d’accès. Une alternative sensible non tranchée reste proposée avec son test discriminant et sa revue attendue. Signale le couplage sémantique (droits, cycle de vie, configuration, comportement consommé) même sans fichier commun : il fixe le coût d’intégration.

## Exiger des preuves applicables

Lie chaque exigence à un scénario, un responsable et une preuve réaliste sur candidat identifié. Sépare implémentation, test hors ligne, raccord local et qualification externe ; une preuve synthétique ou une configuration ne qualifie pas appareil, fournisseur ou stockage réel. Distingue testé, échoué, non évalué et bloqué ; aucune preuve ne se transfère entre versions. Exige une remise d’auteur sur le candidat exact : commande et répertoire, attendu et observé, collecte et skips, sorties brutes, empreintes et limites, ainsi que la récupération (moyen, périmètre, propriétaire, éprouvée ou non). Une qualification externe fermée laisse avancer l’indépendant couvert : prépare la demande concrète et suspends seulement son chemin.

## Adapter et remettre

Pour un nouveau lot ou une refonte sensible, fais contre-relire les prompts harmonisés par un nouvel acteur selon le contrat commun ; conserve champions Opus et revues GPT prévus. Avant une délégation autorisée, vérifie modèles et options live sans substitution silencieuse ; sépare paramètre demandé, configuration retournée et effort interne non attesté. Une revue manquante reste un prérequis du lancement concerné.

Applique une seule fois le filtre prescrit (contrat commun). Remets fichiers, sources réellement lues, inconnus, couverture et non-exécuté. Une évaluation sans délégation porte « revue indépendante non exécutée ». Après harmonisation, transfère à revue les seuls deltas pertinents. Termine sur cette livraison documentaire, sans lancement.
