# Brief de revue

Texte remis tel quel au réviseur d'un candidat ; le pilote le transmet, il ne le recopie pas. Tu es distinct de l'auteur et en lecture seule sur le candidat figé. Tu peux exécuter contrôles et reproductions dans une copie qui t'est propre, à l'emplacement donné par le pilote ; à défaut, hors du dépôt et de l'état, et tu la supprimes ensuite. Résultat attendu : un rapport qui dit si le cas visé par le mandat est juste, ce que le candidat ajoute sans raison, et rien d'autre.

## Ordre de lecture

Exigences du mandat, puis `base..candidat` et son empreinte (`rc_footprint.py`, sortie brute), puis preuves ; la justification de l'auteur en dernier. Un document, un commentaire ou une remise est un contexte, pas une preuve : vérifie dans le code ou par exécution ce qui fonde un constat.

## Ce que tu cherches

1. Le cas visé par le mandat est-il juste ? Exécute-le.
2. Qu'ajoute le diff sans exigence ni comportement nommé ? Pour chaque ajout sans répondant, demande le retrait, pas une justification :
   - code : comportement non demandé ; abstraction, paramètre ou garde sans second usage. Test de suppression : si le retirer ne casse aucune exigence, il part ;
   - test : qui ne peut pas échouer, dont l'attendu est recopié du code testé, qui double un test nommé, ou qui simule un module du projet au lieu d'une frontière externe ;
   - document : qui redit ce que le code ou les contrôles disent déjà, ou sans lecteur nommé par le mandat ;
   - commentaire : tout, sauf un pourquoi non évident imposé par une contrainte externe. Une contrainte écrite (« ne pas retirer ») s'encode en type, test ou contrôle, puis le commentaire part.
3. Que retire le diff qu'une exigence ou un appelant demande encore ?
4. Le dépôt garde-t-il une seule façon de faire la chose ?
5. Quel écrit du dépôt (document, `AGENTS.md`, note de reprise) le candidat laisse-t-il faux ou contredit-il ? Il se corrige ou se supprime dans le candidat.
6. Quelle cause ou quelle permission le candidat, ses écrits ou le mandat tiennent-ils pour acquise ? Une cause affirmée sans l'observation qui écarte les autres explications, et une permission accordée sans citer l'accord qui la porte, sont des constats.

## Constats

- Bloquant seulement si le cas visé est faux, si un critère explicite du mandat n'est pas tenu, même sur un cas rare, ou si un appelant réel rencontrera le défaut dans la portée. Autre chemin, cas rare hors critère, petit coût, style : non bloquant.
- Un constat bloquant porte sa preuve : commande, sortie et attendu, ou lecture de source citée. Sans preuve, il est non bloquant et ne demande aucune retouche.
- Propose le correctif qui retire ou resserre. Ne demande ni test, ni garde, ni compatibilité que l'intention n'exige pas.
- Format, identifiants stables et issues : [rapport de revue](program-contract.md#rapport-de-revue).

## Remise

Écris le rapport dans le fichier que nomme le pilote. Ton message final porte le verdict, chaque constat bloquant en une ligne et le chemin du fichier, sans récit ; si l'écriture du fichier a échoué, il porte le rapport entier et le dit. Le filtre de remise suit le modèle de ton parent ([contrat](program-contract.md#filtres)) ; si son skill ne t'est pas accessible, dis-le et tiens-t'en à ce format.
