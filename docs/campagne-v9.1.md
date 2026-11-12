# Campagne d'essais réels v9 (11 novembre 2026)

Source de la v9.1. La v9 avait été qualifiée par des contrôles déterministes et par une épreuve de décision sur scénarios ; aucun pilote ne l'avait encore conduite de bout en bout. Cette campagne l'a fait.

## Dispositif

- Onze petits programmes synthétiques en Python (journal radio de chantier), chacun dans son propre dépôt git, avec un mandat écrit : une démonstration préalable, puis dix essais T01–T10 lancés en parallèle.
- Pilote : `gpt-6.1-sol` (effort `medium`) par essai, avec les skills v9 installés dans le profil Codex. Tous ses sous-agents sont en `gpt-6.1-sol`, sans autre modèle.
- Chaque pilote remet un relevé typé : résultat, déroulé, incidents (gravité, règle en cause, commande et sortie, constaté ou supposé, correctif proposé), coût, règles utiles.
- La racine a revérifié chaque résultat déclaré : commits, contrôle d'acceptation, `rc_state.py check` sur chaque état.

Limites : produits minuscules, un seul modèle pour tous les acteurs, un essai par scénario. Ces essais révèlent des défauts ; ils ne mesurent ni gain ni taux de réussite.

## Résultats

| Essai | Objet | Issue | Acteurs |
|---|---|---|---|
| Démo | B1+B2 puis jardin | acceptée au 5e essai, après trois accords ajoutés au mandat | 4 |
| T01 | démarrage, B1+B2 parallèles, jardin | accepté | 7 |
| T02 | contrat créé par B1, consommé par B2/B3 | arrêt prématuré avant code | 1 |
| T03 | lot irréalisable (réseau interdit) | partiel : B1/B2 acceptés, B3 bloqué honnêtement | 2 |
| T04 | relais entre pilotes | partiel : B1 accepté, relais impossible | 4 |
| T05 | jardin avec invariant de sécurité | accepté, gardes de chemin conservées | 4 |
| T06 | migration à spécification contradictoire | décision humaine posée, lot entier suspendu | 0 |
| T07 | mode `prepare` | préparation remise, aucun lancement | 0 |
| T08 | superviseur séparé imposé | arrêt à l'amorçage, états invalides | 0 |
| T09 | ressource partagée | arrêt avant lancement sur la preuve du modèle | 1 |
| T10 | décision humaine manquante | accepté, B3 en attente correcte | 3 |

Quatre essais sur dix n'ont produit aucun code. Les essais acceptés ont tenu les garanties visées (faux verts refusés, invariant de sécurité préservé, aucun choix humain tranché par l'agent), mais au prix de 35 à 65 commandes d'état pour quelques dizaines de lignes de produit.

## Défauts et corrections

| Défaut | Essais | Correction v9.1 |
|---|---|---|
| Aucune commande de création d'état, alors que le contrat interdit l'écriture à la main | démo, T01–T10 | `rc_state.py init` (index ou vague détachée, révision 0, titulaire posé) |
| Un état initial mal formé ne peut plus être réparé (sans titulaire, `write` refuse) | démo, T08 | `init --replace-invalid --evidence`, ancien fichier conservé |
| Types des champs absents de la doc ; refus sans champ ni type | T08, démo | `init --template` imprime le squelette typé ; refus par champ, type attendu et reçu |
| Une fonction sans appelant gardée au nom du « comportement inchangé » | démo | `garden.md` : comportement observable défini ; code mort retiré avec ses tests |
| Un script qui relit et repasse la révision désarme `--expect-revision` | démo | règle explicite dans le contrat |
| `check_wave.py` refuse un état v2 valide | démo, T03 | rôle v1 seulement écrit dans le contrat |
| Revue « autre famille » contre un mandat mono-modèle | démo, T06, T10 | le mandat prime ; acteur distinct permis avec réserve |
| Rattachement runtime appliqué aux sous-agents natifs | démo | la règle vise les fils de premier niveau |
| Clone local Windows refusé (`dubious ownership` sur `.git`) | T01, T05, T10 | recette : `safe.directory` pour le dépôt et son `.git` |
| Lots consommant un contrat stable traités comme couplés (plan, intégrateur, revue d'intégration) | T01, T07, T09 | contrat commité et inchangé, ou auteurs sérialisés : pas de couplage |
| Contrôle complet exigé de chaque auteur d'une même copie, mêmes tests lancés plusieurs fois | T01, T03, T10 | boucle rapide par auteur, acceptation une fois sur l'assemblé ; une exécution si les collectes sont identiques |
| Retours de sous-agents enregistrés après la clôture (`late`) | T05, T10 | `event` dès la réception, avant disposition ou clôture |
| Aucun emplacement pour l'intention de relais entre pilotes ; `KeyError` brute | T04 | relais consigné dans `last_milestone` et `claim --takeover` ; refus explicite |
| Blocage faute de modèle exécuté attesté (`executedModel` nul) | T09 | fournisseur et modèle retournés suffisent, avec réserve |
| Conflit de ressources invisible entre admis de vagues différentes | T09 | `ready` signale `admitted-admitted` |
| Actions répétées par `resume` pour une même vague | T03 | actions dédupliquées |
| `candidate_seq: null` refusé malgré « valeur inconnue : null » | T05 | accepté pour une revue documentaire |
| Lot entier suspendu par une décision qui n'en touche qu'une partie | T06 | découper avant de suspendre |
| Arrêt au premier refus ou à la première revue négative | T02 | un refus ou un plan rejeté n'est pas une fin |
| Découpage initial erroné non corrigeable (résultats non supprimables) | T02 | clore `abandoned` avec source, ajouter les nouveaux |
| Préparateur distinct lancé par défaut | T01, T04, T09 | le pilote charge `rc-prepare-socle-prompts` lui-même |
| Politique propre à une vague inscrite dans `AGENTS.md` | T01 | elle va dans le mandat de vague |
| Revue globale exigée pour une seule petite vague à risque bas | T03 | la revue du candidat en tient lieu si elle couvre tout le livré |

## Ce qui a tenu

- Aucun pilote n'a accepté un `OK` de collecte vide (T02, T08, T10) ni un vert qui ne couvrait pas la portée (T03, T06).
- Le jardin de T05 a gardé les trois tests de refus de chemin, qui semblaient redondants, et retiré le code mort ; six mutations ont été détectées.
- T03 et T10 ont avancé l'indépendant pendant qu'un lot attendait, sans réveil fictif ni choix à la place de l'humain.
- `resume` et les révisions ont permis des reprises à froid sans relancer les champions (démo).

## Essais rejoués

Six essais ont été rejoués sur le premier candidat v9.1 (`205b50b`) : T01, T02, T04, T08 et T09 sont acceptés, T06 pose correctement sa décision mais garde suspendue la partie indépendante. Détail et limites : [qualification](qualification.md#version-v91-11-novembre-2026).

## Non qualifié

Les corrections postérieures à `205b50b` n'ont pas été rejouées. Le coût d'administration reste élevé : la v9.1 retire des cérémonies, mais n'en mesure pas le gain.
