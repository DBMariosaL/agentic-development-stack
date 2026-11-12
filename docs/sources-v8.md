# Sources et choix de la v8

Les changements de flux de revue de la v8 s'appuient sur deux sources externes, lues par deux analyses indépendantes (GPT et Opus) puis arbitrées par la racine le 9 novembre 2026. Ce dépôt ne reproduit pas ces sources ; il en garde les liens et les adaptations retenues.

- Article : [Solving code review at Anthropic](https://claude.dev/blog/solving-code-review-at-anthropic/). Pratiques rapportées par l'équipe Claude Code ; chiffres non vérifiés ici.
- Vidéo : [commentaire de l'article](https://www.youtube.com/watch?v=TFCDWrEBaFM), analysé sur transcription fournie par l'utilisateur, non visionné. Opinions et anecdotes distinguées des faits de l'article.

## Retenu, adapté

| Thème | Adaptation dans les skills RC |
|---|---|
| Vérification avant revue | Preuve d'auteur sur le candidat exact (commande, répertoire, attendu/observé, collecte, skips, limites) avant revue d'acceptation ou question humaine. Contrôle rouge connu : corriger ou laisser la portée non acceptée. Runtime manquant ou refusé : les revues de source avancent sans qualifier ce runtime. |
| Bruit des revues | Disposition par constat dans le rapport référencé (origine, effet bloquant, issue et preuve, doublon, report). Pas de registre ni de schéma nouveaux. |
| Convergence | Preuve discriminante, recadrage quand les tours stagnent ou que le diff gonfle. Pas de vote, de note ni de plafond universel ; une petite correction utile reste permise. |
| Risque et humains | Risque fixé par effets et chemins ; passe sécurité ciblée dans la revue GPT existante. L'approbation humaine vient du mandat, jamais d'une classe de risque ou d'un avis d'agent. |
| Retour arrière | Récupération nommée dans la remise : moyen, périmètre, propriétaire, éprouvée ou non ; un revert ne restaure pas une migration consommée. |
| Publication | Si le mandat couvre GitHub : références PR/head/cible, CI constatée, rapprochement après issue incertaine. Jalon bref, sans accusé ni format fixe. |
| Incidents | Cas défectueux, corrigé et propre ; correction de structure, puis contrôle, puis instruction courte. |
| Filtres | Six skills livrés ; routage par destinataire direct, une passe sans récursion, sans Unslop vers un parent. |

## Écarté ou différé

Vote ou note comme acceptation, trois tours universels, conseil de modèles permanent, service de revue payant, nouveau MCP ou superviseur, file de fusion, campagnes nocturnes, paliers universels de 0/1/2 humains : non retenus. Contrôle de l'enveloppe par `rc_state.py` (P8) : différé, aucune défaillance démontrée ne motive de changer le moteur d'état v7 dans ce lot.

Les décisions détaillées, par proposition, sont dans le rapport de remise de l'implémentation (dossier de preuve local) ; elles ne constituent pas une mesure de gain.
