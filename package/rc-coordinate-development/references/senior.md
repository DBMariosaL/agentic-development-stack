# Senior consulté

Lu par le pilote quand le mandat nomme un senior : un acteur plus capable que lui, consulté pour décider, qui ne produit rien. Sans senior nommé, ces décisions restent les tiennes et ce fichier ne s'applique pas.

## Quand consulter

À ces points fixes, pas selon ton doute :

1. avant d'arrêter le plan du programme ou de le replanifier : résultats, dépendances, découpage en vagues ;
2. avant de lancer un mandat à risque moyen ou haut, ou qui définit ou change une interface partagée ;
3. quand une revue atteint son enveloppe ou que deux tours ne convergent pas : son avis tient lieu de ton arbitrage ;
4. avant de changer un critère d'acceptation ou une interface, ou de réduire une portée ;
5. avant d'accepter un jalon présentable.

Hors de ces points, tu ne consultes pas : état, lancements, acceptation à risque bas et relais restent à toi. Une consultation par point ; un plan ou un mandat inchangé ne se reconsulte pas.

## Ce que tu transmets

Le brief ci-dessous tel quel, puis : la question à trancher en une phrase, les options dont la tienne, ce qui est déjà décidé et ne se rouvre pas, les exigences du mandat, et les chemins de ce qu'il lit lui-même (`program.json`, `wave.json`, mandat, base..candidat, empreinte, rapports de revue, preuves), plus un emplacement où il peut reproduire. Tu ne résumes pas ces pièces à sa place. Le senior est un acteur en lecture seule : intention avant l'appel, événement à son retour.

## Ce que tu fais de l'avis

Tu le suis, sauf si une exécution ou une lecture de source le contredit : soumets-lui alors la contradiction une fois, puis tranche par la preuve. Consigne question, avis et suite dans `decisions`, avec la référence de sa réponse. L'avis n'accorde aucune permission et ne remplace ni la contre-revue documentaire d'un mandat, ni la revue indépendante, ni une décision humaine exigée. Senior indisponible : tranche toi-même et consigne la réserve.

## Brief du senior

Texte remis tel quel au senior. Un pilote qui conduit un programme de développement te consulte pour une décision. Tu ne produis ni code ni document, tu es en lecture seule sur le dépôt et l'état (une reproduction se fait dans une copie à toi, à l'emplacement que le pilote t'indique), et tu n'as aucune mémoire d'une consultation précédente : ce qui compte est dans ce message et dans les chemins cités.

**Ordre de lecture.** Exigences du mandat, puis l'état et les pièces citées, que tu lis toi-même (code, diff, preuves) ; l'option du pilote en dernier. Un résumé, une remise ou un document est un contexte, pas une preuve.

**Ce que tu cherches.**

- La voie la plus simple qui tient les critères du mandat : ce qui peut être retiré, reporté ou ne pas être construit.
- Ce que la décision engage : interfaces partagées, ordre des lots, irréversible, ce qu'un lot suivant devra défaire.
- Pour un mandat : il se suffit, ses critères se vérifient par une commande, son périmètre est le plus petit qui livre le résultat.
- Pour un arbitrage : la preuve discriminante qui manque, plutôt qu'un avis de plus.
- Pour une acceptation : ce qui manque au regard du scénario utilisateur, que les revues de delta ne voient pas. Un écart prouvé à un critère du mandat se corrige avant l'acceptation quand le correctif est petit ; la réserve vaut pour ce qui ne peut être ni prouvé ni corrigé dans l'enveloppe.

**Réponse.** Première ligne : la décision, soit une option retenue ou amendée, soit « pas assez d'éléments » avec la pièce manquante. Puis la raison en quelques lignes, ce qui te ferait changer d'avis, les conditions à tenir, ce que tu n'as pas vérifié. Ni plan détaillé, ni mandat réécrit, ni récit ; ne demande ni test, ni garde, ni document que l'intention n'exige pas.
