# Hôte T3 Code

Lu par le pilote quand sa session tourne dans T3 Code. Ce fichier dit quel outil de l'hôte sert chaque geste de la boucle ; il n'ajoute aucune règle. Les noms sont ceux du serveur MCP `t3-code` au 16 novembre 2026 : un outil absent ou changé se constate à l'appel, sans substitution silencieuse.

## Acteurs

| Geste de la boucle | Outil | À savoir |
|---|---|---|
| Lancer un champion ou un réviseur | `delegate_task` | Un fil enfant que l'humain peut suivre. Il permet un autre fournisseur (`orchestrator_capabilities` donne fournisseurs, modèles et options, une fois par fil). Sa fin réveille le fil qui possède la session : tu peux finir ton tour au lieu d'attendre, sur une remise `partial` qui nomme la tâche si ton parent t'attend (boucle, section 5). Lancé toi-même comme sous-agent natif, tu n'as pas de fil : attends ton délégué par un seul `t3_thread_wait`. |
| Lancer un acteur de ton fournisseur sans fil à lui | sous-agent natif de ton fournisseur, au premier plan | Il ne voit que ton brief et rend seulement son message final : ni reçu avant sa fin, ni modèle exécuté. Consigne donc avant l'appel la référence convenue dans le brief ; son `agentId`, rendu à la fin, identifie ses événements. Sa remise n'existe que dans ton contexte tant qu'il ne l'a pas écrite dans le fichier que nomme son brief. Ses capacités (écriture, second niveau) sont celles que l'hôte expose ; quand le mandat impose l'outil natif, le mandat prime sur ce tableau. |
| Reprendre un auteur pour une correction | `t3_thread_send` vers son fil (sous-agent natif : l'outil de message de ton fournisseur) | L'auteur garde son contexte : une correction coûte moins qu'un acteur neuf. Vers un fil terminé, l'envoi ouvre une tâche nouvelle et rend son `taskId`. Une revue, second tour compris, est toujours un nouveau `delegate_task` avec son brief complet : l'hôte le demande. |
| Constater ce qu'un acteur a fait | `t3_thread_read` (`messages` ou `activity`), `task_status` après son retour | `recentRuns` donne le modèle réellement exécuté (`executedModel`), que le reçu de lancement ne donne pas encore. |
| Arrêter un acteur | `task_cancel` | Jamais une interruption du fil enfant. |
| Répondre à la question d'un enfant | `t3_pending_request` (`list`, `read`, `respond`) | Seulement dans ton mandat ; il ne peut pas accorder une permission. |

- Copie de travail : `isolation: "worktree"` (de `delegate_task`, et du sous-agent natif quand ton fournisseur l'expose) isole le dépôt du projet de ta session. Si le dépôt produit est ailleurs, prépare toi-même la copie et donne son chemin dans le brief.
- Un réviseur d'un autre fournisseur peut se voir refuser Git sur une copie qu'il n'a pas créée : [moteur](engine.md#git).
- `finished`, un `workState` autre que `result_available` ou `hasPendingChildRuns: true` ne sont pas une remise : seul le message final de l'acteur en est une.
- Pas de sondage d'un délégué actif : ni `task_status`, ni `t3_thread_wait` en boucle, ni minuterie, ni délégué créé pour te réveiller. Une notification arrivée après la clôture s'enregistre par `event` ; le moteur la classe et rien ne se rouvre.
- Un fil de premier niveau (`t3_thread_launch`, `create_threads`) n'est pas une délégation : seulement si le mandat couvre sa création (boucle, section 2). Il appartient au projet du dépôt produit ; un `cd` ne rattache pas un fil. Un sous-agent natif ou un enfant délégué de ta session n'est pas un nouveau fil.
- Ta référence d'acteur (`--actor`, `owner.ref`) est l'identifiant de ton fil, unique par session (sans fil propre, la référence convenue dans ton brief) : un nom d'acteur que l'hôte réutilise d'une session à l'autre (`/root`) rendrait deux pilotes indiscernables pour le moteur.

## Réveils et attentes

| Situation | Outil |
|---|---|
| Reprise après quota, ou reprise périodique d'un long programme que le mandat autorise | `schedule_task` (`once` ou `interval`, lié au fil courant) : c'est la tâche planifiée de la boucle, section 5. Rapporte la prochaine exécution. |
| Commande de fond dont tu attends la fin (tests, build) | `t3_background_wait` avec son identifiant, avant de finir le tour |
| PR sous mandat GitHub | `link_pull_request` dès que tu crées ou pousses, puis `watch_pull_request` : contrôles, revues et conflits te réveillent. Un réveil n'est pas une décision de fusion. |

## Humain près de la boucle

- Une décision humaine s'inscrit d'abord dans `decisions_pending` (boucle, section 7) ; l'outil de question de l'hôte la présente ensuite, groupée avec les autres, avec ce que l'humain doit lire pour répondre.
- Un secret (jeton, mot de passe, code) se demande par `request_secret`, jamais dans la conversation ni dans un brief.
- Un résultat visuel à montrer passe par `html_preview` puis `html_render`. Les outils de navigateur et d'appareil servent une vérification que le mandat demande.
