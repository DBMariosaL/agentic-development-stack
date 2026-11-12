# Contrat d'état — programme et vagues

Source canonique des formats partagés par `rc-coordinate-development`, `rc-prepare-socle-prompts` et `rc-prepare-supervisor`, installés ensemble avec les trois skills de filtre de la section « Filtres ». Ce fichier est un contrat de données : le lire n'invoque aucun skill et ne lance rien. La conduite (choix, revues, continuité) est dans [la boucle de pilotage](operating-loop.md). Outil déterministe : [rc_state.py](../scripts/rc_state.py) ; il contrôle et écrit ces fichiers sous conditions, sans certifier autorité, revue ni exécution.

## Fichiers et propriétaires

| Fichier | Contenu canonique | Écrivain |
|---|---|---|
| `program.json` (schéma `rc-program/1`) | résultats du programme, dépendances entre résultats, statut du programme, décisions humaines en attente, dernier jalon, références aux vagues | le titulaire du programme (`owner`) |
| `wave.json` (`schema_version: 2`) | état opérationnel d'une vague : lots, artefacts, revues, acteurs, intentions, candidat | le titulaire de la vague, normalement le même pilote |
| `journal.jsonl` | événements reçus et décisions, en ajout seul ; jamais un état courant | `rc_state.py` pour le titulaire |

L'index référence les vagues par `state_ref` ; il ne recopie ni leur phase, ni leurs acteurs, ni leurs revues. Une donnée dérivée (résumé, tableau de jalon) cite sa source et ne sert pas à décider. Les décisions produit et le backlog restent dans leur source projet. Les enfants produisent artefacts et deltas proposés ; ils n'écrivent pas ces fichiers sauf attribution explicite.

Un seul titulaire par fichier. `owner` vaut `{role, ref}` avec une référence réellement connue (fil ou tâche retournés par le runtime), ou `null`. Chaque écriture par l'outil exige l'acteur titulaire et la `revision` lue ; une révision différente signifie qu'un autre écrivain est passé : relire, réconcilier, puis réessayer. Reprise de propriété seulement sur transfert consigné ou remplacement autorisé après arrêt constaté de l'ancien titulaire (`claim --takeover --evidence`).

## `program.json`

- `schema`: `"rc-program/1"` ; `revision`: entier, incrémenté à chaque écriture.
- `owner`, `mandate` (`ref`, `sha256` si connu, `scope`, `exclusions`, `end_criteria`), `skills_consumed` (liste `{name, sha256}` des `SKILL.md` et références réellement lus au démarrage).
- `status` : `active`, `waiting_human`, `waiting_quota`, `waiting_runtime`, `stopped`, `completed` ; `status_reason` texte.
- `outcomes` : objets `id`, `outcome`, `depends_on` (IDs de résultats), `status`, `state_ref` (chemin relatif du `wave.json` ou `null`), `waiting_on` (`null` ou `{kind, detail, trigger}` avec `kind` parmi `human`, `quota`, `runtime`, `dependency`, `resource`), `resources`, `next_action`. Pour `accepted_partial`, `abandoned` : `closure` (`source` de la décision, `remaining` décrit). Pour `failed` : `closure` avec cause et condition de reprise.
- `decisions_pending` : `id`, `question`, `option` (proposition concrète), `effects`, `suspends` (IDs suspendus seulement).
- `last_milestone` : `{at, summary, ref}` ; `ref` désigne le message ou l'artefact visible du jalon.

Statuts de résultat : `pending` (non admis), `admitted` (vague active, `state_ref` requis), `accepted`, `accepted_partial`, `failed`, `abandoned`, `blocked`. Un résultat est **prêt** s'il est `pending`, que toutes ses dépendances sont `accepted`, que `waiting_on` est nul et qu'aucune décision en attente ne le suspend. Une décision qui suspend un résultat va avec `waiting_on.kind = human` sur ce résultat, et réciproquement. Admettre ou accepter un résultat exige aussi des dépendances `accepted` : `abandoned` ou `accepted_partial` ne satisfont pas une dépendance dure ; une consommation partielle passe par un résultat distinct qui nomme la portée acceptée. Les conflits de ressources calculés par `ready` (entre résultats prêts, et avec les résultats admis) ne portent que sur les ressources déclarées : la réservation réelle reste à faire. Un échec de lot ne termine pas le programme.

Statuts de programme :

- `active` : du travail est prêt ou admis.
- `waiting_human` / `waiting_quota` / `waiting_runtime` : aucun résultat prêt ni admis sans attente ; la raison et le déclencheur attendu sont écrits. `waiting_human` exige au moins une décision en attente. Du travail prêt interdit tout statut d'attente.
- `stopped` : arrêt explicite par l'autorité du mandat, source citée.
- `completed` : chaque résultat est `accepted`, ou clos `accepted_partial`/`abandoned` avec sa source. Un programme dont le reste dépend d'un humain est en attente, jamais terminé.

## `wave.json` version 2

Le dossier de vague contient `wave.json`, les mandats des champions sous `socles/`, leur raccord commun si nécessaire, `supervisor.txt` et les preuves sous `evidence/`, seulement quand ils servent. Valeur inconnue : `null` avec une réserve, jamais un identifiant plausible inventé.

Champs hérités de la version 1 (règles inchangées) :

- `mode` : `prepare` (aucun champion, superviseur, intégrateur ni effet produit ; auteurs et revues documentaires si la mission les autorise) ou `prepare-and-launch`. L'activation d'un skill ne donne aucune autorisation produit.
- `project` : `root`, `baseline`, `observed_at` ; une base historique est étiquetée historique.
- `authorization` : `launch` (booléen), `source` (demande applicable), `scope` (actions/cibles couvertes), `exclusions`.
- `socles` : `id`, `outcome`, `depends_on` (IDs de la vague), `readiness` (`ready`, `partial`, `blocked`), `resources`, `source_refs`, `prompt_artifact` (clé du mandat couvrant un lot admis). `partial` précise `ready_scope`/`blocked_scope`. `consumption_dependencies` : `producer`, `artifact`, `consumer_scope`, `continue_scope` ; dans un cycle de consommation, chaque participant décrit son `ready_scope` d'amorçage et une décision le justifie.
- `batches` : admission simultanée proposée, pas barrière de fin de lot ; un ID n'y figure qu'une fois, après ses dépendances dures. Au runtime, seuls ressource libre et prérequis réellement satisfaits comptent.
- `artifacts` : nom → chemin relatif au dossier de vague, sans sortie du dossier.
- `reviews` : `artifact` (clé), `sha256`, `status` (`done`, `pending`, `not_executed`, `not_required`), `disposition`, `reference`. `done` exige des constats disposés ; `not_required` exige le motif applicable.
- `decisions` : justifications courtes du découpage, inconnus, chemins suspendus et travail qui continue.
- `state` : `phase`, `owner`, `next_action`, `blockers`, `consumed` (nom d'artifact → `{version, sha256}`), `launch_ready` (faux par défaut).

Seul le titulaire met `launch_ready=true`, après demande applicable consignée, contexte constaté (`project` complet), portée réalisable, aucun bloqueur, mandats de tous les lots admis non bloqués consommés (et `supervisor` s'il existe) et revues disposées sur les mêmes empreintes. Tout changement de `project`, `authorization`, lots, batches, artefacts, consommations, revues ou candidat remet ce drapeau à faux jusqu'à réconciliation ; l'outil refuse une écriture qui le conserve. `prepare` impose `authorization.launch=false` et `launch_ready=false` ; les phases opérationnelles exigent mode, autorisation, titulaire et portée déclarés.

Ajouts de la version 2 :

- `schema_version: 2`, `revision`, `migrated_from` si issue d'une migration, `program_ref` : chemin relatif d'un index existant dont un résultat référence cette vague, ou `null` ; immuable une fois posé.
- `candidate` : `null` ou `{seq, ref, artifact, sha256, frozen_at}`. `seq` croît à chaque nouveau candidat ; `artifact` est la clé de son manifeste dans `artifacts` et `sha256` l'empreinte de ce manifeste ; un candidat figé ne change plus. Une revue de candidat porte `candidate_seq` et cite ce même artefact et ce même SHA.
- `envelope` : enveloppe de revue choisie pour la vague (`review_rounds` ou autre borne, motif). Une borne atteinte n'est ni une approbation ni une fermeture de défaut.
- `actors` : `role`, `model`, `ref` (identifiants réellement retournés), `correlation`, `target`, `status` (`running`, `waiting`, `completed`, `failed`, `cancelled`, `interrupted`, `unknown`), `candidate_seq` traité. Un acteur naît d'une intention de lancement confirmée, avec la cible de cette intention ; il n'est jamais retiré, seulement requalifié (avec sa preuve) ; deux acteurs vivants ne partagent pas une cible.
- `intents` : `correlation`, `op` (`launch`, `send`, `write`, `promote`), `target`, `status` (`pending`, `confirmed`, `absent`, `failed`), `result_ref`. Une intention est écrite **avant** l'appel ; aucun nouveau lancement sur une cible dont un acteur est `running`, `waiting` ou `unknown`, ni dans une vague qui garde un acteur `unknown` sans cible connue ; l'outil l'applique à toute écriture, pas seulement à `intent add`. `clientRequestId` peut porter la corrélation, mais sa déduplication n'est pas une garantie établie.
- `state.waiting` : `{kind, detail, trigger, resume, from}` obligatoire pour `blocked` et les phases `waiting_*`, `null` sinon ; `resume` dit concrètement comment reprendre ; `from` est la phase active quittée (dérivée de l'ancienne phase, `null` seulement pour une migration ou une phase sans origine active) et la seule où la sortie revient.

Phases et transitions autorisées :

| Depuis | Vers |
|---|---|
| `planning` | `preparing`, `blocked`, `stopped` |
| `preparing` | `ready`, `waiting_children`, `waiting_quota`, `blocked`, `stopped` |
| `ready` | `preparing`, `launched`, `stopped` |
| `launched`, `integrating` | entre elles, `waiting_children`, `waiting_quota`, `waiting_runtime`, `waiting_human`, `blocked`, `completed`, `completed_partial`, `failed`, `stopped`, `handed_off` |
| `waiting_*`, `blocked` | la phase active d'où l'attente est sortie (`preparing`, `launched`, `integrating`), une autre attente, `failed`, `stopped` |
| `handed_off` | `launched`, `integrating` (par le nouveau titulaire) |

`completed`, `completed_partial`, `failed`, `stopped` sont terminaux : aucune transition ni relance. Un signal tardif est consigné au journal sans changer l'état ; une reprise passe par une nouvelle vague. `completed` exige un candidat, des revues disposées de son artefact et de son SHA sur ce `candidate_seq`, aucune intention `pending`. Toute phase terminale exige aussi qu'aucun acteur ne soit `running`, `waiting` ou `unknown`. `completed_partial` exige en plus la portée non qualifiée dans `decisions` ; `failed` sa cause et sa condition de reprise. Une fin de tour, un quota ou une notification `finished` ne produisent jamais une phase terminale.

## Rapport de revue

`reviews.reference` désigne le rapport qui porte les constats ; `disposition` les résume sans les remplacer. Le schéma reste fermé : ces données vivent dans le rapport, sans registre courant concurrent. Chaque constat donne :

- un identifiant stable d'un tour à l'autre, le candidat visé (`candidate_seq`, SHA ou manifeste), le scénario et sa conséquence ;
- l'origine : `introduit`, `préexistant` ou `inconnu` ; un défaut préexistant que le delta expose ou aggrave reste dans la portée ;
- l'effet sur l'acceptation : `bloquant` pour une portée nommée, ou `non bloquant` ;
- l'issue et sa preuve : `corrigé` (preuve sur le nouveau candidat), `faux positif` (réfutation), `intentionnel` (contrat ou décision cités ; intentionnel ne veut pas dire sûr), `doublon` (identifiant du constat canonique), `reporté` (responsable, portée, suivi et, si le risque l'exige, autorité qui l'accepte) ou `ouvert`.

Un constat `ouvert` et `bloquant` interdit l'acceptation de sa portée, quels que soient notes, votes ou nombre de tours.

## Événements

Chaque signal reçu reçoit un identifiant stable (`taskId` + `runId`, ou équivalent retourné). `rc_state.py event` le consigne au journal et répond :

- `new` : à traiter, puis à marquer appliqué par l'écriture qui le traite (`--applies-event`) ou par `ack` s'il ne change rien ;
- `unapplied` : déjà reçu mais jamais appliqué (interruption entre réception et traitement) : le traiter maintenant ;
- `duplicate` : déjà appliqué, aucun effet ;
- `stale` : il porte un `candidate_seq` inférieur au candidat courant, consigné sans clore la version récente ;
- `late` : la vague est terminale, consigné sans relance ;
- `uncertain` : une écriture qui l'appliquait est restée sans validation au journal : `reconcile` d'abord, aucun retraitement.

Un événement reçu avant la clôture de sa vague et jamais appliqué ne rouvre pas la vague : son titulaire consigne sa disposition au journal (`rc_state.py dispose FICHIER --id … --disposition late|handled_elsewhere|not_applicable --evidence …`), après rattachement s'il est legacy ; le fichier de vague terminale n'est pas modifié.

Chaque entrée porte l'identité de sa vague (chemin relatif au journal) ; un événement ne s'applique qu'à la vague qui l'a reçu. Un événement reçu non appliqué qui revient après l'avancée du candidat est reclassé `stale`. `resume` liste les événements reçus non appliqués avec leur vague. Une entrée écrite par une version antérieure de l'outil, sans identité de vague, n'est ni appliquée ni reclassée tant qu'elle n'est pas rattachée à sa vague par `event --attach-legacy --evidence` ; l'entrée d'origine reste intacte et le rattachement est consigné à part. L'identifiant est unique pour tout le journal du programme.

## Écritures

Chaque écriture de l'outil prend le verrou du fichier puis celui du journal avant de remplacer le fichier ; un verrou présent est un refus, jamais un forçage. Le fichier `.lock` laissé par un arrêt brutal se retire seulement après avoir constaté qu'aucun écrivain n'est actif.

L'outil ne réutilise ni ne modifie aucune entrée qu'il n'a pas créée : le nouvel état passe par un temporaire créé exclusivement sous un nom propre à l'opération ; le journal doit être un fichier ordinaire à lien unique (sinon refus, avant tout changement d'état) ; un lien symbolique ou une jonction sur le fichier d'état ou ses ancêtres est refusé. Un fichier préexistant inconnu (ancien `wave.json.tmp` par exemple) reste intact.

Une écriture se déroule en trois temps durables : ligne `prepare` au journal (révisions, empreintes avant/après, temporaire, événement appliqué éventuel), remplacement de l'état, ligne de validation (`commits`). Une ligne `prepare` sans validation est une **opération incertaine** : `resume` l'expose et échoue, l'événement concerné est classé `uncertain` au lieu de « non appliqué », et toute autre écriture du même fichier est refusée. `rc_state.py reconcile FICHIER --op ID --evidence …` la résout : état identique à l'empreinte d'après → `committed` (l'événement devient appliqué) ; identique à l'empreinte d'avant → `not_committed` (l'événement reste à traiter, le temporaire propre est retiré) ; ni l'un ni l'autre → refus, puis déclaration sourcée `--declare committed|not_committed` par le titulaire. Une déclaration contraire aux octets est refusée. `reconcile` est réservé au titulaire du fichier, avec une seule exception : l'auteur d'un `prepare` de type `claim` sur ce même fichier (premier titulaire ou reprise interrompue), qui peut le conclure tant que l'état ne montre pas un autre titulaire ; il ne peut jamais déclarer validée une prise refusée par les octets. Les journaux participants d'un fichier sont son journal courant, son journal local (à côté du fichier) et tout journal listé par un `prepare` de ce fichier trouvé dans ces deux journaux, ouvert ou clos. Une opération reste ouverte tant qu'un participant porte son `prepare` sans validation ni résolution : toute écriture du fichier est alors refusée, `resume` la signale (pour le programme et chaque vague référencée) et `reconcile` la retrouve par son identité dans tous les participants. Si une copie est déjà close, `reconcile` complète les autres avec la même issue, vérifiée sur les octets ; une contradiction entre copies est refusée ; une réconciliation répétée d'une opération entièrement close répond `already_resolved` sans rien écrire. Le premier rattachement d'une vague détachée (`program_ref` posé alors qu'il était `null`, par exemple après migration) inscrit son opération dans le seul journal local, puis la vague consulte aussi ce journal comme participant : aucune copie partielle n'est possible. Avant ce rattachement, les événements du journal local appartenant explicitement à la vague (reçus avec son identité ou rattachés avec preuve) doivent être appliqués ou disposés ; leurs identifiants sont reportés comme appliqués dans le journal du programme. Un reçu legacy sans identité qui peut concerner ce fichier (même nom de fichier d'origine, ou fichier inconnu) bloque le rattachement jusqu'à `event --attach-legacy --evidence` ; un reçu legacy d'un autre fichier n'est ni reporté ni bloquant. `event --attach-legacy` refuse un reçu dont le fichier d'origine connu est un autre fichier. Les opérations à deux copies écrites par la version précédente de l'outil restent couvertes par ces règles. Ce mécanisme rend la fenêtre état/journal détectable ; il ne garantit pas l'idempotence d'un lancement T3. Une ligne de journal illisible (écriture interrompue) est signalée par son numéro ; elle se met de côté avec sa preuve avant toute autre action.

Les commandes `check`, `ready` et `resume` échouent tant que l'état est incohérent ; leur vue ne sert alors qu'au rapprochement.

## Migrations de format

Une migration produit un nouveau fichier et ne modifie jamais sa source : `rc_state.py migrate SOURCE DEST`. `DEST` existant est refusé. La source v1 est d'abord validée avec [check_wave.py](../scripts/check_wave.py), validateur historique conservé pour ce format. v1 → v2 conserve tous les champs v1, place `runtime_refs` dans `state.legacy_runtime_refs` et crée pour chacun un acteur `legacy` au statut `unknown`, que `resume` désigne au rapprochement et qui bloque toute fin de vague et tout lancement de cette vague tant qu'il n'est pas requalifié ; elle initialise `revision: 0`, `intents`, `candidate: null` et enregistre `migrated_from` (`schema_version`, `sha256`, chemin). Une vague v1 `completed` ou `completed_partial` n'est pas migrée : elle reste un registre historique en lecture seule, référencé tel quel par l'index, sans candidat ni revue fabriqués. Les consommateurs adoptent la version 2 à une frontière de vague stable ; une vague active garde son format jusqu'à cette frontière. Une évolution future du schéma reçoit un numéro, une migration et des tests ; pas de nouvelle valeur injectée dans un schéma fermé.

## Filtres et revues documentaires

Les instructions de mission, de projet et de filiation priment. À défaut, le filtre dépend du seul destinataire direct de chaque livrable, classé séparément :

- prompt ou mandat destiné à une IA : optimiseur du modèle cible, [gpt-prompt-optimizer](../../gpt-prompt-optimizer/SKILL.md) pour GPT, [claude-opus-prompt-optimizer](../../claude-opus-prompt-optimizer/SKILL.md) pour Opus ; nommer le modèle réellement visé, car la cible par défaut de ces copies est datée ;
- remise d'un enfant à son parent direct : optimiseur du modèle de ce parent, jamais [Unslop](../../unslop/SKILL.md) ; parent inconnu : le chercher dans le brief ou les métadonnées de délégation, sinon le demander ;
- livrable destiné à un humain : Unslop, invoqué explicitement.

Une seule passe par livrable, consignée, sans récursion. Le filtre ne remplace pas l'action demandée : modifications, commandes et vérifications restent à exécuter. Un skill requis indisponible est déclaré, ni simulé ni remplacé en silence. Ces trois skills sont livrés avec le paquet ; leurs faits fournisseurs datent de leur copie et ne sont pas revérifiés par elle. Un autre skill qu'ils citent, comme l'optimiseur Fable, reste externe : utilisé seulement si la cible l'exige et s'il est disponible.

Une revue nouvelle a un mandat et un acteur distincts ; une revue interdite ou indisponible est déclarée non exécutée et ne vaut pas accord.
