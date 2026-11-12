# Qualification

## Version v9.1.1 (11 novembre 2026)

Statut : **acceptée dans la portée locale implémentée** le 11 novembre 2026, sur trois corrections tirées des deux essais de contrôle de la v9.1 publiée (`ab6bba7`).

- Contrôles de la v9.1 : T06 a découpé le lot partiellement suspendu (écriture v2 livrée et acceptée, lecture v1 seule en attente de décision). T01 s'est arrêté sur une ambiguïté sans enjeu (`message(s)`), que les essais précédents tranchaient par le format littéral du mandat : régression d'autonomie introduite par la règle « critère ambigu → question ».
- Corrections : la question n'est due que si le choix change un effet protégé par le mandat (données, contrat, droits, comportement visible), et une forme écrite littéralement fait foi ; les refus d'une vague v2 perdent le préfixe `v1-fields:` ; `init --template` indique que `prompt_artifact` est dû avant `launch_ready=true`.
- Contrôles déterministes : `tools/check.py` vert, avec deux tests d'état ajoutés et la suite `updater-from-v9.1` (mise à jour d'une installation v9.1 reconstituée depuis `tests/fixtures/v9.1/`).
- Rejeu de T01 sur le candidat `b2962b0` : accepté, format littéral appliqué sans question, jardin fait (collecte 16 → 9, sept identités retirées justifiées), cinq acteurs `gpt-6.1-sol`.
- Revue : changement à risque bas (texte d'une règle, deux messages et un gabarit du moteur), accepté par la racine sur ces preuves, sans revue GPT distincte.
- Limites : un seul rejeu ; coût d'administration toujours élevé (61 commandes d'état et 40 écritures pour T01).

## Version v9.1 (11 novembre 2026)

Statut : **acceptée dans la portée locale implémentée** le 11 novembre 2026, après deux revues GPT-6.1-SOL xhigh et la vérification par la racine de la dernière correction. Aucune installation dans un profil actif au moment de l'acceptation.

### Origine

Campagne d'essais réels de la v9 : une démonstration et dix essais T01–T10, chacun conduit par un pilote `gpt-6.1-sol` dont tous les sous-agents sont `gpt-6.1-sol`. Résultats, défauts et corrections : [campagne v9.1](campagne-v9.1.md).

### Revues

- Candidat `205b50b` : revue R1, verdict « accepter après corrections », aucun P1. Trois P2 : `--replace-invalid` pouvait réinitialiser un index créé par l'outil ; une création sans entrée de journal restait valide et continuable ; le relais de pilote n'avait pas de trace durable avant l'appel. Deux P3 : temporaire orphelin après un remplacement refusé sous Windows ; lecture obligatoire en hausse, avec sept coupes proposées.
- Candidat `f761962` : revue R2 sur le delta. Les cinq constats R1 sont fermés sur preuve, dont une sonde Windows indépendante avec un handle réel ; le relais est fermé par protocole documentaire, sans changement de schéma ni garantie d'idempotence runtime. Un nouveau P3 : la section de qualification annoncée par le README manquait. Elle est ajoutée ici ; la racine a vérifié cette correction et les trois précisions issues de l'essai T04 rejoué (lancement d'un champion depuis une vague rattachée et `launched`, champs d'une revue disposée, exemple `init`) par le contrôle complet vert sur le commit d'acceptation, sans troisième revue, conformément à la règle de convergence.

### Contrôles déterministes

`python -B tools/check.py` exécute `inventory`, `state`, `updater-v7`, `updater-v8`, `updater-from-v8`, `updater-from-v9`, `package` et `structure` ; collectes déclarées dans `EXPECTED`.

- `state` : les 142 tests v9 inchangés, plus `tests/state/test_rc_state_v91.py` (création, squelette, remplacement d'un état initial invalide, cycle durable de `init` et sa réconciliation, refus après historique, messages par champ, intentions refusées sur l'index, chemins de liste refusés, déduplication de `resume`, conflits entre vagues admises, `candidate_seq` nul).
- `updater-from-v9` : mise à jour réelle d'une installation v9 reconstituée octet pour octet depuis `tests/fixtures/v9/` (manifeste et fichiers RC propres à la v9), `tests/fixtures/v8/`, `tests/fixtures/v7/` et les dépendances identiques.
- Les 19 états produits par les essais v9 restent valides avec le moteur v9.1 (sonde de la revue R1).

### Essais rejoués

Six essais rejoués sur le candidat `205b50b`, mêmes mandats, mêmes modèles, skills lus depuis un instantané du paquet :

| Essai | v9 | v9.1 (`205b50b`) |
|---|---|---|
| T01 démarrage et jardin | accepté, 7 acteurs | accepté, 4 acteurs |
| T02 contrat consommé | arrêt avant code | accepté |
| T04 relais entre pilotes | relais impossible | accepté, chaîne de trois pilotes |
| T06 spécification contradictoire | lot suspendu | décision posée ; partie indépendante encore suspendue |
| T08 superviseur séparé | arrêt à l'amorçage | accepté |
| T09 ressource partagée | arrêt sur la preuve du modèle | accepté, après une décision du mandant |

Chaque état a été créé par `rc_state.py init`. Les incidents restants des rejeux ont nourri le delta `205b50b..` : acceptation d'un résultat à la clôture de sa vague, arrêt au premier refus, exemples `write --help`, chemins de liste refusés, suspension partielle explicite, critère ambigu posé avant lancement, commande de clone Windows complète, champion lancé seulement depuis une vague `launched`.

### Limites

- Les rejeux portent sur `205b50b` ; les corrections suivantes n'ont pas été rejouées.
- Petits programmes synthétiques, un seul modèle pour tous les acteurs, un essai par scénario : aucun taux de réussite ni gain de coût n'est revendiqué.
- T06 n'a toujours pas découpé le lot partiellement suspendu malgré la règle ; la formulation plus concrète du candidat final n'a pas été rejouée.
- Le coût d'administration reste élevé (35 à 90 commandes d'état par essai). La lecture obligatoire du pilote passe de 3 527 à environ 3 950 mots.
- Installation, reprise runtime réelle et comportement hors de ces essais : non qualifiés.

## Version v9 « jardin » (10 novembre 2026)

Statut : **acceptée dans la portée locale implémentée** le 10 novembre 2026. Aucune installation dans un profil actif.

### Revues

- Plan : quatre analyses Opus (vidéo, retours d'expérience Alpha Radio Chantier et rc-alpha, auto-audit v8), puis une contre-revue GPT-6.1-SOL xhigh. Verdict : GO avec corrections. Ses trois P1 ont été intégrés à l'arbitrage avant l'implémentation : obligations du gabarit transférées avant la suppression de l'auto-mandat, isolation des cibles destructives à chaque exécution, aucun critère automatique d'élagage.
- Candidat `5fb2de6` : revue d'acceptation GPT-6.1-SOL xhigh R1, verdict « accepter après corrections », aucun P1. Trois P2 : statut v8 resté dans la documentation, campagne non livrée, fin de mission du superviseur séparé contradictoire. Trois P3 : cardinalité des tests, oracle Q14, sorties d'erreur réelles de `rc_state.py`. Tous corrigés dans le delta suivant.
- Candidat `26b43b2` : revue R2 GPT-6.1-SOL xhigh sur le delta. Les six constats R1 sont fermés sur preuve et il n'y a aucun P1. Trois nouveaux constats ont été corrigés : un P2 sur le contrat de gel des scénarios, contredit par le ré-épinglage (l'original est restauré et la révision publiée à part), et deux P3 de formulation (README, attribution de Q21). La racine a vérifié ces corrections par le contrôle complet vert sur le commit d'acceptation ; elles n'ont pas reçu de troisième revue, conformément à la règle de convergence.

### Contrôles déterministes

`python -B tools/check.py` exécute `inventory`, `state`, `updater-v7`, `updater-v8`, `updater-from-v8`, `package` et `structure`. Les collectes attendues sont déclarées dans `tools/check.py` (`EXPECTED`) et le résultat de chaque exécution est dans son `summary.json`. Les comptes ne sont pas recopiés ici.

- Les racines des profils factices sont désormais hors du clone : `RC_CHECK_FIXTURES_ROOT` ou le dossier temporaire système. Un préflight refuse une base trop longue. En v8, un clone profond sous Windows (`LongPathsEnabled=0`) produisait 27 échecs trompeurs de mise à jour.
- `updater-from-v8` éprouve une vraie mise à jour d'une installation v8. Le paquet v8 est reconstitué octet pour octet depuis `tests/fixtures/v8/` (manifeste et fichiers RC propres à la v8), `tests/fixtures/v7/` et les dépendances identiques. Cas éprouvés : remplacement des seuls fichiers RC, dépendances intactes, édition locale refusée, interruption puis reprise, retour arrière vers les octets v8.
- `package` vérifie aussi `scenarios-v9.json` et sa révision `scenarios-v9-r1.json` : empreintes épinglées, Q1–Q11 identiques à la v8, seul l'oracle de Q14 différent entre les deux, cas nouveaux jugeables.
- Gelés : `rc_state.py`, `check_wave.py` et leurs 142 tests d'état. Aucun test existant n'a été retiré.

### Épreuve de conduite exploratoire v8/v9

`tests/qualification/scenarios-v9.json` fixe 21 scénarios : Q1–Q11 repris de la v8, et Q12–Q21, des cas de jardinage et d'autonomie (6 décisions, 4 manipulations observables). Empreinte : `8f054c906bb4f64bf39d416bfb0ba81c9e3a2b608c0d83bd23c3a9bdcfd19d0d`. Le fichier v8 reste inchangé (`a050ce188ca4819d62080c334024ccaafd379c1ec1f035a2794436adfcbc26ba`). La correction a utilisé la révision `scenarios-v9-r1.json` (`8b998599c146b3a889652eca01dbcd9595ab26e1e3bf087db5c762d29d6e3f52`), qui ne change que l'oracle de Q14 (voir les limites).

Dispositif : un pilote GPT-6.1-SOL high par version. Chaque pilote ne reçoit que les skills de sa version (v8 : `22b05e2`, v9 : `5fb2de6`) et les scénarios sans oracles. Il construit la matière synthétique des manipulations et laisse ses observables sur disque. Correction aveugle par deux correcteurs indépendants, Opus 5.5 et GPT-6.1-SOL high, contre les oracles. Copies anonymisées X/Y, chemins et en-têtes de version retirés.

| Correcteur | Version | Q1–Q11 réussi/partiel/échoué | Q12–Q21 réussi/partiel/échoué | Inconnu |
|---|---|---|---|---|
| Opus 5.5 | v8 | 10/1/0 | 6/2/2 | 0 |
| Opus 5.5 | v9 | 10/1/0 | 9/1/0 | 0 |
| GPT-6.1-SOL | v8 | 8/3/0 | 6/2/2 | 0 |
| GPT-6.1-SOL | v9 | 8/3/0 | 8/2/0 | 0 |

Les deux correcteurs relèvent les deux mêmes échecs, tous deux sur v8 :
- Q16 : fin de tour sans réveil réel pendant qu'un enfant travaille ;
- Q19 : revue GPT ajoutée pour une entrée unique à risque bas déjà prouvée.

Sur Q1–Q11, les deux versions obtiennent le même résultat. Défaut commun aux deux versions :
- Q8 : filiation étendue à tous les livrables, sans passe Opus sur le mandat ni Unslop sur la note humaine ;

Défaut propre à la v9, relevé par les deux correcteurs (leurs avis divergent sur la v8) :
- Q21 : contrôle remplaçant le cliquet qui n'arrête pas une identité disparue sans justification.

Deux phrases ont été corrigées après l'épreuve, dans `program-contract.md` (« Filtres ») et `garden.md` (« Valeur des tests »). Ce delta n'a pas été remesuré.

Limites :
- une exécution par version ;
- des correcteurs qui peuvent reconnaître la version à ses références (`garden.md`) ;
- des oracles écrits par l'équipe qui a conçu la v9 ;
- un oracle Q14 assoupli après la réponse du pilote v8 et avant toute correction, sur constat de la revue R1 : deux doublons symétriques sont acceptés indifféremment ; l'original figé reste `scenarios-v9.json`, la révision est publiée à part (`scenarios-v9-r1.json`) et les verdicts lui sont attribués ;
- la matière des manipulations construite par chaque pilote.

Ces résultats sont des observations exploratoires, pas une mesure de fiabilité ni un gain d'autonomie. Transcriptions, réponses et verdicts restent dans les archives locales de la session.

### Limites v9

- Aucune installation active ; découverte des six skills en conversation neuve non constatée.
- Reprise runtime (réception d'un réveil, interruption et reprise du même titulaire) non qualifiée : distincte de l'épreuve de prompts.
- `provenance.json` couvre toujours les fichiers écrits dans ce dépôt ; sa réduction aux copies vendored (C4) est différée.
- Les cycles de jardinage, l'environnement `AGENTS.md` et les règles d'élagage n'ont pas encore été appliqués à un programme produit réel. Leur effet sur rc-alpha reste à observer à la prochaine vague.
- Les limites v8 et v7 ci-dessous restent valables pour le moteur d'état et l'outil de mise à jour.

## Version v8 acceptée localement (9 novembre 2026)

Statut : **acceptée dans la portée locale implémentée**, après rapprochement de la contre-revue indépendante et du contrôle complet par le pilote. Aucune installation dans un profil actif n'a été effectuée.

### Preuves d'acceptation

- Implémentation contre-revue : commit `dbe47f3a9f0fca182dbee826e48986ceec02aaa7`, arbre `558c3ff927bafad9a87a5cc7a686d7cd86328aed`.
- Contrôle complet : 142 tests d'état, 30 de compatibilité v7, 28 de mise à jour v8 et 22 de paquet, soit **222 tests**, puis **347 contrôles structurels**, sans échec ni test ignoré. Les empreintes de toutes les entrées éprouvées ont été rapprochées des sources commitées. Le contrôle a commencé avant le commit de ces mêmes octets ; seule la métadonnée Git a changé pendant son exécution.
- Contre-revue GPT-6.1-SOL xhigh R1 : deux constats P2, application d'un plan v1 valide et omission d'un `expectedFailure` par le collecteur. Corrigés, puis fermés par R2 sur le delta : sept régressions ciblées vertes et 99 empreintes concordantes. Aucun nouveau défaut décisif établi dans cette portée.
- Manifeste du paquet : `574cc3376f29be59d77fc2b56f9fa63c3fbf1a3804d254a39905047190c1cfa8`, distribution `rc-core-with-dependencies`, 46 fichiers. Les 34 fichiers des trois dépendances restent identiques à l'instantané source.
- Rapport indépendant R2 : SHA-256 `14ea4043cf0c74a723e33b0a73c6e415644735397052a27cf55059a08a959c3d`. Résumé du contrôle complet : SHA-256 `ea7d9d4010152d995d45afd4ddd41576812d8a5c4bb2c0728fac7e38dbbe6650`. Ces pièces restent dans les archives locales de développement.

La clôture après R2 ne modifie que le statut de version dans README, ce document et le champ `status` de `provenance.json`. Elle reçoit un contrôle d'inventaire, de liens locaux et de structure distinct ; les outils, le paquet et les tests éprouvés restent identiques. Les essais de conduite d'agents et l'installation active restent hors acceptation.

### Contrôles déterministes

`python -B tools/check.py` exécute, sur ce candidat seulement :

| Étape | Contenu | Collecte attendue |
|---|---|---|
| `inventory` | `manifest.json` contre `package/`, `provenance.json` contre chaque fichier listé | — |
| `state` | régressions d'état v7, inchangées, sur `package/` | 142 |
| `updater-v7` | `tests/updater/test_rc_update.py`, inchangé, sur la fixture v7 (31 octobre vers v7) | 30 |
| `updater-v8` | distribution v8 et compatibilité des plans v1 sur profils factices | 28 |
| `package` | paquet déplacé, ressources, métadonnées, scripts, collecte et scénarios figés | 22 |
| `structure` | `tools/validate_package.py` avec provenance | aucun échec |

Les 30 tests historiques de mise à jour visent désormais la fixture `tests/fixtures/v7/` au lieu de `package/` : leurs assertions (dont le compte de 12 fichiers) décrivent le paquet v7 et la transition entre manifestes à trois skills. Le fichier de test est inchangé ; ses garanties portent sur l'outil v8. La transition vers six skills est couverte par `updater-v8`.

Les cas v8 couvrent : trois skills vers six, dépendance absente, identique, personnalisée, partielle ou de même nom inconnue, collision de casse, jonction, interruption et reprise d'une installation, fichier tiers pendant la panne, retour arrière complet ou partiel limité aux ajouts possédés, refus après édition tierce, manifestes forgés, retour à rc-core refusé, plan v7 interrompu repris puis annulé par l'outil v8, paquet déplacé et ressource manquante.

Les régressions de contre-revue couvrent aussi l'application d'un plan v1 valide non commencé (puis vérification et retour arrière), le refus d'un plan périmé ou altéré, et la collecte des `expectedFailure`. Un échec attendu reste identifié et rend l'étape non qualifiée ; il n'est pas effacé par un code de sortie zéro. Les témoins de collecte saine et de succès inattendu sont conservés.

Les scripts vendored des optimiseurs sont compilés, leurs imports sont vérifiés comme bibliothèque standard, et chacun est exécuté avec `--help` et une entrée synthétique, hors ligne. Cela n'établit ni la justesse de leurs diagnostics ni la qualité d'un prompt.

### Scénarios de conduite

`tests/qualification/scenarios-v8.json` fixe onze scénarios et leurs oracles avant toute réponse : changement ordinaire autorisé, faux positif, doublon, défaut bloquant malgré une note, delta sensible non couvert, refus de runtime, interruption de push, routage des filtres, récupération irréversible, stagnation, incident confirmé.

Empreinte du fichier figé : `a050ce188ca4819d62080c334024ccaafd379c1ec1f035a2794436adfcbc26ba`.

**Aucun de ces essais d'agent n'a été exécuté.** Le test associé vérifie seulement leur structure et cette empreinte. Un gain d'autonomie, de temps ou de faux positifs ne pourra être affirmé qu'après une campagne comparative v7/v8 sur les mêmes scénarios, avec effectifs bruts.

### Limites v8

- Aucune installation dans un profil actif ; découverte des six skills en conversation neuve non constatée.
- Validation structurelle par lecteurs limités aux sous-ensembles présents, pas par un parseur YAML.
- Les faits fournisseurs des optimiseurs sont ceux de leur copie, non revérifiés.
- Un arrêt brutal entre la création d'un dossier de dépendance et sa consignation laisse, après retour arrière, ce dossier vide en place.
- Les limites v7 ci-dessous restent valables ; `rc_state.py` et `check_wave.py` sont inchangés.

## Version v7 acceptée (4 novembre 2026)

Le paquet v7 a reçu un avis indépendant favorable, puis une acceptation de la racine dans la portée locale implémentée, le 4 novembre 2026. Ses octets sont conservés sous `tests/fixtures/v7/`.

La revue R4 a rejoué 142 tests d'état, 30 tests de mise à jour et 71 contrôles structurels sans échec, erreur ni test ignoré. Quinze scénarios indépendants supplémentaires ont éprouvé les fenêtres d'interruption et l'attribution des événements anciens.

Les derniers défauts concernaient la fermeture partielle d'une opération dans deux journaux et le report d'un événement legacy vers la mauvaise vague. La v7 inscrit les nouvelles opérations de rattachement dans une seule copie locale et retrouve les journaux participants pour réparer les états v6 existants. Le report exige une identité de vague explicite ou rapprochée avec preuve.

### Identité des sources acceptées

- Manifeste candidat v7 : `b8e6152d474e3acaa71ffb3e65357fcb50545d9a39e0ebbdd52a0e79613334cf`.
- Manifeste de remise local : `8f0883af85d786206370fd049728ef2caacd04bd077e6115f4321067e51f8386`.
- Rapport indépendant R4 : `44cde1833cc3eaebb1c5a8bd08f8a6bbedc9018b8d5ac8b6ee1481f2eddcf9ad`.

`provenance.json` identifie les fichiers exportés. Une seule source de test v7 est adaptée : les deux chemins de fixtures historiques dans `test_rc_state_ar3.py`. Les preuves complètes et les anciennes revues restent dans les archives locales du développement. Les empreintes ci-dessus permettent le rapprochement ; le dépôt ne prétend pas contenir ces archives.

### Limites v7

- Les pannes sont injectées ; les reprises CLI passent par de nouveaux processus Python. Les coupures réelles de processus ou d'alimentation et la durabilité physique ne sont pas qualifiées.
- La contention réelle, les courses sur les ancêtres et les journaux locaux supprimés ou déplacés restent hors des garanties éprouvées.
- La reprise automatique après quota, les signaux de réveil et l'idempotence des lancements T3 ne sont pas établis.
- La campagne T3 historique portait sur v2 ; elle n'est pas transférée à v7 ni à v8.
- La découverte en conversation neuve, le raccord au programme actif et l'usage réel borné restent à vérifier après installation.
- Une restauration du paquet sur profils factices ne qualifie aucun retour arrière de données, de migration ou de produit.
- Aucun gain général de coût, de temps ou d'interventions humaines n'est revendiqué.
