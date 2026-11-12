# Jardinage

À lire pour admettre ou conduire un cycle de jardinage, accepter un candidat qui retire, fusionne ou renomme des tests, ou corriger un artefact mauvais. Chaque seuil ci-dessous est un signal d'examen réglable au mandat, jamais une condition d'acceptation. Acceptation et preuve suivent la [boucle](operating-loop.md#3-livrer-juste).

## Cycles

Un cycle est un résultat ordinaire de `program.json` : `outcome` nomme sa nature et la friction qu'il retire ; `resources` réserve son domaine exclusif. Trois natures :

- **simplifier** : code mort, chemin legacy, doublons, fichier géant découpé, nom de vague remplacé par un nom de domaine ;
- **harmoniser** : patterns concurrents entre champions (erreurs, nommage, logs, configuration, helpers dupliqués), exemples et docs obsolètes ou trompeurs retirés, car un agent copie ce qu'il voit ;
- **optimiser** : seulement sur une métrique annoncée, mesurée avant et après sur la même base.

Un seul auteur, champion au domaine exclusif pendant la passe, conduit le cycle ; pas d'essaim d'analystes. Livrable : un diff accepté, comportement inchangé, contrôle d'acceptation vert ; une mesure seule n'est pas un résultat. Suis séparément les lignes nettes du produit et des tests, sans compenser l'une par l'autre ; un solde négatif ou nul est attendu pour simplifier ou harmoniser, mais reste descriptif : juge les chemins supprimés, la duplication retirée, le coût de maintenance. Renomme par domaine les fichiers neufs et ceux que la passe touche ; un renommage massif exige un besoin de navigation établi.

Deux cycles consécutifs sans changement accepté rendent leur budget au produit ; le suivant attend un signal nouveau. Un cycle n'avance pas de scénario utilisateur : il nomme la friction retirée, et son jalon la cite.

## Valeur des tests

Un test protège un comportement ou un défaut nommé.

- Retire ou fusionne un test seulement si l'obligation qu'il protège disparaît explicitement, ou reste couverte par un test identifié ; prouve-le par une contre-épreuve ciblée, par exemple une mutation ou une casse locale qui fait échouer le test restant.
- Liste les identités disparues avec leur justification dans le commit et la remise ; une collecte non vide ne suffit pas. Aucun minimum de tests en cliquet : un cliquet existant devient un contrôle qui échoue sur une collecte vide ou sur une identité disparue sans justification listée ; l'historique vit dans Git, pas dans les commentaires du contrôle.
- N'affaiblis jamais une assertion d'invariant de sécurité, de droits, de données ou d'intégrité du dispositif, et ne cache aucun skip.
- Un défaut reproduit reçoit un test de régression court dans le harnais commun, livré avec son correctif et sa doc ; un défaut peut justifier plusieurs cas discriminants.
- Un témoin de plus de trois fois le diff produit plus cent lignes signale une disproportion : étends le harnais commun plutôt qu'un harnais privé, ou motive l'exception (invariant sensible déclaré).
- Nomme fichiers, modules et tests par domaine et comportement, jamais par vague, lot ou constat ; un identifiant de constat va dans le commit ou un commentaire court.
- Inventaires de tests, patchs et bilans restent hors dépôt ou regénérables ([contrat](program-contract.md#fichiers-et-propriétaires)).

## Désherber à la source

Un artefact mauvais (test inutile, pattern concurrent, doc fausse, état parallèle) se corrige, et ce qui l'a induit aussi : mandat, `AGENTS.md`, exemple, doc ou outil. Demande à son auteur : « qu'est-ce qui t'a conduit à ajouter ceci ? ». Corrige d'abord la structure ou le code, puis ajoute un contrôle automatique rapide et ciblé dont la sortie tombe là où l'agent lit, et seulement ensuite une instruction courte.

Un incident confirmé (défaut échappé, faux positif récurrent, revue nuisible) devient un cas discriminant : cas défectueux qui échoue sur l'ancien candidat, cas corrigé, cas propre pour le bruit, ou preuve de remplacement explicite si le cas n'est pas automatisable ; nomme la cause ou l'inconnu et la couche qui aurait dû l'arrêter. Ce protocole ne prouve aucun gain de conduite et n'ouvre aucune campagne récurrente.

Les frictions des remises nourrissent ce désherbage : corrige tout de suite ce qui est petit, couvert et vérifié ; inscris le reste comme signal de cycle.
