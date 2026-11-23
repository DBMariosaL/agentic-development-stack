# Jardinage

À lire pour admettre ou conduire un cycle de jardinage, accepter un candidat qui retire, fusionne ou renomme des tests, juger un document ou un commentaire ajouté, ou corriger un artefact mauvais. Chaque seuil ci-dessous est un signal d'examen réglable au mandat, jamais une condition d'acceptation. Acceptation et preuve suivent la [boucle](operating-loop.md#3-livrer-juste).

## Cycles

Un cycle est un résultat ordinaire de `program.json` : `outcome` nomme sa nature et la friction qu'il retire ; `resources` réserve son domaine exclusif. Trois natures :

- **simplifier** : code mort, chemin legacy, doublons, fichier géant découpé, nom de vague remplacé par un nom de domaine ;
- **harmoniser** : patterns concurrents entre champions (erreurs, nommage, logs, configuration, helpers dupliqués), exemples et docs obsolètes ou trompeurs retirés, car un agent copie ce qu'il voit ;
- **optimiser** : seulement sur une métrique annoncée, mesurée avant et après sur la même base.

Un seul auteur, champion au domaine exclusif pendant la passe, conduit le cycle ; pas d'essaim d'analystes. Livrable : un diff accepté, comportement observable inchangé, contrôle d'acceptation vert. Le comportement observable est celui qu'appellent le produit, ses interfaces publiques et ses contrats ; une fonction sans appelant hors de ses propres tests est du code mort, retirée avec ces tests ; une mesure seule n'est pas un résultat. Suis séparément les lignes nettes du produit et des tests, sans compenser l'une par l'autre ; un solde négatif ou nul est attendu pour simplifier ou harmoniser, mais reste descriptif : juge les chemins supprimés, la duplication retirée, le coût de maintenance. Renomme par domaine les fichiers neufs et ceux que la passe touche ; un renommage massif exige un besoin de navigation établi.

Deux cycles consécutifs sans changement accepté rendent leur budget au produit ; le suivant attend un signal nouveau. Un cycle n'avance pas de scénario utilisateur : il nomme la friction retirée, et son jalon la cite.

## Valeur des tests

Un test protège un comportement ou un défaut nommé.

- Retire ou fusionne un test seulement si l'obligation qu'il protège disparaît explicitement, ou reste couverte par un test identifié ; prouve-le par une contre-épreuve ciblée, par exemple une mutation ou une casse locale annulée aussitôt, qui fait échouer le test restant ; une contre-épreuve par obligation conservée, pas par test retiré.
- Liste les identités disparues avec leur justification dans le commit et la remise ; une collecte non vide ne suffit pas. Aucun minimum de tests en cliquet : un cliquet existant devient un contrôle qui échoue sur une collecte vide ou sur une identité disparue sans justification listée ; l'historique vit dans Git, pas dans les commentaires du contrôle.
- L'attendu d'un test vient d'une source indépendante du code testé ; un test qui ne peut pas échouer se retire. Simule les seules frontières externes, jamais un module du projet. Teste à la jointure la plus haute qui porte le comportement ; un module approfondi remplace les tests de ses anciens morceaux, avec la même contre-épreuve.
- N'affaiblis jamais une assertion d'invariant de sécurité, de droits, de données ou d'intégrité du dispositif, et ne cache aucun skip.
- Un défaut reproduit reçoit un test de régression court dans le harnais commun, livré avec son correctif et sa doc ; un défaut peut justifier plusieurs cas discriminants.
- Un témoin de plus de trois fois le diff produit plus cent lignes signale une disproportion (`tests_outweigh_product` dans l'empreinte) : fais classer les tests ajoutés selon le [brief de revue des tests](test-review-brief.md), par un réviseur d'une autre famille si le mandat le permet. Les inutiles se retirent ; tu tranches chaque débattable avec son motif ; le volume seul ne condamne aucun test. Un auteur qui coupe jusqu'à éteindre le signal dispense de cette revue. Étends le harnais commun plutôt qu'un harnais privé.
- Nomme fichiers, modules et tests par domaine et comportement, jamais par vague, lot ou constat ; un identifiant de constat va dans le commit.
- Inventaires de tests, patchs et bilans restent hors dépôt ou regénérables ([contrat](program-contract.md#fichiers-et-propriétaires)).

## Écrits

Code, contrôles et état observé font foi ; un écrit qui les redit est un cache qui périme, et un agent le suit comme une règle. Supprime le document qui recopie l'environnement ; rattache à un SHA celui qui décrit le code ; génère depuis le code ce qui peut l'être. Un commentaire survit seulement pour un pourquoi non évident imposé par une contrainte externe ; une contrainte écrite (« ne pas retirer ») s'encode en type, test ou contrôle, puis le commentaire part. Une longue justification d'un contournement désigne la cause à corriger, pas un texte à polir.

## Désherber à la source

Un artefact mauvais (test inutile, pattern concurrent, doc fausse, état parallèle) se corrige, et ce qui l'a induit aussi : mandat, `AGENTS.md`, exemple, doc ou outil. Demande à son auteur : « qu'est-ce qui t'a conduit à ajouter ceci ? ». Corrige d'abord la structure ou le code, y compris pour ce que tu écris toi-même en conduite : une friction qui revient se corrige dans le lanceur, le harnais ou la commande du projet, pas par une consigne répétée de mandat en mandat ; puis ajoute un contrôle automatique rapide et ciblé dont la sortie tombe là où l'agent lit et dit comment corriger, et seulement ensuite une instruction courte, réservée au jugement. Un contrôle ajouté s'accepte après l'avoir vu passer, échouer sur le défaut visé, puis repasser. Une règle de l'`AGENTS.md` sans commande qui l'applique est un signal de cycle ; celle qu'un contrôle porte déjà sort du texte. Une instruction modifiée (mandat type, `AGENTS.md`, skill) se revoit comme du code.

Un incident confirmé (défaut échappé, faux positif récurrent, revue nuisible) devient un cas discriminant : cas défectueux qui échoue sur l'ancien candidat, cas corrigé, cas propre pour le bruit, ou preuve de remplacement explicite si le cas n'est pas automatisable ; nomme la cause ou l'inconnu et la couche qui aurait dû l'arrêter. Ce protocole ne prouve aucun gain de conduite et n'ouvre aucune campagne récurrente.

Les frictions des remises nourrissent ce désherbage : corrige tout de suite ce qui est petit, couvert et vérifié ; inscris le reste comme signal de cycle.
