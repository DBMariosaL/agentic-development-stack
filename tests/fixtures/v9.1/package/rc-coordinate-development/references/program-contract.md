# Contrat d'état — programme et vagues

Formats et règles communes aux trois skills RC ; le lire ne lance rien. Conduite : [boucle de pilotage](operating-loop.md).

## Outil

Toute création ou modification d'état passe par [rc_state.py](../scripts/rc_state.py) (`--help`, exemples compris), jamais par un script ad hoc ni à la main. Il contrôle titulaire, révision, verrous et déclarations, sans certifier autorité, revue ni exécution. `init` crée un index ou une vague détachée à la révision 0 avec titulaire ; `init --template program|wave` donne les types ; `--replace-invalid --evidence` remplace seulement un fichier initial écrit hors outil, invalide et sans autre titulaire, en conservant l'ancien. `--expect-revision` est la révision lue pour décider ; une relecture automatique désarme ce contrôle. `check_wave.py` vise seulement le format v1. `ready` donne le travail prêt et les conflits de ressources déclarées, y compris entre vagues admises ; `resume`, les actions de reprise. Un refus se corrige à sa cause, sans contournement ; une suite de commandes s'arrête au premier refus, et aucun lancement ne suit une porte non constatée ; sorties détaillées et refus inexpliqués : [moteur](engine.md).

## Fichiers et propriétaires

| Fichier | Contenu canonique | Écrivain |
|---|---|---|
| `program.json` (`rc-program/1`) | résultats et dépendances, statut, décisions en attente, dernier jalon, vagues | titulaire du programme |
| `wave.json` (`schema_version: 2`) | lots, artefacts, revues, acteurs, intentions, candidat | titulaire de la vague, normalement le pilote |
| `journal.jsonl` | événements reçus et décisions, en ajout seul | `rc_state.py` |

Ces fichiers seuls font foi ; un résumé ou tableau de suivi cite sa source et ne sert pas à décider. Décisions produit et backlog restent dans leur source projet. Sauf attribution, les enfants n'écrivent pas ces fichiers : ils remettent des deltas. `owner` vaut `{role, ref}` avec une référence réellement retournée, ou `null` ; reprise de propriété seulement sur transfert consigné ou arrêt constaté (`claim --takeover --evidence`).

Le dossier de vague (`wave.json`, mandats sous `socles/`, raccord commun, `supervisor.txt` pour un superviseur séparé, preuves sous `evidence/`) vit à un emplacement durable hors du dépôt produit ou dans un chemin qu'il ignore. Une preuve citée a une référence résoluble : chemin et empreinte, jamais l'empreinte seule. Le dépôt produit garde au plus une note courte par vague ; inventaires, patchs, bilans et reçus restent dehors ou regénérables.

## `program.json`

- `schema`, `revision`, `owner`, `mandate` (`ref`, `sha256`, `scope`, `exclusions`, `end_criteria`), `status`, `status_reason`.
- `skills_consumed` : `{name, sha256}` par skill chargé, empreinte de son `SKILL.md` ; elle identifie la version sans attester une lecture.
- `outcomes` : `id`, `outcome`, `depends_on`, `status`, `state_ref`, `waiting_on` (`null` ou `{kind, detail, trigger}`), `resources`, `next_action`, `closure` une fois clos (source et reste, ou cause et condition de reprise).
- `decisions_pending` (`id`, `question`, `option` concrète, `effects`, `suspends`) ; `last_milestone` (`{at, summary, ref}`).

**Prêt** : résultat `pending`, dépendances `accepted`, `waiting_on` nul, aucune décision qui le suspend. `abandoned` ou `accepted_partial` ne satisfont pas une dépendance dure ; une consommation partielle passe par un résultat distinct. Un résultat s'accepte à la clôture de sa vague : un résultat à accepter avant d'autres (contrat consommé, premier de lots sérialisés) a sa propre vague. Un découpage erroné se corrige sans supprimer : le résultat superflu se clôt `abandoned` avec sa source, les nouveaux s'ajoutent. Le programme attend (`waiting_*`) seulement sans travail prêt ni admis hors attente ; il est `completed` quand chaque résultat est accepté ou clos avec sa source.

## `wave.json` version 2

Valeur inconnue : `null` avec réserve, jamais un identifiant plausible.

- `mode` : `prepare` (documents et revues documentaires autorisés ; ni champion, ni superviseur, ni intégrateur, ni effet produit) ou `prepare-and-launch` ; activer un skill n'autorise rien.
- `project` (`root`, `baseline`, `observed_at`), `authorization` (`launch`, `source`, `scope`, `exclusions`), `artifacts` (nom → chemin relatif), `batches` (admissions proposées, pas barrières).
- `socles` : `id`, `outcome`, `depends_on`, `readiness` (`ready`, `partial` avec `ready_scope`/`blocked_scope`, `blocked`), `resources`, `source_refs`, `prompt_artifact`, `consumption_dependencies`.
- `reviews` : `artifact`, `sha256`, `status` (`done`, `pending`, `not_executed`, `not_required` motivé), `disposition`, `reference`, `candidate_seq` (absent ou `null` pour une revue documentaire, hors candidat). Une revue disposée (`done`, `not_required`) porte `disposition` (motif) et `reference` (source).
- `decisions` : textes courts : découpage, inconnus, chemins suspendus, ce qui continue, règles locales (boucle, section 5) et, quand le pilote supervise, dispositif d'intégration, approbations exigées et leurs octets, chemin des preuves, ressources réservées.
- `state` : `phase`, `owner`, `next_action`, `blockers`, `consumed` (artefact → `{version, sha256}`), `launch_ready`, `waiting` (`{kind, detail, trigger, resume, from}`).
- `candidate` (`{seq, ref, artifact, sha256, frozen_at}`, figé), `envelope` (borne de revue et `reason` ; atteinte, elle n'approuve rien), `actors`, `intents`, `revision`, `program_ref`.

Seul le titulaire met `launch_ready=true` : demande consignée, `project` complet, aucun bloqueur, mandats des lots admis consommés (et `supervisor` s'il existe), revues disposées sur les mêmes empreintes. Tout changement de ces éléments le remet à faux.

Phases terminales : `completed`, `completed_partial`, `failed`, `stopped`, sans relance ; une attente (`waiting_*`, `blocked`) revient à la phase active quittée. `completed` exige un candidat et des revues disposées de son artefact et de son SHA sur ce `candidate_seq`, sans intention `pending` ni acteur vivant ou `unknown` ; `completed_partial` nomme dans `decisions` la portée non qualifiée, `failed` sa cause et sa condition de reprise.

## Rapport de revue

`reviews.reference` désigne le rapport, que `disposition` résume sans remplacer. Chaque constat donne un identifiant stable entre tours, le candidat visé, le scénario et sa conséquence ; son origine (`introduit`, `préexistant` mais dans la portée si le delta l'expose ou l'aggrave, `inconnu`) ; son effet (`bloquant` pour une portée nommée, ou `non bloquant`) ; son issue et sa preuve :

- `corrigé` : preuve sur le nouveau candidat ;
- `faux positif` ou `intentionnel` : réfutation, ou contrat et décision cités, sans toucher le code sain ; intentionnel ne veut pas dire sûr ;
- `doublon` : relié au constat canonique, sans second correctif ;
- `reporté` : responsable, portée, suivi, autorité si le risque l'exige ;
- `ouvert`.

Un constat `ouvert` et `bloquant` interdit l'acceptation de sa portée, quels que soient notes, votes ou tours. Un constat disposé revient seulement avec une preuve nouvelle ; un non bloquant n'impose aucune retouche hors portée.

## Règles communes

- **Faits.** Sépare observé, historique, hypothèse et inconnu. Un ancien acteur ou un numéro de socle n'est pas une activité courante.
- **Modèles.** Respecte le choix demandé ; vérifie catalogue, paramètres et reçu de lancement. Si le modèle exécuté n'est pas exposé, fournisseur et modèle configuré retournés suffisent, avec réserve ; l'effort reste non attesté. Un modèle indisponible suspend son lancement, sans substitution silencieuse. Si le mandat impose une seule famille, un acteur distinct autorisé remplace la diversité de familles, avec réserve.
- **Contre-revue documentaire.** Un mandat de champion ou de superviseur séparé est contre-relu par un nouvel acteur seulement s'il ouvre un nouveau domaine, définit ou change une interface partagée, ou touche un chemin sensible ([risque](operating-loop.md#3-livrer-juste)) ; sinon sa revue s'inscrit `not_required` avec ce motif. Une revue interdite ou indisponible est `not_executed`, ne vaut pas accord et reste prérequise au lancement concerné. Un changement de statut n'ouvre ni rédaction ni revue.

## Filtres

Les instructions de mission et de projet priment. À défaut, classe séparément chaque livrable d'une même réponse et choisis son filtre par son seul destinataire direct ; ta filiation ne décide que de la remise à ton parent :

- prompt ou mandat pour une IA : optimiseur du modèle cible réellement visé, [gpt-prompt-optimizer](../../gpt-prompt-optimizer/SKILL.md) pour GPT, [claude-opus-prompt-optimizer](../../claude-opus-prompt-optimizer/SKILL.md) pour Opus (leur cible par défaut est datée) ;
- remise d'un enfant à son parent direct : optimiseur du modèle de ce parent, jamais [Unslop](../../unslop/SKILL.md) ; parent inconnu : le chercher dans le brief ou les métadonnées de délégation, sinon le demander ;
- livrable pour un humain : Unslop, invoqué explicitement.

Une seule passe par livrable, consignée, sans récursion ; le filtre ne remplace pas l'action demandée. Un skill requis indisponible est déclaré, ni simulé ni remplacé en silence ; un skill externe qu'ils citent (optimiseur Fable) sert seulement si la cible l'exige.
