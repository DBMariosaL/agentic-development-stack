# Dépendances de filtre

Les skills RC routent leurs livrables vers des filtres (section « Filtres » du contrat d'état). Depuis la v8, ces skills sont livrés dans `package/` pour que le paquet fonctionne sans le profil personnel d'origine ; la v10 ajoute `claude-fable-prompt-optimizer` aux trois premiers.

| Skill | Fichiers | Usage dans la stack |
|---|---|---|
| `gpt-prompt-optimizer` | 15 | Prompt destiné à GPT ; remise d'un enfant à un parent GPT. |
| `claude-opus-prompt-optimizer` | 15 | Prompt destiné à Opus ; remise d'un enfant à un parent Opus. |
| `claude-fable-prompt-optimizer` | 14 | Prompt destiné à Fable ; remise d'un enfant à un parent Fable. |
| `unslop` | 4 | Livrable destiné à un humain ; invocation explicite seulement. |

## Origine

- Source de `gpt-prompt-optimizer`, `claude-opus-prompt-optimizer` et `unslop` : profil Codex de l'utilisateur (`%USERPROFILE%\.codex\skills`), instantané du 9 novembre 2026 à 09:29 UTC, copié octet pour octet. `provenance.json` donne pour chaque fichier la source, l'empreinte source et l'empreinte de la copie.
- `claude-fable-prompt-optimizer` : repris du profil Claude du propriétaire (`%USERPROFILE%\.claude\skills`, version du 3 septembre 2026 écrite pour Fable 5.1), puis mis à jour dans ce dépôt le 16 novembre 2026 pour Fable 5.2 et Mythos 5.2, d'après la documentation d'Anthropic lue ce jour-là. Ce n'est donc pas une copie octet pour octet : ce dépôt en est la source, et `provenance.json` garde l'empreinte de chaque fichier d'origine.
- Exclus : `gpt-prompt-optimizer/scripts/__pycache__/` (cache), archives `.zip` du profil, tout autre skill.
- Droits et origine déclarés : les optimiseurs GPT et Opus (12 novembre 2026) et l'optimiseur Fable (16 novembre 2026) ont été créés par le propriétaire du dépôt ; Unslop est une adaptation de pstack de Lauren Tan (Poteto), sous MIT. Voir [la notice tierce](../THIRD_PARTY_NOTICES.md). La révision initialement reprise d’Unslop n’est pas connue ; le rapprochement et la licence amont vérifiée sont consignés dans `provenance.json`. Les 34 fichiers des trois premières dépendances restent identiques à la v9.1.1.

## Ce qui est contrôlé

`tools/validate_package.py` vérifie sur ces copies, sans les réécrire : nom et description, sous-ensemble de `agents/openai.yaml` effectivement utilisé, icônes résolues depuis la racine du skill, politique d'invocation enregistrée (Unslop non implicite et sans `default_prompt`), liens Markdown et ancres, lus sur le texte brut, exemples de code compris : toute destination, y compris le premier mot de toute ligne qui commence par `[étiquette]:`, porte un schéma, vise l'identifiant d'un titre ATX simple, ou nomme un fichier du paquet à la casse exacte, avec une ancre seulement vers un fichier Markdown, sinon elle est refusée en nommant la règle ; tout chemin `references/`, `scripts/` ou `assets/` cité, lu en entier, nomme un fichier du skill depuis sa racine ; un nom de fichier à blanc, un commentaire HTML ou un bloc HTML hors bloc de code est refusé ; compilation et imports de bibliothèque standard des scripts. Avec `--provenance`, toute modification d'octet est détectée.

`tests/package/` exécute en plus `--help` et une entrée synthétique de chacun des huit scripts, hors ligne, sans écriture. Ces contrôles ne mesurent pas la qualité des optimiseurs ; un lint de prompt ne certifie pas un prompt.

## Renvois externes et limites

- Les optimiseurs portent des faits fournisseurs datés : par exemple, la cible maintenue de `gpt-prompt-optimizer` est celle de sa référence `current-model.md` à la date de la copie, distincte du modèle du pilote. Le contrat demande de nommer le modèle réellement visé ; la copie n'est pas corrigée sur place.
- Une consigne générale d'une dépendance ne prime ni le mandat ni les règles RC : un filtre ne remplace pas l'action demandée, ne change pas de modèle et ne supprime pas une revue exigée.

## Rafraîchir une dépendance

1. Copier la nouvelle version amont dans un instantané hors dépôt, avec empreintes.
2. Comparer à `package/<skill>/`, relire le diff et ses effets sur le routage RC.
3. Remplacer les fichiers, mettre à jour `provenance.json`, la politique attendue du validateur si l'amont l'a changée, puis régénérer `manifest.json` (`python -B tools/rc_update.py manifest --package package --out <nouveau-fichier>`).
4. Lancer `python -B tools/check.py` et faire contre-relire le delta avant publication. Dans un profil installé, la mise à jour passe par `rc_update.py` : une copie locale personnalisée reste en conflit.
