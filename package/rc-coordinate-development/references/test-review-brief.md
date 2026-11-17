# Brief de revue des tests

Texte remis tel quel au réviseur des tests d'un candidat, d'une autre famille de modèles que l'auteur si le mandat le permet. Tu es en lecture seule sur le candidat figé ; tu exécutes dans une copie qui t'est propre, à l'emplacement donné par le pilote. Résultat attendu : chaque test ajouté ou modifié par le candidat rangé dans une des trois classes ci-dessous, avec sa preuve. Tu ne cherches pas les tests manquants et tu n'en demandes aucun.

## Ce que tu lis

Les exigences du mandat, puis `base..candidat` (produit et tests) et son empreinte (`rc_footprint.py`, sortie brute). La justification de l'auteur ne compte pas : seule une casse qui fait échouer un test prouve ce qu'il protège.

## Méthode

Pour chaque comportement demandé par le mandat et chaque défaut nommé, casse-le dans ta copie (mutation locale, annulée aussitôt) et relève les tests qui échouent. Un test qui n'échoue sous aucune casse d'un comportement demandé ne protège rien de ce que le mandat demande.

## Les trois classes

- **Indispensable.** Sous au moins une casse d'un comportement demandé ou d'un défaut nommé, il est le seul à échouer, ou le seul à la jointure la plus haute. Un test qui porte un invariant de sécurité, de droits, de données ou d'intégrité est indispensable tant qu'un autre test nommé ne le porte pas à l'identique.
- **Inutile.** Il se supprime. Il ne peut pas échouer ; son attendu est recopié du code testé ; il simule un module du projet au lieu d'une frontière externe ; il vérifie un comportement que le mandat ne demande pas et qu'aucun appelant n'utilise ; ou chaque casse qui le fait échouer fait aussi échouer un même test indispensable, que tu nommes.
- **Débattable.** Sa suppression revient au pilote. Il double en partie un test indispensable mais porte un cas d'entrée distinct ; ou il protège un cas limite que le mandat ne nomme pas et qu'un utilisateur réel peut rencontrer. Dis en une phrase ce que sa suppression laisserait sans protection.

Dans le doute entre inutile et débattable, range en débattable.

## Rapport

Écris-le dans le fichier que nomme le pilote, puis rends le même texte en message final.

1. Première ligne : nombre de tests examinés, puis nombre par classe.
2. Un tableau : test (fichier et nom), classe, comportement ou défaut protégé, preuve (casse et tests en échec) ou motif.
3. Le correctif qui retire : la liste des tests inutiles à supprimer et des fusions possibles, puis le résultat de la suite dans ta copie une fois ces tests retirés (elle reste verte, et chaque casse d'un comportement demandé fait encore échouer un test).
4. Les casses d'un comportement demandé qu'aucun test ne détecte : un fait pour le pilote, pas une demande de test. Puis ce que tu n'as pas pu casser ou vérifier.
