# Boucle de pilotage

Conduite commune du pilote et de tout superviseur séparé. Formats et règles communes : [contrat d'état](program-contract.md). Un mandat explicite prime ces défauts.

## 1. Choisir la suite

Recalcule le prêt (`rc_state.py ready`) et choisis selon l'objectif du mandat et le parcours utilisateur, pas l'ordre du backlog : chaque vague produit nomme le scénario utilisateur qu'elle fait avancer. `ready` vide n'est pas une fin tant que le backlog couvert garde des priorités non inscrites : inscris-les comme résultats. Une dépendance fermée bloque son consommateur, pas l'équipe.

Le parallélisme suit les ressources réelles : fichiers et auteurs actifs, appareils, instances, ports, budgets, capacité des modèles (le quota Opus se réserve) et coût des contrôles sur leur machine. Garde de la capacité pour revues et contrôles.

Inscris aussi comme résultats ordinaires :

- un cycle de jardinage quand un signal le justifie : friction remontée, fin de vague multi-champions, latence de boucle ou ratios tests/produit et preuve/diff qui dérivent. Toutes les trois vagues produit (réglable), réexamine ces signaux ; sans friction utile, aucun cycle n'est dû ([jardinage](garden.md#cycles)) ;
- avant un jalon présentable, et au moins toutes les trois vagues produit, le scénario fil rouge sur la version courante et une revue globale fraîche (autre famille de modèles si le mandat le permet, lecture seule, examinateurs par domaine, checklist terrain), car les revues de delta ne voient pas ce qui manque. Pour un programme d'une seule vague à risque bas, la revue du candidat en tient lieu si elle porte sur tout le livré.

Le méta-travail (méthode, stack, outillage d'état) répond à un problème observé, avec portée et critère de fin ; pendant un programme produit, il exige un mandat.

## 2. Lancer

Vérifie `launch_ready`, base et outils live : un champion ne part que d'une vague rattachée à l'index, `launch_ready` vrai et passée `launched` ; seules les revues documentaires partent avant. Un fil de premier niveau appartient au projet runtime du dépôt produit ; un `cd` ne rattache pas un fil. Si le mandat couvre la création du fil, crée-le dans ce projet ; sinon remets une action humaine unique : projet, fil, texte exact. Un sous-agent natif ou un enfant délégué de ta session n'est pas un nouveau fil. Fais couvrir par le mandat, avant la vague, les accords que l'exécution demandera : Git (`safe.directory` en option de commande ; clone local : `git -c safe.directory=<dépôt> -c safe.directory=<dépôt>/.git clone …`), push, ports, instances, appareils. Écris dans la vague l'intention avant chaque appel d'acteur (`rc_state.py intent add`) ; consigne seulement les références réellement retournées. **Relais à un pilote successeur** (index sans vague active) : avant l'appel, écris dans l'index `last_milestone` « relais en cours », avec la corrélation passée au lancement (`clientRequestId`) et le chemin du brief ; après le reçu, réécris-le avec la référence retournée. Le successeur reprend par `claim --takeover --evidence`. Un « relais en cours » sans référence se rapproche par la liste des fils et tâches avant tout nouveau lancement.

L'`AGENTS.md` du dépôt produit (contenu : `rc-prepare-socle-prompts`) donne la boucle rapide de l'auteur et le contrôle d'acceptation ; note leurs durées à chaque vague.

## 3. Livrer juste

Chaque brief se suffit : résultat, base, sources et chemins, domaine de code et de tests, fichiers partagés attribués, ressources, effets permis, interfaces consommées (SHA), délégation permise ou interdite et ses bornes, critères, preuve et point de remise, filiation et modèle du parent. Un contrat de code consommé par un autre worktree est commité (SHA, manifeste) avant ses consommateurs ; seul le chemin consommateur attend.

**Preuve d'auteur.** L'auteur itère avec la boucle rapide, puis livre un candidat figé (`candidate.seq`, SHA ou manifeste) avec le contrôle d'acceptation exécuté sur ce candidat exact : commande et répertoire, attendu et observé, collecte et skips, sorties brutes, limites. Code de sortie nul, collecte vide, skip pertinent ou autre candidat ne valent pas réussite. Un contrôle rouge connu se corrige avant l'acceptation, sinon sa portée reste non acceptée. Plusieurs auteurs dans une même copie livrent chacun leur boucle rapide sur leurs fichiers ; le contrôle d'acceptation s'exécute alors une fois, sur le candidat assemblé figé. Quand boucle rapide et contrôle d'acceptation collectent exactement les mêmes tests, une exécution sur le candidat suffit. Un runtime manquant n'arrête pas les revues de source ou documentaires ; seule la portée qui en dépend reste non qualifiée. Des tests retirés, fusionnés ou renommés sont listés et justifiés ([valeur des tests](garden.md#valeur-des-tests)) ; une baisse de collecte non justifiée est un échec.

**Remise.** Risque bas : candidat, preuve d'auteur, limites, récupération, lignes ajoutées et retirées (produit et tests séparés), friction rencontrée. Au-delà, ajoute portée, rapports bruts, dispositions, échecs, non-exécuté et récupération complète : moyen (revert, restauration, désactivation, correctif en avant), périmètre, propriétaire, éprouvée ou non. Un revert ne restaure ni données supprimées ni migration consommée : l'irréversible se déclare et limite la portée, sans opération destructrice réelle pour l'éprouver. `finished`, « revue lancée », `workState` autre que `result_available` ou `hasPendingChildRuns: true` ne sont pas une remise.

**Risque.** Il se fixe par les effets et chemins touchés, pas par la taille du diff ni l'auteur : droits, secrets, entrées non fiables, CI ou publication, installeur ou mise à jour, migrations, effets destructifs ou externes, données réelles.

**Acceptation.**

- Risque bas, entrée unique, preuve d'auteur complète : vérifie la preuve sur le candidat exact et accepte sans réviseur distinct ; inscris sur ce candidat une revue `done` dont `reference` est ta note de vérification.
- Risque moyen ou haut, ou entrées couplées : revue indépendante par un acteur distinct de l'auteur, d'une autre famille si le mandat le permet (GPT pour un auteur Claude), en lecture seule, mandatée par toi, sur le candidat figé, avec exigences, base..candidat, delta et preuves avant la justification de l'auteur. Un delta sensible y reçoit une passe sécurité ciblée ; refusée, elle reste non exécutée et sa portée non acceptée, sans contournement. Une pré-revue de champion ne la remplace pas.
- Entrées couplées, même sans fichier commun (interfaces, migrations, lockfiles, droits, cycle de vie, configuration) : plan d'assemblage contre-relu, intégrateur distinct, auteurs gelés sur les périmètres transférés, revue d'intégration des deltas transférés, sauf allègement permis par le mandat. La preuve porte sur l'assemblage exact. Lire un contrat déjà commité et inchangé n'est pas un couplage : des lots aux fichiers disjoints qui le consomment suivent la règle de leur risque, sans plan d'assemblage ni intégrateur. Des auteurs sérialisés sur un fichier partagé ne sont pas couplés : le second part du candidat accepté du premier.

Une approbation humaine exigée porte sur les octets présentés, pas sur un delta ultérieur : présente-la sur le candidat final revu. Ni risque ni avis d'agent n'accordent une permission ; un changement ordinaire autorisé continue sans question. Un majeur non traité ou un delta sensible non couvert interdit l'acceptation de sa portée ; une portée réduite s'accepte si le mandat le permet, chaque critère non qualifié nommé.

**Revues et convergence.** Fixe `envelope` selon le risque ; les tours suivants portent sur les constats ouverts et le code modifié, disposés dans leur rapport (contrat). Un désaccord se tranche par une preuve discriminante (test, reproduction, lecture de source), jamais par note, majorité ou borne ; preuve impossible dans l'enveloppe : réserve sur sa portée, ou décision humaine si l'acceptation d'un risque produit change. Deux tours sur un même delta ou critère sans convergence déclenchent ton arbitrage avant un troisième : autre approche, découpe, portée réduite permise, réserve ou abandon sourcé. Un tour suivant cite un delta ou une preuve nouvelle ; un doute restant vaut une répétition ciblée, puis une réserve. Recadre aussi quand les tours rouvrent une classe de défaut ou font grossir le diff sans lien avec eux.

## 4. Garanties de toute vague

- **Ressources disjointes** : copies, chemins sans liens ni jonctions, racines de contrôle, bases, instances, ports, caches, rapports ; appareil et signature exclusifs ; preuves, données et processus étrangers préservés.
- **Cible destructive** : chaque exécution destructive (`fresh`, reset, purge) vise une cible isolée, possédée et revérifiée à cet usage ; un `fresh` exige une instance neuve hors cache partagé ; un helper réutilisé s'inspecte selon sa version et ses effets. Le clone propre complet n'est exigé qu'à l'acceptation finale de vague ou d'assemblage.
- **Migrations** : préfixes et dépendances reconstatés, sans numéro inventé ; source et manifeste commités avant application par le runner du projet, seule voie, sans DDL déguisé en fixture ; immuables dès la première application ou le premier partage consommé ; base vide et montée peuplée contrôlées si concernées ; un banc incompatible se préserve et un banc neuf le remplace, sans reset masquant.
- **Promotion** : si le mandat l'autorise, exacte (fast-forward du candidat accepté) et vérifiée ; un mouvement concurrent de la cible impose réconciliation et requalification.
- **Qualification** : ni simulation, ni configuration, ni somme d'essais isolés ne qualifient appareil, fournisseur, stockage réel ou alpha entière.

## 5. Continuer

Après acceptation, mets à jour la vague puis l'index, recalcule le prêt et référence dans `last_milestone` un jalon bref : changement, preuve, risque restant, récupération, suite ; ta note de vérification peut en tenir lieu. Le superviseur séparé écrit seulement sa vague ([relais](separate-relay.md)). Enchaîne sans accusé les phases autorisées (assemblage, lanceur, contrôle, acceptation, promotion) dont les conditions tiennent ; sinon escalade. Sous mandat GitHub, le push suit l'acceptation ; distingue accepté, publié, CI inconnue et CI échouée, et rapporte PR et CI au head courant.

Refus d'écriture, plan rejeté ou découpage erroné : corrige et continue dans le mandat et le budget. Avant de rendre la main, exécute le prêt autorisé ou engage son acteur. Sinon, consigne qui attend quoi, le signal et la reprise, avec un réveil réel : attente d'outil, retour d'enfant, ou tâche planifiée exposée et autorisée qui reprend le travail. À défaut, nomme une action humaine précise (message, fil, chemin d'état). Aucun délégué créé pour te réveiller.

Pilote racine, tu peux finir un tour pendant qu'un délégué travaille si son retour te réveille ; un hôte qui suit tes enfants et te réveille à leur retour vaut réveil réel, même pilote délégué. Attendu par ton parent, ne termine pas avec un descendant nécessaire actif : attends-le, ou remets une remise partielle qui le nomme. Pas de polling d'un délégué actif, mais une lecture ciblée pour reprendre ou réconcilier ; un message à un autre fil crée un tour, réservé à une vraie coordination.

Une règle bloquante que tu t'imposes (plafond d'exécutions, outil écarté après un refus) s'inscrit dans `decisions`, locale et révocable, avec sa source, et se réexamine à chaque reprise. Sans fondement dans les instructions applicables (projet, outil, plateforme), le mandat ou une limite constatée, elle ne bloque pas le travail prêt.

## 6. Traverser les interruptions

| Situation | Conduite |
|---|---|
| Quota ou limite de débit | `waiting_quota` avec `waiting.resume` ; acteurs, IDs et réservations conservés ; indépendant poursuivi ; reprise par réveil réel, sinon action humaine unique. Ni reset ni sondage. |
| Erreur terminale (authentification, fournisseur) | Lot `failed` avec cause et condition de reprise ; le programme et les autres chemins continuent. |
| Résultat d'outil incertain (timeout, erreur sans reçu, push compris) | L'intention reste `pending`. Relis l'état réel (fil, tâche, fichier, distant), résous `confirmed` ou `absent`, puis seulement réessaie avec une nouvelle corrélation. Un timeout n'est pas un échec certain. |
| Signal reçu | `rc_state.py event` dès la réception (retour d'un sous-agent natif compris), avant toute disposition ou clôture ; enregistré après la clôture, il devient `late`. Suis `classification` et `effect` ; l'écriture qui le traite le marque appliqué (`--applies-event`, sinon `ack`). Doublon sans effet et sans nouvelle équipe ; ancien consigné sans clore le récent ; tardif consigné sans relance ; non appliqué d'une vague close : `dispose`, sans la rouvrir. |
| Reprise à froid, écriture interrompue, signal absent | Sans présumer la cause, `rc_state.py resume` au prochain tour réel ; traite ses `actions` : opération incertaine par `reconcile` avant toute écriture du fichier ([moteur](engine.md#écritures)), intentions `pending` et acteurs `unknown` rapprochés avant de relancer leur cible ; un `unknown` sans cible bloque les lancements de sa vague ; le travail prêt sans lien continue. |

Attente, quota, erreur et fin réelle sont distincts : seule la fin réelle clôt.

## 7. Préparer les décisions humaines

Réutilise les accords applicables. Pour un effet ou une portée non couverts, inscris dans `decisions_pending` une question avec option concrète, effets et seul chemin suspendu. Si elle ne touche qu'une partie d'un résultat, inscris d'abord la partie indépendante comme résultat distinct et lance-la ; seule la partie dépendante attend. Avant une absence annoncée, groupe les décisions nécessaires (accords, fournisseur, enveloppe, corpus, appareil) et poursuis les lots indépendants. Autorisation, dépense, fournisseur, donnée réelle ou effet externe non couverts restent fermés ; le silence ne vaut pas accord, et une question nécessaire n'est pas un échec.

## Fin du programme

Termine quand les critères de fin du mandat sont acceptés, ou sur arrêt explicite, pas quand une vague est livrée. Chaque remise distingue accepté, échoué, bloqué, en attente et non qualifié.
