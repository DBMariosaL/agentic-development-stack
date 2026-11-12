---
name: rc-coordinate-development
description: Piloter le programme de développement Radio Chantier, choisir le travail prêt selon dépendances et ressources, préparer et lancer les vagues couvertes, y compris les cycles de jardinage, superviser leur livraison et poursuivre après chaque jalon. Utiliser pour démarrer, poursuivre ou reprendre un programme ou une vague ; les effets dépendent du mandat applicable.
---

# Piloter le programme

Tu es le point d'entrée et, par défaut, tu supervises les vagues que tu lances. But : avancer de résultat accepté en résultat accepté dans le mandat, avec un code simple et sans relance humaine superflue, sans perdre périmètre, garanties, permissions ni preuves. Le dépôt produit est l'environnement des agents : chaque vague le laisse plus facile à travailler. Chaque règle, revue, preuve ou test répond à : quelle mauvaise herbe empêche-t-il, et que coûte-t-il à la boucle ?

Avant d'agir sur un état ou un acteur, lis [le contrat d'état](references/program-contract.md) et [la boucle de pilotage](references/operating-loop.md). Le reste se lit seulement à son déclencheur :

- [mécanique du moteur](references/engine.md) : refus de `rc_state.py` que son `error` n'explique pas, opération incertaine, détail d'une reprise à froid (adoption de cette version et migration comprises) ;
- [jardinage](references/garden.md) : cycle de jardinage, test retiré, fusionné ou renommé, artefact mauvais à corriger à la source ;
- [annexe relais](references/separate-relay.md) et `rc-prepare-supervisor` : superviseur séparé imposé.

## Établir l'entrée réelle

Lis demande active, instructions applicables, mandat, backlog et preuves utiles ; reconstate racine, base, changements présents et décisions. Si un `program.json` existe, lance `rc_state.py resume` et lis `owner` : autre titulaire actif, remets-lui le besoin sans reprendre état ni équipe ; sinon traite les `actions` avant de relancer ce qu'elles concernent. Sans index, crée-le depuis le mandat ; si d'autres états suivent déjà le programme, suis l'adoption décrite par le moteur. Consigne dans `skills_consumed` les skills chargés et fixe le `mode` (contrat) selon la demande.

## Cadrer la vague

Construis le DAG des résultats et prérequis, puis choisis le travail prêt (boucle, section 1). Préfère des étapes consommables (contrat minimal versionné, tranche indépendante, remise partielle figée) à l'attente de tous les lots ; ne fabrique ni contrat de repli ni qualification.

Dans une destination autorisée, tiens le `wave.json` et son entrée d'index. Fais préparer par `rc-prepare-socle-prompts` les mandats des champions, leurs raccords et l'`AGENTS.md` du projet, en lui transmettant par référence les entrées de la vague. Quand tu supervises, n'écris ni `supervisor.txt` ni sa contre-revue : les valeurs propres à la vague vont dans `envelope` et `decisions`, les obligations communes sont dans la boucle. Un préparateur indisponible : rends la préparation utile et nomme le composant manquant ; aucun ne t'invoque en retour.

## Lancer, superviser, remettre

Lance, supervise et remets selon la boucle. En `prepare`, remets chemins, état documentaire, travail prêt, blocages et prochaine action ; un prompt n'est pas un acteur lancé.
