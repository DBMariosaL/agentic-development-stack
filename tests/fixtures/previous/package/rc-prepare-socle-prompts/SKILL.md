---
name: rc-prepare-socle-prompts
description: Préparer un ou plusieurs prompts de champions Radio Chantier depuis un besoin et l’état du projet, avec domaines, interfaces communes et preuves attendues. Utiliser pour rédiger ou harmoniser ces mandats, sans lancer développement ni superviseur.
---

# Préparer les prompts des socles

Livre des prompts exécutables ultérieurement, adaptés au besoin actuel. Leur rédaction ne lance aucun développement, superviseur ou service et n’étend aucune autorisation.

## Établir les entrées

Lis la mission, les instructions applicables, l’état projet et les sources métier/techniques nécessaires. Distingue état observé, référence historique et hypothèse. Ne déduis ni le prochain socle de son numéro, ni une capacité d’un ancien lancement.

Lis le [contrat de vague compagnon](../rc-coordinate-development/references/wave-contract.md) comme données, sans invoquer le coordinateur. Utilise le dossier de vague fourni. Sinon, crée un dossier minimal autorisé avec les prompts sous `socles/` et les preuves utiles sous `evidence/`. Tiens `wave.json` si cette responsabilité t’est confiée ou si tu crées le dossier sans propriétaire concurrent ; sinon remets ses deltas proposés. Un propriétaire désigne une responsabilité, pas un agent à réveiller. L’absence de coordinateur actif ne bloque pas la préparation.

## Définir des mandats réalisables

Prépare un ou plusieurs prompts selon les résultats et dépendances utiles, sans effectif fixe. Chaque prompt précise :

- résultat concret, base et sources accessibles, inclus/exclus ;
- réalisation modulaire réutilisable dans l’architecture existante, ports consommés et livrables attendus ;
- domaine propre de code **et de tests**, fichiers partagés, ressources, responsable d’intégration ;
- actions couvertes et portes restantes, critères d’acceptation, preuves et remise.

Demande du code et des contrôles effectifs lorsque le futur mandat les couvre ; des interfaces vides ou une procédure ne satisfont pas un résultat d’implémentation. Préserve la sous-délégation utile permise par la mission, avec propriété, preuves et point d’intégration transmis.

## Raccorder avant consommation croisée

Distingue propriétaires historiques des modules, auteurs actifs et attributions seulement proposées. Affecte explicitement interfaces, SQL/migrations, composition, configuration, lockfiles et tests partagés : un auteur actif par fichier partagé. N’invente ni réservation ni numéro de migration ; respecte l’immuabilité des migrations appliquées.

Pour plusieurs socles, harmonise avant version finale. Garde une définition canonique par interface partagée : producteurs/consommateurs, formes, erreurs, versions, propriétaires et preuves. Une interface par fichier versionné, sans empreinte globale couplant des interfaces disjointes. La version consommable précède l'usage croisé et ne suspend que son chemin.

Éprouve les choix de contrat contre les primitives lues et les scénarios de reprise/concurrence : un conflit sur une unité, des effets indépendants, une issue inconnue et une perte d'accès. La facilité d'un callback ne suffit pas à justifier une atomicité globale. Une alternative sensible non tranchée reste proposée avec son test discriminant et sa revue attendue.

## Exiger des preuves applicables

Lie chaque exigence à un scénario, un responsable et une preuve réaliste sur candidat identifié. Sépare implémentation, test hors ligne, raccord local et qualification externe. Une preuve synthétique, compilation ou configuration ne qualifie pas appareil, fournisseur ou stockage réel. Distingue testé, échoué, non évalué et bloqué ; aucune preuve n’est transférée automatiquement entre versions.

Une qualification externe fermée laisse avancer le développement indépendant couvert. Attribuer un fichier n’autorise ni outil nouveau, fournisseur, données, dépense ou effet externe. Prépare la demande manquante concrète et suspends seulement son chemin.

## Adapter et remettre

Pour un nouveau lot ou une refonte sensible, fais contre-relire les prompts harmonisés par un nouvel Opus selon le contrat commun ; conserve champions Opus et revues GPT dans les mandats. Respecte les choix explicites ; avant délégation autorisée, vérifie modèles/options live sans substitution silencieuse. Sépare paramètres demandés, configuration retournée et effort interne non attesté. Une revue manquante reste un prérequis du lancement concerné, pas une activité simulée.

Applique une seule fois le filtre prescrit par la mission et le parent selon le contrat commun. À défaut de règle supérieure : `gpt-prompt-optimizer` pour GPT, `claude-opus-prompt-optimizer` pour Opus. Réutilise ces skills sans copie ni optimisation en cascade ; consigne toute disposition et indisponibilité, sans passe supplémentaire pour compenser.

Remets fichiers, sources réellement lues, inconnus, couverture et non-exécuté. Une évaluation bornée sans délégation porte « revue indépendante non exécutée », sans verdict inventé. Après harmonisation, transfère à revue les seuls deltas pertinents et leur contrôle attendu ; conserve les échecs et réserves. Termine sur cette livraison documentaire, sans lancement.
