# RC — stack de pilotage agentique

Six skills pour préparer et piloter le développement d’un projet dans T3 Code, avec un pilote GPT et des champions Opus : trois skills RC et les trois skills de filtre qu'ils appellent.

| Skill | Rôle |
|---|---|
| `rc-coordinate-development` | Choisir les lots prêts, préparer les vagues, lancer le travail autorisé et poursuivre après les jalons. |
| `rc-prepare-socle-prompts` | Préparer et harmoniser les mandats des champions, leurs interfaces et leurs preuves attendues. |
| `rc-prepare-supervisor` | Préparer un mandat de supervision qui soutient les champions et conserve les limites de la mission. |
| `gpt-prompt-optimizer` | Dépendance : passe unique sur un prompt destiné à GPT, ou sur la remise d'un enfant à un parent GPT. |
| `claude-opus-prompt-optimizer` | Dépendance : passe unique sur un prompt destiné à Opus, ou sur la remise d'un enfant à un parent Opus. |
| `unslop` | Dépendance : passe finale sur un livrable destiné à un humain, invocation explicite seulement. |

Le même pilote coordonne et supervise par défaut. Le paquet fournit aussi `rc_state.py` pour l'état durable du programme, les événements et la reprise ; `tools/rc_update.py` met à jour les skills de façon contrôlée.

## Version

Ce dépôt contient la **v9.1.2**, généralisation de la v9.1.1 sans changement de moteur, de format ou de conduite. Les noms `rc-*` restent un préfixe historique pour préserver les installations. La référence v9.1.1 est figée par le tag du même nom dans l’archive privée, sa fixture incluse et `provenance.json`.

La **v9.1.1** est le correctif de la v9.1 issu de ses essais de contrôle : la règle « critère ambigu → question » ne se déclenche plus que si le choix change un effet protégé par le mandat (une forme écrite littéralement fait foi), les refus d'une vague v2 ne portent plus le préfixe `v1-fields:`, et `init --template` indique quand `prompt_artifact` devient obligatoire. La v9.1 est une correction de la v9 « jardin » tirée d'une campagne d'essais réels du 11 novembre 2026 : des pilotes et sous-agents `gpt-6.1-sol` ont conduit la v9 sur dix petits programmes. Quatre essais sur dix n'avaient produit aucun code, d'abord parce que la v9 interdisait d'écrire un état à la main sans offrir de commande pour le créer. La v9.1 ajoute `rc_state.py init` (création, squelette typé, remplacement d'un état initial invalide), des refus qui nomment champ et type, et corrige les règles trop coûteuses ou ambiguës relevées par les essais. Campagne, défauts et corrections : [campagne v9.1](docs/campagne-v9.1.md) ; statut, revues et essais rejoués : [qualification](docs/qualification.md). La v9 acceptée le 10 novembre 2026 reste la référence précédente : `provenance.json` (`v9_reference`) et `tests/fixtures/v9/` ; la v8 garde `v8_reference` et `tests/fixtures/v8/`.

La v9 fait de l'environnement du projet un livrable : `AGENTS.md` court et boucle de feedback rapide. Elle ajoute aux vagues des cycles de jardinage (simplifier, harmoniser, optimiser) déclenchés par des signaux et bornés par une règle d'arrêt. Elle fixe des règles de valeur et d'élagage des tests, sans cliquet ni affaiblissement d'invariant. Elle renforce la continuité autonome et allège la lecture du pilote : 5 322 mots avant d'agir en v8, environ 3 500 en v9, la mécanique du moteur passant dans `engine.md`, lu sur erreur ou reprise. Les choix et leurs sources sont dans [sources v9](docs/sources-v9.md). En v9.1, les formats programme/vague (`rc-program/1`, vague v2), `check_wave.py` et les dépendances ne changent pas ; `rc_state.py` gagne `init` et des messages par champ, et tout état v9 valide le reste.

Une épreuve exploratoire v8/v9 a été menée sur 21 scénarios figés, avec une exécution par version et deux correcteurs aveugles ; ses effectifs bruts et ses limites sont dans la qualification. Aucun gain général de conduite, de temps ou d'autonomie n'est revendiqué.

## Vérifier le dépôt

Python 3.10 ou ultérieur, bibliothèque standard uniquement. La validation de référence est effectuée sous Windows ; les tests de jonctions NTFS sont propres à cet environnement.

```powershell
python -B tools/check.py
```

La commande vérifie les empreintes du paquet et de la provenance, lance les suites d'état, de mise à jour (historique v7, distribution à six skills, mises à jour réelles depuis la v8, la v9, la v9.1 et la v9.1.1) et de paquet, puis la validation structurelle. Elle écrit dans un nouveau dossier `.local/` un `summary.json` : identité du candidat, empreintes des entrées, commandes, collectes, skips et journaux. Une étape ne passe que si sa collecte correspond au nombre déclaré, sans échec ni skip non déclaré ; un code de sortie nul ne suffit pas. Elle utilise des fichiers synthétiques et des profils factices, sans réseau ; elle n'installe aucun skill dans les profils actifs.

## Installation et usage

Les six dossiers à installer sont dans `package/`. Lire [les instructions d'installation](docs/installation.md) avant de modifier un profil existant : une dépendance déjà présente et personnalisée n'est jamais écrasée.

Dans T3 Code, le pilote a besoin d'un mandat qui précise les résultats attendus, les autorisations, les ressources disponibles et les critères de fin. Les skills utilisent les outils réellement exposés par le runtime ; ils ne créent pas à eux seuls de service de réveil ni d'ordonnanceur. Les copies des optimiseurs portent des faits fournisseurs datés : nommer le modèle réellement visé. Un skill qu'elles citent hors du paquet (l'optimiseur Fable notamment) reste externe.

Le dossier `package/` utilise des descriptions génériques. Pour chaque projet, fournir son mandat, ses instructions, son backlog et ses autorisations ; aucun profil privé supplémentaire n’est nécessaire. La généralisation des descriptions ne qualifie pas un nouveau runtime ou un autre modèle.

## Organisation

```text
package/              Six skills : trois RC et trois dépendances de filtre
manifest.json         Manifeste v9.1.2 (format rc-update-manifest/2, distribution et rôles)
tools/                Vérification, validation structurelle et mise à jour
tests/state/          Tests de l'état et de la reprise (ceux de la v9 inchangés, plus la v9.1)
tests/updater/        Tests sur profils factices : historique v7, distribution v8, mises à jour depuis v8, v9, v9.1 et v9.1.1
tests/package/        Paquet déplacé, ressources, métadonnées, scripts vendored, scénarios
tests/qualification/  Scénarios figés de l'épreuve exploratoire ; résultats dans la qualification
tests/fixtures/       Versions historiques nécessaires aux tests (v7, v8, v9, v9.1, v9.1.1)
docs/                 Installation, dépendances, sources, campagne d'essais, qualification
provenance.json       Origine et empreintes des fichiers (format 2)
```

Les journaux T3, données métier, profils actifs, secrets, archives complètes de développement et textes complets des sources de recherche ne font pas partie de ce dépôt. Ce dépôt est distribué sous licence MIT : [LICENSE](LICENSE). Unslop est adapté de pstack de Lauren Tan (Poteto) ; sa notice MIT est conservée dans [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Les deux optimiseurs ont été créés par le propriétaire du dépôt, selon sa déclaration du 12 novembre 2026.

Les noms Radio Chantier et les résultats datés restent dans les archives de qualification et les fixtures historiques, conservées à l’octet près. Les anciens SHA de commits dans la provenance identifient la lignée privée : ils ne seront pas présents dans l’historique neuf du dépôt public. Les fixtures incluses et leurs empreintes permettent de refaire les contrôles sans accès à cet historique.
