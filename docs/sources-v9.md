# Sources et choix de la v9 « jardin »

La v9 s'appuie sur une source externe et sur le retour d'expérience des projets Alpha Radio Chantier et rc-alpha. Quatre analyses Opus indépendantes (vidéo, deux retours d'expérience, auto-audit de la v8), une contre-revue GPT-6.1-sol du plan, puis l'arbitrage de la racine, le 10 novembre 2026. Ce dépôt ne reproduit ni la source ni les journaux ; il garde les liens et les adaptations retenues.

- Vidéo : [Theo, les ingénieurs deviennent jardiniers](https://youtu.be/GtJKFhztgdM), analysée sur la transcription fournie par l'utilisateur, non visionnée. Le segment sponsorisé est écarté. Les chiffres (tests supprimés, PR par jour) sont auto-déclarés.
- Retour d'expérience : fils T3 des projets Alpha Radio Chantier et rc-alpha, dossier de preuves local et dépôt rc-alpha, lus en lecture seule.

## Constats qui motivent la v9

- Du 1er au 10 novembre, rc-alpha gagne environ 1 400 lignes produit pour environ 20 600 lignes de tests. Plusieurs correctifs de 13 à 31 lignes arrivent avec 1 200 à 1 760 lignes de témoin. `docs/developpement` pèse plus de la moitié des octets suivis.
- Environ trois fils sur quatre sont des revues ou des acceptations, avec des boucles jusqu'à R9. Deux défauts de parcours restent invisibles aux revues de delta jusqu'à la revue globale du 9 novembre, dont l'un est encore à confirmer sur appareil.
- L'autonomie se perd surtout sur des attentes sans mécanisme de réveil, des règles bloquantes que l'agent s'est données lui-même, des lancements dans le mauvais projet, des accords Git non préparés et des décisions humaines non groupées avant une absence.
- 253 scripts d'état à usage unique dans le dossier local, des tests nommés par vague, un minimum de tests « jamais abaissé » qui interdit l'élagage.
- Les cycles d'optimisation C01–C05 mobilisent quinze analystes pour un seul gain accepté, sans règle d'arrêt.
- La stack ne disait rien sur la simplicité du code, la valeur des tests, l'harmonisation entre champions ni l'environnement des agents dans le projet. Le pilote lisait 5 322 mots avant d'agir, dont environ 1 050 décrivaient en prose ce que `rc_state.py` applique déjà.

## Retenu, adapté

| Thème | Adaptation |
|---|---|
| Le jardin | Le projet porte un `AGENTS.md` court : boucle rapide de l'auteur, contrôle d'acceptation, conventions, chemins interdits. La latence de ces boucles est un signal de santé et borne le parallélisme. |
| Cycles de jardinage | Simplifier, harmoniser, optimiser : résultats ordinaires du DAG, déclenchés par des signaux (frictions remontées, fin de vague multi-champions, dérive des ratios ; réexamen au plus tard toutes les trois vagues produit). Un seul auteur au domaine exclusif ; livrable = diff accepté à comportement inchangé ; arrêt après deux cycles sans changement accepté. |
| Valeur des tests | Un test protège un comportement ou un défaut nommé. Retrait ou fusion seulement si l'obligation disparaît ou reste couverte par un test identifié, avec contre-épreuve. Aucun cliquet de minimum. Aucun affaiblissement d'invariant de sécurité, de droits, de données ou d'intégrité. Nommage par domaine. |
| Désherber à la source | Corriger aussi ce qui a induit un mauvais artefact (mandat, `AGENTS.md`, exemple, doc), en demandant à l'auteur ce qui l'y a conduit. |
| Seuils | Deux tours sur un même critère, témoin de plus de trois fois le diff plus cent lignes, solde de lignes, 60–90 s : signaux d'examen, jamais conditions d'acceptation. |
| Autonomie | Budget d'autonomie par lot, passages par conditions entre phases autorisées, DAG alimenté depuis le backlog couvert avant de conclure à une attente, aucune attente sans réveil réel ni action humaine précise, règles locales infondées révocables, décisions groupées avant une absence. |
| Boussole produit | Chaque vague produit nomme le scénario utilisateur qu'elle fait avancer ; revue globale fraîche périodique par une autre famille de modèles. |
| Allègement | Mécanique du moteur dans `engine.md`, lu sur erreur ou reprise. Une source par règle. Pas d'auto-mandat de supervision. Contre-revue documentaire réservée au nouveau domaine, à l'interface partagée ou au chemin sensible. Acceptation sans réviseur distinct pour une entrée unique à risque bas avec preuve complète. Remise proportionnée. |

## Écarté ou différé

- Cycles calendaires obligatoires, renommages rétrospectifs massifs, règle « une version par problème » : écartés.
- Volumes comme conditions d'acceptation : écartés.
- Suppression de tests d'état jugés redondants : écartée, les cas couvrent des situations distinctes.
- Modification de `rc_state.py`, `check_wave.py` et des formats : gelés.
- Réduction de `provenance.json` aux seules copies vendored (C4) : différée.
- Refonte générale des tests de mise à jour : écartée ; seule une référence v8 compacte est ajoutée.
