# Mécanique du moteur `rc_state.py`

À lire seulement quand l'outil refuse et que son `error` ne suffit pas, qu'une opération d'écriture reste incertaine, ou pour le détail d'une reprise à froid, d'une adoption ou d'une migration. L'outil applique tout ce qui suit ; rien n'est à refaire à la main. Formats et règles de décision : [contrat d'état](program-contract.md).

## Formats

Champs complets que l'outil exige :

- `program.json` : `schema` (`rc-program/1`), `revision`, `owner`, `mandate`, `skills_consumed`, `status`, `status_reason`, `outcomes`, `decisions_pending`, `last_milestone`. `waiting_on.kind` parmi `human`, `quota`, `runtime`, `dependency`, `resource`. `admitted` exige `state_ref` ; admettre ou accepter exige des dépendances `accepted`. Une décision qui suspend un résultat va avec `waiting_on.kind = human` sur ce résultat, et réciproquement. `waiting_human` exige une décision en attente ; du travail prêt interdit tout statut d'attente ; une décision ne suspend pas un résultat clos.
- `wave.json` : `schema_version: 2`, `revision`, `mode`, `project`, `authorization`, `socles`, `batches`, `artifacts`, `reviews`, `decisions`, `state`, `program_ref`, `candidate`, `envelope`, `actors`, `intents`, `migrated_from` si issue d'une migration.
- `batches` : un ID n'y figure qu'une fois, après ses dépendances dures. Un cycle de `consumption_dependencies` exige le `ready_scope` d'amorçage de chaque participant et une décision qui le justifie.
- `artifacts` : chemins relatifs, sans sortie du dossier de vague. `reviews` : `done` exige des constats disposés ; une revue disposée exige `disposition` et `reference`.
- `program_ref` : chemin relatif d'un index existant dont un résultat référence la vague, ou `null` ; immuable une fois posé.
- `candidate` : `seq` croît à chaque candidat ; `artifact` est la clé de son manifeste et `sha256` son empreinte ; une revue de candidat porte `candidate_seq` et cite ce même artefact et ce même SHA.
- `envelope` : `null` ou objet avec `reason`.
- `actors` : `status` parmi `running`, `waiting`, `completed`, `failed`, `cancelled`, `interrupted`, `unknown`. Un acteur naît d'une intention de lancement confirmée, avec la cible de cette intention ; il n'est jamais retiré, seulement requalifié avec sa preuve ; deux acteurs vivants ne partagent pas une cible.
- `intents` : `op` parmi `launch`, `send`, `write`, `promote` ; `status` parmi `pending`, `confirmed`, `absent`, `failed`. Aucun nouveau lancement sur une cible dont un acteur est `running`, `waiting` ou `unknown`, ni dans une vague qui garde un acteur `unknown` sans cible ; l'outil l'applique à toute écriture. `clientRequestId` peut porter la corrélation, sans garantie établie de déduplication.
- `state.waiting` : `{kind, detail, trigger, resume, from}` obligatoire pour `blocked` et `waiting_*`, `null` sinon ; `from` est la phase active quittée et la seule où la sortie revient.
- `launch_ready` : tout changement de `project`, `authorization`, lots, batches, artefacts, consommations, revues ou candidat le remet à faux ; l'outil refuse une écriture qui le conserve. `prepare` impose `authorization.launch=false` et `launch_ready=false` ; les phases opérationnelles exigent mode, autorisation, titulaire et portée déclarés.

## Phases

| Depuis | Vers |
|---|---|
| `planning` | `preparing`, `blocked`, `stopped` |
| `preparing` | `ready`, `waiting_children`, `waiting_quota`, `blocked`, `stopped` |
| `ready` | `preparing`, `launched`, `stopped` |
| `launched`, `integrating` | entre elles, `waiting_children`, `waiting_quota`, `waiting_runtime`, `waiting_human`, `blocked`, `completed`, `completed_partial`, `failed`, `stopped`, `handed_off` |
| `waiting_*`, `blocked` | la phase active d'où l'attente est sortie, une autre attente, `failed`, `stopped` |
| `handed_off` | `launched`, `integrating` (par le nouveau titulaire) |

Un signal tardif sur une vague terminale est consigné au journal sans changer l'état.

## Événements

Chaque signal reçu a un identifiant stable (`taskId` + `runId`, ou équivalent retourné), unique pour tout le journal du programme. `event` le consigne et répond :

- `new` : à traiter, puis marqué appliqué par l'écriture qui le traite (`--applies-event`) ou par `ack` s'il ne change rien ;
- `unapplied` : reçu mais jamais appliqué (interruption entre réception et traitement) : le traiter maintenant ;
- `duplicate` : déjà appliqué, aucun effet ;
- `stale` : `candidate_seq` inférieur au candidat courant, consigné sans clore la version récente ;
- `late` : vague terminale, consigné sans relance ;
- `uncertain` : une écriture qui l'appliquait est restée sans validation : `reconcile` d'abord, aucun retraitement.

Un événement reçu avant la clôture de sa vague et jamais appliqué ne la rouvre pas : `dispose FICHIER --id … --disposition late|handled_elsewhere|not_applicable --evidence …`, après rattachement s'il est legacy ; le fichier de vague terminale reste inchangé. Une entrée porte l'identité de sa vague et ne s'applique qu'à elle ; reçue non appliquée puis dépassée par le candidat, elle devient `stale`. Une entrée d'une version antérieure, sans identité de vague, n'est ni appliquée ni reclassée avant `event --attach-legacy --evidence` ; l'entrée d'origine reste intacte et le rattachement est consigné à part.

## Écritures

Chaque écriture prend le verrou du fichier puis celui du journal ; un verrou présent est un refus, jamais un forçage. Un `.lock` laissé par un arrêt brutal se retire seulement après avoir constaté qu'aucun écrivain n'est actif. L'outil ne réutilise ni ne modifie aucune entrée qu'il n'a pas créée : temporaire exclusif propre à l'opération ; journal en fichier ordinaire à lien unique ; lien symbolique ou jonction sur l'état ou ses ancêtres refusés ; fichier inconnu préexistant (ancien `wave.json.tmp`) intact.

Une écriture a trois temps durables : ligne `prepare` au journal (révisions, empreintes avant/après, temporaire, événement appliqué), remplacement de l'état, ligne de validation. Un `prepare` sans validation est une **opération incertaine** : `resume` l'expose et échoue, l'événement concerné est `uncertain`, toute autre écriture du fichier est refusée. `reconcile FICHIER --op ID --evidence …` la résout : état égal à l'empreinte d'après → `committed` (l'événement devient appliqué) ; égal à celle d'avant → `not_committed` (l'événement reste à traiter, le temporaire propre est retiré) ; ni l'un ni l'autre → refus, puis déclaration sourcée `--declare committed|not_committed` par le titulaire ; une déclaration contraire aux octets est refusée. `reconcile` est réservé au titulaire, sauf l'auteur d'un `prepare` de type `claim` sur ce fichier, qui peut le conclure tant que l'état ne montre pas un autre titulaire, sans jamais déclarer validée une prise refusée par les octets.

Journaux participants d'un fichier : son journal courant, son journal local et tout journal listé par un `prepare` de ce fichier trouvé dans ces deux journaux. Une opération reste ouverte tant qu'un participant porte son `prepare` sans résolution ; `reconcile` la retrouve partout, complète les copies avec la même issue vérifiée sur les octets, refuse une contradiction, et répond `already_resolved` sans rien écrire si tout est clos. Le premier rattachement d'une vague détachée (`program_ref` posé alors qu'il était `null`) inscrit son opération dans le seul journal local, que la vague consulte ensuite comme participant. Avant ce rattachement, les événements du journal local appartenant à la vague sont appliqués ou disposés, et leurs identifiants reportés comme appliqués dans le journal du programme ; un reçu legacy sans identité qui peut concerner ce fichier bloque le rattachement jusqu'à `event --attach-legacy --evidence`, qui refuse un reçu dont le fichier d'origine connu est un autre. Les opérations à deux copies d'une version précédente restent couvertes. Ce mécanisme rend la fenêtre état/journal détectable ; il ne garantit pas l'idempotence d'un lancement T3. Une ligne de journal illisible est signalée par son numéro et se met de côté avec sa preuve avant toute autre action.

## Reprise à froid

`resume` donne titulaire, acteurs, intentions non résolues, opérations incertaines, événements reçus non appliqués avec leur vague, candidat, attentes et prochaine action, avec ses `actions`. Une opération incertaine se résout par `reconcile` avant toute écriture du même fichier. Intentions `pending` et acteurs `unknown` se rapprochent avant de relancer leur cible ; un acteur `unknown` sans cible connue bloque les lancements de sa vague jusqu'à son rapprochement.

## Adoption et migrations

Adopter une nouvelle version de la stack dans un programme en cours se fait à une frontière de vague stable : consigne les versions consommées dans `skills_consumed`, rapproche une fois les états concurrents (`suivi.json`, tableaux de suivi, `OWNERS.md` tenu en journal) vers `program.json` et les `wave.json`, fais pointer chaque résultat restant vers son état canonique, retire les attentes périmées avec leur preuve, ne recopie rien. Une vague active garde ses règles jusqu'à sa frontière.

Une migration de format produit un nouveau fichier sans modifier sa source : `rc_state.py migrate SOURCE DEST`, `DEST` existant refusé. La source v1 est d'abord validée avec [check_wave.py](../scripts/check_wave.py). v1 → v2 conserve tous les champs v1, place `runtime_refs` dans `state.legacy_runtime_refs` et crée pour chacun un acteur `legacy` `unknown`, qui bloque toute fin et tout lancement de la vague tant qu'il n'est pas requalifié ; elle initialise `revision: 0`, `intents`, `candidate: null` et enregistre `migrated_from`. Une vague v1 `completed` ou `completed_partial` n'est pas migrée : registre historique en lecture seule, référencé tel quel, sans candidat ni revue fabriqués. Une évolution future du schéma reçoit un numéro, une migration et des tests ; pas de nouvelle valeur dans un schéma fermé.
