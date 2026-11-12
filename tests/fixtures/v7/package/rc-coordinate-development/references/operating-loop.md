# Boucle de pilotage

Conduite commune du pilote, qu'il coordonne ou supervise, et de tout superviseur séparé. Les formats sont dans [le contrat d'état](program-contract.md) ; les garanties propres à une vague produit (migrations, candidat exact, qualification) sont dans le mandat composé avec [le gabarit](../../rc-prepare-supervisor/references/supervisor-template.md). Un mandat explicite prime ces défauts.

## 1. Choisir la suite

Recalcule le travail prêt depuis `program.json` et les `wave.json` référencés (`rc_state.py ready`), puis choisis selon l'objectif du mandat, pas l'ordre du backlog. Distingue dépendance technique dure, décision absente, ressource exclusive et raccord nécessaire seulement à une consommation : une dépendance fermée bloque son consommateur, pas l'équipe.

Le parallélisme suit les ressources réelles : fichiers et auteurs actifs, appareils, instances, ports, budgets, slots et capacité des modèles demandés. La capacité d'un modèle partagé (quota Opus notamment) se réserve comme une ressource. Garde de la capacité pour les revues et les contrôles ; remplir tous les slots n'est pas un but. Un contrat de code consommé par un autre worktree doit être commité, avec SHA et manifeste, avant ses consommateurs ; une préparation documentaire n'autorise pas un commit produit.

## 2. Livrer juste

Chaque brief est autonome, car l'enfant ne reçoit que sa tâche : résultat, base, sources et chemins, domaine de code et de tests, fichiers partagés attribués, ressources, effets permis, interfaces consommées (SHA), délégation autorisée ou interdite et ses bornes, critères, preuve et point de remise, filiation et modèle du parent. Avant l'appel, écris l'intention et sa corrélation (`rc_state.py intent add`) ; après le reçu, consigne les références retournées.

Les revues d'acceptation sont mandatées par le pilote, en lecture seule, sur un candidat figé identifié (`candidate.seq`, SHA ou manifeste), avec exigences, base..candidat, delta et preuves avant la justification de l'auteur. Un champion peut faire des pré-revues ; elles ont leur filiation et ne remplacent pas la revue d'acceptation.

La revue est proportionnée au risque et au delta. Fixe l'enveloppe de la vague (`envelope`) selon le risque ; il n'y a pas de plafond universel. Les tours suivants portent sur les constats ouverts et le code modifié. Un désaccord se tranche par une preuve discriminante (test, reproduction, lecture de source) ; ni note, ni majorité, ni borne atteinte ne ferment un défaut. Si la preuve est impossible dans l'enveloppe, le constat devient une réserve qui bloque seulement sa portée, ou une décision humaine s'il change l'acceptation d'un risque produit. Après une correction sensible, couvre le delta explicitement ou déclare-le non couvert.

Le coût d'intégration suit le couplage technique et sémantique, même sans conflit de fichiers : interfaces, migrations, lockfiles, droits, cycle de vie, configuration, comportement consommé. Plusieurs entrées couplées : plan d'assemblage contre-relu, intégrateur distinct, revue d'intégration couvrant les deltas transférés. Une intégration incrémentale plus légère exige que le mandat la permette. Dans tous les cas, la preuve porte sur l'assemblage exact accepté ; une preuve de composant ne se transfère pas.

Une remise identifie candidat, portée, preuves, rapports bruts, dispositions, échecs et non-exécuté. Un retour `finished`, un texte « revue lancée », `workState` autre que `result_available` ou `hasPendingChildRuns: true` ne sont pas une remise finale : traite-les comme un état intermédiaire.

## 3. Continuer après le jalon

À l'acceptation : mets à jour la vague puis le résultat dans l'index, recalcule le prêt, écris le jalon visible dans ce fil et référence-le dans `last_milestone`. Le jalon informe ; il n'attend pas d'accusé.

Avant de rendre la main, s'il reste du travail autorisé prêt, exécute-le dans le même tour ou engage réellement son acteur. Sinon, écris l'attente précise : qui, quoi, signal attendu, prochaine action. Suis l'instruction d'attente retournée par l'outil (`next`). N'invente pas de délégué pour obtenir un réveil et ne bloque pas un tour artificiellement.

Ta position compte. Pilote racine : une fin de tour pendant qu'un délégué travaille est normale si l'outil l'indique. Acteur dont le parent attend la remise : ne termine pas avec un descendant nécessaire actif ; attends-le avec le mode d'attente de l'outil, ou remets explicitement une remise partielle qui nomme ce descendant et le signal attendu.

Pas de polling ni de watcher d'un délégué actif. Les lectures ciblées restent permises pour reprendre, réconcilier un effet incertain ou répondre à un contrôle demandé. Un message à un autre fil crée un tour : réserve-le à une vraie commande ou information de coordination.

## 4. Traverser les interruptions

| Situation | Conduite |
|---|---|
| Quota ou limite de débit | Attente persistée (`waiting_quota`, `waiting.resume`), acteurs, IDs et réservations conservés, indépendant couvert poursuivi. Reprise automatique seulement si un mécanisme réel est établi pour ce runtime ; sinon écris que la qualification manque et la relance concrète à faire (message, fil, chemin d'état). Aucun reset, substitution de modèle ou sondage. |
| Erreur terminale (authentification, fournisseur) | Lot `failed` avec cause et condition minimale de reprise ; autres chemins poursuivis ; pas de substitution. |
| Résultat d'outil incertain (timeout, erreur sans reçu) | L'intention reste `pending`. Relis l'état réel (fil, tâche, fichier, référence) avant tout réessai ; résous `confirmed` ou `absent` ; seulement alors une nouvelle tentative avec une nouvelle corrélation. Un timeout n'est pas un échec certain. |
| Signal reçu, dupliqué, ancien ou tardif | `rc_state.py event` à la réception, puis l'écriture qui le traite le marque appliqué. Reçu non appliqué : à traiter. Doublon : sans effet. Ancien : consigné sans clore la version récente. Tardif après clôture : consigné sans relance ; reçu avant clôture mais non appliqué : disposition sourcée (`dispose`), vague non rouverte. Un doublon ne recrée pas l'équipe. |
| Écriture d'état interrompue | `resume` signale une opération incertaine : `reconcile` avant toute autre écriture ou retraitement de l'événement concerné. |
| Signal absent | Ne présume pas sa cause. Au prochain tour réel, réconcilie (`rc_state.py resume`) avant de reprendre. |
| Reprise à froid | Un nouvel acteur reprend depuis `program.json`, les `wave.json` et le journal (`rc_state.py resume`) : titulaire, acteurs, intentions non résolues, opérations d'écriture incertaines, événements reçus non appliqués, candidat, attentes, prochaine action. Il ne relit pas tout l'historique. Une opération incertaine se résout par `reconcile` avant toute écriture du même fichier. Il réconcilie intentions `pending` et acteurs `unknown` avant de relancer leur cible ; un acteur `unknown` sans cible connue bloque les lancements de sa vague jusqu'à son rapprochement ; le travail prêt sans lien avec eux s'engage pendant ce rapprochement. |

Attente, quota, erreur et fin réelle sont distincts : seule la fin réelle clôt.

## 5. Préparer les décisions humaines

Avant de demander, réutilise les accords et décisions applicables. Une question nécessaire porte une option concrète, ses effets, ce qui reste suspendu (le seul chemin dépendant) et ce qui continue ; elle est inscrite dans `decisions_pending`. Poursuis l'indépendant. Une autorisation, une dépense, un fournisseur, une donnée réelle ou un effet externe non couverts restent fermés tant que la décision manque ; le silence ne vaut pas accord. Une question nécessaire n'est pas un échec : ne la supprime pas pour réduire les sollicitations.

## Fin du programme

Termine quand les critères de fin du mandat sont acceptés, ou sur arrêt explicite. Une vague livrée n'épuise pas le mandat s'il reste du travail autorisé prêt. Remets décision, candidats acceptés, preuves, échecs, non-exécuté, réserves et attentes restantes, en distinguant fait observé, preuve d'auteur, hypothèse et non qualifié.
