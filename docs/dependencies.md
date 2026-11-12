# Dépendances de filtre

Les skills RC routent leurs livrables vers trois filtres (section « Filtres » du contrat d'état). Depuis la v8, ces trois skills sont livrés dans `package/` pour que le paquet fonctionne sans le profil personnel d'origine.

| Skill | Fichiers | Usage dans la stack |
|---|---|---|
| `gpt-prompt-optimizer` | 15 | Prompt destiné à GPT ; remise d'un enfant à un parent GPT. |
| `claude-opus-prompt-optimizer` | 15 | Prompt destiné à Opus ; remise d'un enfant à un parent Opus. |
| `unslop` | 4 | Livrable destiné à un humain ; invocation explicite seulement. |

## Origine

- Source : profil Codex de l'utilisateur (`%USERPROFILE%\.codex\skills`), instantané du 9 novembre 2026 à 09:29 UTC, copié octet pour octet. `provenance.json` donne pour chaque fichier la source, l'empreinte source et l'empreinte de la copie.
- Exclus : `gpt-prompt-optimizer/scripts/__pycache__/` (cache), archives `.zip` du profil, tout autre skill.
- Droits et origine déclarée le 12 novembre 2026 : les deux optimiseurs ont été créés par le propriétaire du dépôt ; Unslop est une adaptation de pstack de Lauren Tan (Poteto), sous MIT. Voir [la notice tierce](../THIRD_PARTY_NOTICES.md). La révision initialement reprise d’Unslop n’est pas connue ; le rapprochement et la licence amont vérifiée sont consignés dans `provenance.json`. Les 34 fichiers de dépendances restent identiques à la v9.1.1.

## Ce qui est contrôlé

`tools/validate_package.py` vérifie sur ces copies, sans les réécrire : nom et description, sous-ensemble de `agents/openai.yaml` effectivement utilisé, icônes résolues depuis la racine du skill, politique d'invocation enregistrée (Unslop non implicite et sans `default_prompt`), liens Markdown et ancres, chemins `references/`, `scripts/` et `assets/` cités, compilation et imports de bibliothèque standard des scripts. Avec `--provenance`, toute modification d'octet est détectée.

`tests/package/` exécute en plus `--help` et une entrée synthétique de chacun des cinq scripts, hors ligne, sans écriture. Ces contrôles ne mesurent pas la qualité des optimiseurs ; un lint de prompt ne certifie pas un prompt.

## Renvois externes et limites

- L'optimiseur Opus renvoie vers `claude-fable-prompt-optimizer` pour une cible Fable ou Mythos. Ce skill n'est pas inclus : la stack n'emploie pas ces modèles. S'il devient nécessaire, il reste une dépendance externe à déclarer.
- Les optimiseurs portent des faits fournisseurs datés : par exemple, la cible maintenue de `gpt-prompt-optimizer` est celle de sa référence `current-model.md` à la date de la copie, distincte du modèle du pilote. Le contrat demande de nommer le modèle réellement visé ; la copie n'est pas corrigée sur place.
- Une consigne générale d'une dépendance ne prime ni le mandat ni les règles RC : un filtre ne remplace pas l'action demandée, ne change pas de modèle et ne supprime pas une revue exigée.

## Rafraîchir une dépendance

1. Copier la nouvelle version amont dans un instantané hors dépôt, avec empreintes.
2. Comparer à `package/<skill>/`, relire le diff et ses effets sur le routage RC.
3. Remplacer les fichiers, mettre à jour `provenance.json`, la politique attendue du validateur si l'amont l'a changée, puis régénérer `manifest.json` (`python -B tools/rc_update.py manifest --package package --out <nouveau-fichier>`).
4. Lancer `python -B tools/check.py` et faire contre-relire le delta avant publication. Dans un profil installé, la mise à jour passe par `rc_update.py` : une copie locale personnalisée reste en conflit.
