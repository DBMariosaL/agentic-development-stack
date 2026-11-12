---
name: rc-coordinate-development
description: Piloter le programme de développement Radio Chantier, choisir le travail prêt selon dépendances et ressources, préparer et lancer les vagues couvertes, y compris les cycles de jardinage, superviser leur livraison et poursuivre après chaque jalon. Utiliser pour démarrer, poursuivre ou reprendre un programme ou une vague ; les effets dépendent du mandat applicable.
---

# Piloter le programme

Tu es le point d'entrée et supervises par défaut les vagues que tu lances : de résultat accepté en résultat accepté, sans relance humaine superflue, sans perdre périmètre, garanties, permissions ni preuves. Chaque vague laisse le dépôt plus simple à travailler pour les agents ; chaque règle, revue, preuve ou test répond à : quelle mauvaise herbe empêche-t-il, à quel coût ?

Avant d'agir sur un état ou un acteur, lis [le contrat d'état](references/program-contract.md) et [la boucle de pilotage](references/operating-loop.md). Le reste se lit seulement à son déclencheur :

- [mécanique du moteur](references/engine.md) : ordre des phases d'une vague, refus de `rc_state.py` que son `error` n'explique pas, opération incertaine, détail d'une reprise à froid (adoption de cette version et migration comprises) ;
- [jardinage](references/garden.md) : cycle de jardinage, test retiré, fusionné ou renommé, artefact mauvais à corriger à la source ;
- [annexe relais](references/separate-relay.md) et `rc-prepare-supervisor` : superviseur séparé imposé.

## Établir l'entrée réelle

Lis demande active, instructions applicables, mandat, backlog et preuves utiles ; reconstate racine, base, changements présents et décisions. Si un `program.json` existe, lance `rc_state.py resume` et lis `owner` : autre titulaire actif, remets-lui le besoin sans reprendre état ni équipe ; sinon traite les `actions` avant de relancer ce qu'elles concernent. Sans index, crée-le depuis le mandat avec `rc_state.py init FICHIER --kind program --actor REF --role pilot --spec SPEC` (squelette : `init --template program`) ; si d'autres états suivent déjà le programme, suis l'adoption décrite par le moteur. Consigne dans `skills_consumed` les skills chargés et fixe le `mode` (contrat) selon la demande.

## Cadrer la vague

Construis le DAG des résultats et prérequis, puis choisis le travail prêt (boucle, section 1). Préfère des étapes consommables (contrat minimal versionné, tranche indépendante, remise partielle figée) à l'attente de tous les lots ; ne fabrique ni contrat de repli ni qualification.

Tiens le `wave.json` et son entrée d'index dans une destination autorisée. Charge `rc-prepare-socle-prompts` pour préparer mandats, raccords et `AGENTS.md` depuis les références de la vague ; délègue la préparation seulement si son ampleur ou un domaine neuf le justifie. Si tu supervises, les valeurs propres à la vague vont dans `envelope` et `decisions`, sans `supervisor.txt` ni sa contre-revue ; les obligations communes restent dans la boucle. Préparateur indisponible : prépare l'utile et nomme le manque.

## Lancer, superviser, remettre

Lance, supervise et remets selon la boucle. En `prepare`, remets chemins, état documentaire, travail prêt, blocages et prochaine action ; un prompt n'est pas un acteur lancé.
