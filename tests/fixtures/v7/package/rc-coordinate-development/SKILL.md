---
name: rc-coordinate-development
description: Piloter le programme de développement Radio Chantier, choisir le travail prêt selon dépendances et ressources, préparer et lancer les vagues couvertes, superviser leur livraison et poursuivre après chaque jalon. Utiliser pour démarrer, poursuivre ou reprendre un programme ou une vague ; les effets dépendent du mandat applicable.
---

# Piloter le programme

Tu es le point d'entrée et, par défaut, le même acteur supervise les vagues qu'il lance : aucun superviseur permanent supplémentaire. Le résultat attendu est un programme qui avance de résultat accepté en résultat accepté dans le mandat, avec moins de relances humaines superflues, sans perdre périmètre, garanties, permissions ni preuves.

Lis avant d'agir sur un état ou un acteur : [contrat d'état](references/program-contract.md) pour les formats, [boucle de pilotage](references/operating-loop.md) pour la conduite. Superviseur imposé dans un autre fil : [annexe relais](references/separate-relay.md). L'outil [rc_state.py](scripts/rc_state.py) (Python 3, bibliothèque standard) valide, calcule le prêt, écrit sous révision et réconcilie ; lance-le avec `--help` pour ses commandes.

## Établir l'entrée réelle

Lis la demande active, les instructions applicables, le mandat de programme, le backlog et les preuves utiles. Reconstate racine, base, changements présents et décisions applicables ; sépare état observé, rapport historique, hypothèse et inconnu. Un ancien acteur nommé ou un numéro de socle n'est pas une activité courante.

Si un `program.json` existe, lance `rc_state.py resume` sur ce fichier puis lis `owner`. Autre titulaire actif : ne reprends ni état ni équipe, remets-lui le besoin. Intentions `pending`, acteurs `unknown`, opérations incertaines ou événements non appliqués : traite-les selon la ligne « Reprise à froid » de la boucle avant de relancer ce qu'ils concernent. Sans index, crée-le depuis le mandat en rapprochant une fois les états existants : chaque résultat restant pointe vers son état canonique, les attentes périmées sont retirées avec leur preuve, rien n'est recopié. Un registre v1 se migre vers un nouveau fichier (`rc_state.py migrate`) à une frontière de vague stable. Consigne dans `skills_consumed` les empreintes des skills et références réellement lus.

Détermine le mode : `prepare` produit documents et revues documentaires autorisées, sans acteur de développement ; `prepare-and-launch` inclut les lancements demandés et couverts. Réutilise les accords existants ; demande seulement ce qui manque pour un effet ou une portée non couverts.

## Cadrer la vague

Construis le DAG des résultats et prérequis, vérifie cycles et prérequis non satisfaits, et choisis le travail prêt selon la section 1 de la boucle. Propose des étapes consommables (contrat minimal versionné, tranche indépendante, remise partielle figée) plutôt qu'une attente de tous les lots ; ne fabrique ni contrat de repli ni qualification. Préserve les modèles demandés et vérifie les options exposées par le runtime sans inventer d'équivalence ni certifier l'effort interne.

Dans une destination autorisée, tiens le `wave.json` de la vague et son entrée dans l'index. Utilise ensuite :

1. `rc-prepare-socle-prompts` avec demande, base, sélection, domaines, ressources, autorisations, critères et chemins : mandats des champions et raccords.
2. `rc-prepare-supervisor` avec le registre, les mandats produits et leur version : mandat de supervision de la vague, ou seulement son delta pour une vague suivante du même programme.

Transmets les artefacts communs par référence. Ces préparateurs ne t'invoquent pas en retour ; s'ils sont indisponibles, rends la préparation utile et nomme le composant manquant. Un nouveau domaine ou un mandat sensible garde sa contre-revue prévue ; un changement de statut n'ouvre pas de cycle de rédaction.

## Lancer et superviser

Avant un lancement, vérifie `launch_ready`, revues indispensables disposées, rattachement du fil au bon projet, base, outils live et versions consommées. Un `cd` ne rattache pas un fil ; sans le bon contexte, remets le lancement concret à exécuter. Écris l'intention avant chaque appel et consigne seulement les références réellement retournées.

Supervise ensuite selon la boucle : livrer juste, continuer après le jalon, traverser les interruptions, préparer les décisions humaines. Le mandat composé pour la vague porte ses garanties produit.

## Remettre

En `prepare`, remets chemins, état documentaire, travail prêt, blocages et prochaine action ; un prompt n'est pas un acteur lancé. En lancement, le programme continue tant qu'il reste du travail autorisé prêt ; chaque remise distingue accepté, échoué, bloqué, en attente et non qualifié.
