# Sources et choix de la v10 « pertinence »

Quatre lectures Opus 5.5 indépendantes le 16 novembre 2026 (tstack, pstack, skills de Matt Pocock, sources publiques), deux implémentations Opus 5.5 en copies isolées, puis l'arbitrage de la racine (Fable 5.2). Ce dépôt ne reproduit pas les sources ; il garde les liens et ce qui en a été tiré.

- [tstack](https://github.com/t3dotgg/tstack) de Theo, et deux vidéos lues sur transcription fournie par l'utilisateur, non visionnées : [conseil multi-modèles](https://youtu.be/TWoS5Nmyoc8), [Opus 5.5 et Fable 5.2](https://youtu.be/XtykeVoSmP8). Segments sponsorisés écartés ; les chiffres sont auto-déclarés.
- [pstack](https://github.com/cursor/plugins/tree/main/pstack) de Lauren Tan, et sa conférence sur la pyramide inversée (code et contrôles, puis vérification, puis un peu de prose), lue sur [transcription](https://youtu.be/O_zcc6Xl12g).
- [Skills de Matt Pocock](https://github.com/mattpocock/skills).
- Sources publiques ouvertes par le lecteur : [Bugbot](https://cursor.com/blog/building-bugbot) (Cursor), [harnais pour longues exécutions](https://www.anthropic.com/engineering/harness-design-long-running-apps) (Anthropic), [évaluation des AGENTS.md](https://arxiv.org/abs/2602.11988) (ETH Zurich), [AGENTS.md et skills](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) (Vercel).
- Documentation d'Anthropic sur Fable 5.2, lue le 16 novembre 2026 pour mettre à jour l'optimiseur Fable ; les pages sont listées dans [ses sources officielles](../package/claude-fable-prompt-optimizer/references/official-sources.md).

## Constats

- Les scripts de la v9 contrôlent l'état de coordination. Rien n'y mesure ce qui est livré : l'auteur déclarait lui-même ses lignes ajoutées, et le tri entre l'utile et le superflu restait en prose.
- La v9 arbitrait une revue qui ne converge pas après deux tours, sans plafond ni échelle de gravité. Theo rapporte des boucles de plus de cinquante tours et une PR passée de 1 000 à 20 000 lignes sous l'effet des retours.
- Le dépôt avait le défaut qu'il combat : quatre suites de mise à jour copiées d'une version à l'autre, à quelques noms près.
- L'étude d'ETH Zurich mesure que les fichiers de contexte n'améliorent pas en général le taux de succès et renchérissent l'inférence de plus de 20 %.

## Retenu, adapté

| Thème | Adaptation | Origine |
|---|---|---|
| Mesurer au lieu de déclarer | `rc_footprint.py` : lignes par classe, commentaires ajoutés, signaux d'examen, croissance entre tours (`--previous`). Les signaux ne refusent rien. | pstack (contrôles et CLI réutilisés), tstack (`git diff --shortstat` à chaque tour) |
| Pertinence | Chaque ajout répond à une exigence ou à un comportement nommé, sinon il sort du candidat. Examen par le pilote à risque bas, par le réviseur au-delà. | Matt Pocock (revue du non-demandé, test de suppression), tstack (`modernize`) |
| Brief de revue | Un fichier lu par le réviseur, pas par le pilote : ordre de lecture, ajouts sans répondant, constat bloquant prouvé par exécution ou lecture de source, correctif qui retire. | pstack (`interrogate`), tstack (`sol-loop`), Matt Pocock (standards lus par le réviseur) |
| Convergence | Gravité requalifiée par l'intention du mandat ; trois tours par défaut, cinq sur chemin sensible ; enveloppe atteinte égale réserve ; le connu se corrige avant la revue ; un diff qui grossit se coupe d'abord. | tstack (`sol-loop`, `babysit-pr`) |
| Écrits | Un écrit hérité est un contexte, pas une preuve. Le document qui redit l'environnement se supprime ; un commentaire ne survit que pour une contrainte externe ; une contrainte écrite s'encode puis le commentaire part. | pstack (`no-comments`, `comment-sicko`, `correct`), tstack (`takeover`), Matt Pocock (`writing-for-agents`) |
| Règle et contrôle | Un contrôle ajouté est vu passer, échouer, repasser. Une règle d'`AGENTS.md` sans commande est un signal de cycle ; `AGENTS.md` ne porte que l'atypique. | pstack (`correct`), Matt Pocock (`setup-ts-deep-modules`, `retro`), ETH Zurich |
| Tests | Attendu indépendant du code testé, simulation aux seules frontières externes, jointure la plus haute. | Matt Pocock (`tdd`) |
| Senior consulté | Rôle optionnel nommé par le mandat : un modèle plus capable que le pilote, consulté à cinq points fixes (plan, mandat à risque, revue sans convergence, changement de critère ou d'interface, jalon), en lecture seule, qui décide sans produire. Il lit les pièces lui-même au lieu du résumé du pilote. | Anthropic (schéma « advisor », mesures de coût des orchestrateurs), demande du propriétaire |
| Voie plus simple | Le champion prend la voie plus simple qui tient les critères et la signale ; il remonte seulement si un critère ou une interface change. | Theo (Opus exécute ce qu'on lui demande sans le contester) |
| Appliqué au dépôt | Quatre suites de mise à jour fondues en un module paramétré (613 lignes retirées, 67 ajoutées, mêmes cas par version) ; fixture v9.1.2 réduite aux octets que le paquet ne porte plus ; budget de lecture du pilote contrôlé par `tools/check.py`. | règles de jardinage de la stack |

## Écarté ou différé

- Notes sur dix, seuil et unanimité du conseil de tstack : écartés. La note ne tranche rien, et l'unanimité n'a pas de plafond. La preuve discriminante reste la règle.
- Permissions accordées par une phrase déclencheuse, escalade humaine dès qu'une boucle bloque : écartées.
- Les vingt-trois playbooks de pstack, ses dix voies de vérification par PR, les spécifications longues et le wiki de Matt Pocock : écartés, ce sont les productions à réduire.
- Vérification runtime par carte de fonctionnalités, captures et transcripts ; tests de mutation sur le diff ; scénarios d'acceptation cachés aux auteurs : différés. Chacun demande un outil par projet et un essai réel.
- Rôles par modèle : la conduite reste écrite par rôle, et le mandat du programme nomme les modèles. Deux configurations à comparer par un essai : pilote Fable qui décide et encadre, ou pilote Opus avec un senior Fable consulté ; champions Opus et réviseurs GPT-6.1 Sol dans les deux cas. Sur un benchmark de recherche de défauts, Anthropic mesure Fable 5.2 orchestrateur 19 % plus cher qu'Opus 5.5 pour un score voisin ([optimiser coût et intelligence](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence), lu le 16 novembre 2026). Sur deux petits programmes, le pilote Fable livre le produit le plus juste et le pilote Opus avec senior le plus sobre ([qualification](qualification.md)) ; le portrait que Theo fait des modèles date de novembre 2026 et périmera.
- Coût d'administration du moteur (35 à 90 commandes d'état par essai en v9.1) : inchangé, toujours le premier défaut ouvert.
