# Installer ou mettre à jour les six skills

La création de ce dépôt n'installe rien dans les profils actifs. Une installation demande un mandat couvrant les profils visés et une frontière de vague stable : un acteur en cours peut encore lire les anciennes instructions.

## Première installation

Les six dossiers sous `package/` sont les dossiers de skills complets. Selon le profil utilisé, les racines habituelles sous Windows sont :

- Codex : `%USERPROFILE%\.codex\skills` ;
- Claude Code : `%USERPROFILE%\.claude\skills`.

Vérifier les chemins réellement utilisés par le client. Copier uniquement les six dossiers, après contrôle de leurs empreintes et de l'absence de dossiers existants de même nom. Les trois dépendances (`gpt-prompt-optimizer`, `claude-opus-prompt-optimizer`, `unslop`) sont souvent déjà présentes dans un profil personnel : si une version existe déjà, suivre la procédure de mise à jour ci-dessous, qui ne remplace jamais une copie personnalisée.

La prise en compte des skills par une nouvelle conversation doit ensuite être constatée dans le client concerné. Unslop reste en invocation explicite (`allow_implicit_invocation: false`).

## Mise à jour d'une installation existante

`tools/rc_update.py` fournit `manifest`, `preflight`, `apply`, `verify`, `resume` et `rollback`. Lancer `python -B tools/rc_update.py --help` pour les paramètres. L'outil n'installe aucune dépendance Python.

Exemple de préflight sous PowerShell, avec une racine de profil explicitement choisie :

```powershell
python -B tools/rc_update.py preflight --previous-manifest "chemin/ancien-manifeste.json" --new-package package --new-manifest manifest.json --target "chemin/profil/skills" --plan-out "chemin/etat-neuf/plan.json"
```

Le manifeste précédent doit être celui de la version réellement installée : `tests/fixtures/v7/manifest.json` pour la v7 acceptée, `tests/fixtures/v8/manifest.json` pour la v8 acceptée, `tests/fixtures/v9/manifest.json` pour la v9 acceptée, `tests/fixtures/v9.1/manifest.json` pour la v9.1 acceptée, `tests/fixtures/v9.1.1/manifest.json` pour la v9.1.1 acceptée, `tests/fixtures/previous/release-manifest.json` pour la version du 31 octobre 2026. Ces fichiers identifient des versions ; ils ne détectent pas l'installation courante.

### Distributions et transitions

L'outil connaît deux distributions, définies dans son code ; un manifeste ne peut ni en ajouter ni changer les rôles :

| Distribution | Skills | Manifeste |
|---|---|---|
| `rc-core` | trois skills RC | format absent ou `rc-update-manifest/1` (31 octobre, v7) |
| `rc-core-with-dependencies` | trois skills RC et trois dépendances | `rc-update-manifest/2` (depuis la v8) |

Transitions acceptées : `rc-core` vers `rc-core`, `rc-core` vers `rc-core-with-dependencies`, `rc-core-with-dependencies` vers elle-même. Un retour de v8 à v7 passe par `rollback` du plan appliqué ; l'outil ne retire jamais une dépendance par simple changement de distribution.

### Décisions par skill

- Skills RC : règles inchangées depuis la v7. Copie de la version précédente : mise à jour ; déjà à jour : rien ; fichier personnalisé : conflit ; fichiers manquants ou versions mélangées : profil refusé.
- Dépendances : absente ou dossier vide : installation (`install`) ; identique : aucune écriture (`already-new`) ; copie exacte de la version précédente du manifeste : mise à jour ; personnalisée, partielle ou dossier existant sans fichier géré : conflit, sans écriture.
- Fichiers inconnus dans un dossier de skill : conservés (`preserve-unknown`). Dossiers hors de la distribution : ni lus ni modifiés.

Un conflit bloque le plan. `apply --allow-blocked` met à jour les seuls skills non bloqués. Relire le plan, ses conflits, les fichiers inconnus et les actions prévues avant application. L'outil sauvegarde les octets remplacés dans le dossier d'état et refuse les états inattendus ou un plan périmé.

```powershell
python -B tools/rc_update.py apply --plan "chemin/etat-neuf/plan.json" --state-dir "chemin/etat-neuf"
python -B tools/rc_update.py verify --plan "chemin/etat-neuf/plan.json"
```

Une issue partielle se traite avec `resume` sur le même plan et le même dossier d'état. `rollback` restaure l'état précédent si les contrôles le permettent : il retire les fichiers créés par le plan et les dossiers qu'il a créés et consignés, s'ils sont vides. Un fichier déposé par un tiers dans une dépendance installée, ou une édition postérieure, fait refuser le retour arrière sans rien supprimer. Conserver plan, sauvegardes, journaux et rapports ; reconstater l'état après une erreur avant de relancer.

### Formats et compatibilité

- `rc-update-manifest/1` (ou sans champ `format`) reste lu tel quel : trois skills RC.
- `rc-update-manifest/2` ajoute `distribution`, la liste ordonnée `skills` avec leur rôle (`rc` ou `dependency`) et une empreinte `digest` calculée sur ces trois champs ; un écart avec le registre de l'outil ou une empreinte incohérente est refusé.
- Les plans sont écrits au format `rc-update-plan/2` (ajout de `roles` et `distributions`). Un plan `rc-update-plan/1` écrit par l'outil v7 reste lisible par `apply`, `resume`, `rollback` et `verify`.

Limite connue : si un arrêt brutal survient entre la création d'un dossier de dépendance et sa consignation au journal, le retour arrière laisse ce dossier vide en place. Un dossier vide est ensuite traité comme une dépendance absente.

## Raccord à un projet

L'installation des skills et la modification des instructions du projet sont deux opérations distinctes. À une frontière stable, rapprocher l'état réel du programme et désigner son titulaire avant toute reprise. Le mode habituel conserve le même pilote pour coordonner et superviser ; l'annexe `separate-relay.md` traite le cas où une mission impose un autre superviseur.

Préserver les règles du projet et les autorisations déjà accordées. La présence des skills ne constitue pas une autorisation de développement, de publication, de dépense ou d'accès à des données réelles.
