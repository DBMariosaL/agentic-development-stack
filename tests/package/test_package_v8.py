"""Tests du paquet v8 : copie déplacée, ressources locales, métadonnées des dépendances,
scripts vendored et scénarios de qualification figés.

Lancer depuis la racine du dépôt : python -B -m unittest tests/package/test_package_v8.py
RC_PACKAGE_FIXTURES : racine courte des copies temporaires (défaut : .local/p-tests).

Ces tests sont structurels ou d'exécution de scripts sur entrées synthétiques. Ils ne
mesurent ni la qualité d'un prompt, ni la conduite d'un agent : les scénarios de
qualification sont seulement vérifiés comme figés et non exécutés.
"""
import sys

sys.dont_write_bytecode = True

import codecs  # noqa: E402
import contextlib  # noqa: E402
import ctypes  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import marshal  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'package'
PROVENANCE = ROOT / 'provenance.json'
SCENARIOS = ROOT / 'tests' / 'qualification' / 'scenarios-v8.json'
FIXTURES = Path(os.environ.get('RC_PACKAGE_FIXTURES') or ROOT / '.local' / 'p-tests').resolve()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load('validate_package_under_test', ROOT / 'tools' / 'validate_package.py')
rc_update = _load('rc_update_registry_under_test', ROOT / 'tools' / 'rc_update.py')
DEPS = rc_update.DEPENDENCIES
SCRIPTS = ['gpt-prompt-optimizer/scripts/prompt_lint.py', 'gpt-prompt-optimizer/scripts/profile_eval_dataset.py',
           'claude-opus-prompt-optimizer/scripts/prompt_lint.py',
           'claude-opus-prompt-optimizer/scripts/profile_eval_dataset.py',
           'claude-opus-prompt-optimizer/scripts/opus_api_check.py',
           'claude-fable-prompt-optimizer/scripts/prompt_lint.py',
           'claude-fable-prompt-optimizer/scripts/profile_eval_dataset.py',
           'claude-fable-prompt-optimizer/scripts/fable_api_check.py']
MAINTAINED_HERE = {'claude-fable-prompt-optimizer'}
# Copies dont prompt_lint.py reconnaît aussi les rubriques d'un mandat français.
ADAPTED_HERE = {'package/gpt-prompt-optimizer/scripts/prompt_lint.py',
                'package/claude-opus-prompt-optimizer/scripts/prompt_lint.py'}


def failing(result):
    return {c['check']: c['detail'] for c in result['checks'] if not c['passed']}


class Base(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.dir = FIXTURES / self._testMethodName[5:]
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.dir.mkdir()
        self.addCleanup(shutil.rmtree, self.dir)

    def copy(self):
        dest = self.dir / 'package'
        shutil.copytree(PACKAGE, dest)
        return dest


class PackageTests(Base):
    def test_real_package_validates(self):
        result = validator.validate(PACKAGE, PROVENANCE)
        self.assertEqual(failing(result), {})
        self.assertEqual(result['distribution'], 'rc-core-with-dependencies-2')
        names = {c['check'] for c in result['checks']}
        for dep in DEPS:  # les contrôles propres aux dépendances ont bien tourné
            self.assertIn(f'{dep}:ui_invocation_policy', names)
            self.assertIn(f'{dep}:ui_icon_small', names)
        links = [c for c in result['checks'] if c['check'].startswith(
            'rc-coordinate-development\\references\\program-contract.md:link') or c['check'].startswith(
            'rc-coordinate-development/references/program-contract.md:link')]
        targets = {c['detail'] for c in links}
        for dep in DEPS:
            self.assertIn(f'../../{dep}/SKILL.md', targets)

    def test_v7_fixture_keeps_rc_rules(self):
        result = validator.validate(ROOT / 'tests' / 'fixtures' / 'v7' / 'package')
        self.assertEqual(failing(result), {})
        self.assertEqual(result['distribution'], 'rc-core')

    def test_moved_copy_validates_without_profile(self):
        copy = self.copy()
        result = validator.validate(copy)
        self.assertEqual(failing(result), {})
        for path in copy.rglob('*'):
            if path.is_file():
                text = path.read_bytes().decode('utf-8')
                for marker in ('.codex', 'Referent', 'USERPROFILE', 'C:\\Users'):
                    self.assertNotIn(marker, text, path)

    def test_missing_reference_is_targeted(self):
        copy = self.copy()
        (copy / 'gpt-prompt-optimizer' / 'references' / 'current-model.md').unlink()
        bad = failing(validator.validate(copy))
        self.assertTrue(bad)
        for name, detail in bad.items():
            self.assertIn('current-model.md', str(detail), name)
            self.assertTrue(name.startswith('gpt-prompt-optimizer'), name)

    def test_missing_script_resource_red(self):
        copy = self.copy()
        (copy / 'claude-opus-prompt-optimizer' / 'scripts' / 'opus_api_check.py').unlink()
        bad = failing(validator.validate(copy))
        self.assertTrue(bad)
        self.assertEqual({detail.split(' (')[0] for detail in bad.values()}, {'scripts/opus_api_check.py'})

    def test_missing_icon_red(self):
        copy = self.copy()
        (copy / 'unslop' / 'assets' / 'icon.svg').unlink()
        bad = failing(validator.validate(copy))
        self.assertEqual(set(bad), {'unslop:ui_icon_small', 'unslop:ui_icon_large'})

    def test_broken_anchor_red(self):
        copy = self.copy()
        path = copy / 'claude-opus-prompt-optimizer' / 'references' / 'behavior-fixes.md'
        path.write_bytes(path.read_bytes() + b'\nSee [missing](#no-such-section).\n')
        bad = failing(validator.validate(copy))
        self.assertEqual(list(bad.values()), ['#no-such-section (no simple ATX heading has this id)'])

    def validate_with_payload(self, payload, extra=None):
        """Payload ajouté à unslop/references/patterns.md ; extra : {chemin du paquet: octets ajoutés}."""
        copy = self.copy()
        for rel, data in {'unslop/references/patterns.md': payload.encode('utf-8'), **(extra or {})}.items():
            path = copy / rel
            path.write_bytes((path.read_bytes() if path.exists() else b'') + data)
        out = self.dir / 'structure.json'
        proc = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'validate_package.py'), str(copy),
                               '--output', str(out)], capture_output=True, text=True, encoding='utf-8', timeout=90)
        result = json.loads(out.read_text(encoding='utf-8'))
        shutil.rmtree(copy)
        return proc.returncode, failing(result)

    def test_reference_link_to_missing_file_red(self):
        code, bad = self.validate_with_payload('\n[missing][dead]\n\n[dead]: does-not-exist.md\n')
        self.assertEqual(code, 1)
        self.assertEqual(list(bad.values()), [f'does-not-exist.md ({validator.DEAD})'])

    def test_windows_machine_path_red(self):
        code, bad = self.validate_with_payload('\nmachine path: C:\\private\\example.txt\n')
        self.assertEqual(code, 1)
        self.assertEqual(list(bad), [os.path.join('unslop', 'references', 'patterns.md') + ':no_machine_snapshot'])

    def test_valid_link_forms_accepted(self):
        for payload in ('\n[t][lbl]\n\n[lbl]:\n  patterns.md\n',
                        '\n[x](patterns%2Emd)\n',
                        '\n[x](<patterns.md>) [y][l]\n\n[l]: <patterns.md>\n',
                        '\n## Zed\n\n## Zed\n\n## Zed 1\n\n  ## Indented Head\n\n'
                        '[a](#zed-1) [b](#zed-1-1) [c](#indented-head)\n',
                        '\n```markdown\n[example](https://example.com/example-only.md)\n```\n',
                        '\n[x](patterns.md#content) [y](../references/patterns.md#language)\n',
                        '\n## A [W]\n\n[x](#a-w)\n',
                        '\nsee references/patterns.md.\n',
                        '\nsee <a href="patterns.md">x</a> <img src="../assets/icon.svg">\n',
                        '\n<https://example.com>\n',
                        '\n```html\n<div>x</div>\n```\n'):
            with self.subTest(payload):
                self.assertEqual(self.validate_with_payload(payload), (0, {}))

    def test_broken_forms_refused(self):
        """Lien mort, ancre morte, ressource absente ou chemin machine : refusés sous toute forme,
        exemples de code compris ; une forme que la règle ne lit pas est refusée par la règle."""
        for payload, extra, expected in (
                ('\n[a [b] c](absent.md)\n', {}, 'absent.md'),
                ('\n```\n[example](example-only.md)\n```\n', {}, 'carries a scheme'),
                ('\n[t][lbl]\n\n[lbl]:\n  absent.md\n', {}, 'absent.md'),
                ('\n- item\n  - inner\n    - [lbl]: absent.md\n\n[t][lbl]\n', {}, 'absent.md'),
                ('\n> [lbl]: absent.md\n', {}, 'absent.md'),
                ('\n[lbl]: <absent file.md>\n', {}, 'unsupported destination'),
                ('\n[lbl]: absent.md (title)\n', {}, 'absent.md'),
                ('\n[l]: absent.md extra\n', {}, 'absent.md'),
                ('\n- [role]: [model], effort [level]\n', {}, 'unsupported destination'),
                ('\n[x](../assets/icon.svg#absent)\n', {}, 'no simple ATX heading'),
                ('\n[x](patterns.md#no-such-heading)\n', {}, 'no simple ATX heading'),
                ('\nsee <a href="absent.md">x</a>\n', {}, 'absent.md'),
                ('\nsee <img src="absent.svg">\n', {}, 'absent.svg'),
                ('\n[t](a(1).md)\n', {}, 'unsupported destination'),
                ('\n[x](PATTERNS.MD)\n', {}, 'PATTERNS.MD'),
                ('\n[x](patterns.md.)\n', {}, 'patterns.md.'),
                ('\n```\n# Hidden\n```\n\n[x](#hidden)\n', {}, 'no simple ATX heading'),
                ('\n    ```\n\n```\n# Hidden\n```\n\n[x](#hidden)\n', {}, 'no simple ATX heading'),
                ('\n```x``` inline\n\n```\n# Hidden\n```\n\n[x](#hidden)\n', {}, 'no simple ATX heading'),
                ('\n\t```\n\n```\n# Hidden\n```\n\n[x](#hidden)\n', {}, 'no simple ATX heading'),
                ('\n- ```\n  # Hidden\n  ```\n[x](#hidden)\n', {}, 'no simple ATX heading'),
                ('\n- ```\nx\n```\n# Hidden\n\n[x](#hidden)\n', {}, 'no simple ATX heading'),
                ('\n> ```\n# Hidden\n\n[x](#hidden)\n', {}, 'no simple ATX heading'),
                ('\nSetext Title\n===\n\n[x](#setext-title)\n', {}, 'no simple ATX heading'),
                ('\n## A [b]\n\n[b]: patterns.md\n\n[x](#a-b)\n', {}, 'no simple ATX heading'),
                ('\n## See [a](patterns.md)\n\n[x](#see-apatternsmd)\n', {}, 'no simple ATX heading'),
                ('\n## A [b][c]\n\n[c]: patterns.md\n\n[x](#a-bc)\n', {}, 'no simple ATX heading'),
                ('\n## A &amp; B\n\n[x](#a-amp-b)\n', {}, 'no simple ATX heading'),
                ('\n## A <b>B</b>\n\n[x](#a-bbb)\n', {}, 'no simple ATX heading'),
                ('\n## A\\*B\n\n[x](#ab)\n', {}, 'no simple ATX heading'),
                ('\n## _Foo_ bar\n\n[x](#_foo_-bar)\n', {}, 'no simple ATX heading'),
                ('\nsee `<!--` here\n', {}, 'HTML comment'),
                ('\n  <details>\n\n# Hidden\n', {}, 'HTML block'),
                ('\nsee scripts/absent.py.\n', {}, 'scripts/absent.py'),
                ('\nrun `python --file=scripts/absent.py`\n', {}, 'scripts/absent.py'),
                ('\nrun ./scripts/absent.py\n', {}, 'scripts/absent.py'),
                ('\nreferences/patterns.md+absent\n', {}, 'unsupported resource word'),
                ('\nRead `references/my file.md`\n', {'unslop/references/my file.md': b'x\n'}, 'blank'),
                ('\nsee c:\\users\\me\\secret.txt\n', {}, 'no_machine_snapshot'),
                ('\nsee \\\\srv\\share\\x\n', {}, 'no_machine_snapshot'),
                ('\nsee /home/me/secret.txt\n', {}, 'no_machine_snapshot'),
                ('\nsnap ' + 'A1B2C3D4E5' * 4 + '\n', {}, 'no_machine_snapshot'),
                ('', {'unslop/references/patterns.md': b'\xff'}, 'utf8'),
                ('', {'gpt-prompt-optimizer/scripts/prompt_lint.py': b'\x00'}, 'compiles')):
            with self.subTest(payload or extra):
                code, bad = self.validate_with_payload(payload, extra)
                self.assertEqual(code, 1)
                self.assertTrue(bad)
                for name, detail in bad.items():
                    self.assertIn(expected, f'{name} {detail}')

    def test_rules_refused(self):
        """Chaque règle promise par la docstring du validateur refuse sa violation (R3B-V01 à V03)."""
        fable = 'claude-fable-prompt-optimizer/references/behavior-fixes.md'
        rc, gpt = 'rc-coordinate-development', 'gpt-prompt-optimizer'
        for label, rel, old, new, expected in (
                ('fichier non régulier', None, None, None, ':regular'),
                ('cache', 'unslop/scripts/__pycache__/x.pyc', None, 'x', 'no_cache_or_temp'),
                ('compilation', f'{gpt}/scripts/prompt_lint.py', None, '\nreturn 1\n', ':compiles'),
                ('import hors bibliothèque standard', f'{gpt}/scripts/prompt_lint.py', None, '\nimport requests\n',
                 ':stdlib_imports'),
                ('dépendance maintenue ici réécrite', fable, None, ' ', 'provenance:' + fable),
                ('fichier hors provenance', 'unslop/references/extra.md', None, 'x\n', 'provenance:inventory'),
                ('fichier à la racine', 'README.md', None, 'x\n', 'no_file_at_package_root'),
                ('nom RC', f'{rc}/SKILL.md', f'name: {rc}', 'name: autre', f'{rc}:name'),
                ('description RC', f'{rc}/SKILL.md', 'description: ', 'description: <', f'{rc}:description'),
                ('clé de métadonnées RC', f'{rc}/SKILL.md', '---\n', '---\nextra: x\n', f'{rc}:metadata_keys'),
                ('clé de frontmatter', f'{rc}/SKILL.md', 'name:', 'Name:', f'{rc}:frontmatter_subset'),
                ('scalaire ambigu', f'{rc}/SKILL.md', 'description: ', 'description: a: b ', f'{rc}:frontmatter_subset'),
                ('gabarit inachevé', f'{rc}/SKILL.md', None, '\n[TODO: finir]\n', 'no_unfinished_scaffold'),
                ('import automatique', f'{rc}/SKILL.md', None, '\n@SKILL.md\n', 'no_automatic_reference_import'),
                ('clé UI répétée', f'{rc}/agents/openai.yaml', None, '  display_name: "X"\n', f'{rc}:ui_line'),
                ('invocation RC', f'{rc}/agents/openai.yaml', f'${rc}', rc, f'{rc}:ui_invocation'),
                ('découverte normale', f'{rc}/agents/openai.yaml', None, 'policy:\n  allow_implicit_invocation: false\n',
                 f'{rc}:ui_normal_discovery'),
                ('produits', f'{gpt}/agents/openai.yaml', '    - "chatgpt"', '    - true', f'{gpt}:ui_products'),
                ('description courte de dépendance', f'{gpt}/agents/openai.yaml',
                 'short_description: "Optimise les prompts GPT et les instructions d\'agents"', 'short_description: ""',
                 f'{gpt}:ui_short_description'),
                ('ligne UI hors sous-ensemble', f'{gpt}/agents/openai.yaml', None, '\nnotakey\n', f'{gpt}:ui_subset'),
                ('titre indenté de quatre espaces', 'unslop/references/patterns.md', None,
                 '\n    ## Four\n\n[x](#four)\n', ':link:'),
                ('extension .MD', 'unslop/references/README.MD', None, '[dead](absent.md)\n', ':link:'),
                ('Markdown avec BOM', 'unslop/references/bom.md', None, '\ufeff[dead]: absent.md\n', ':utf8')):
            with self.subTest(label):
                copy = self.copy()
                patch = mock.patch.object(type(copy), 'is_symlink', lambda path: path.name == 'patterns.md') \
                    if rel is None else contextlib.nullcontext()
                if rel is not None:
                    path = copy / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    text = path.read_text(encoding='utf-8') if path.exists() else ''
                    if old is not None:
                        self.assertIn(old, text)
                    path.write_bytes((text.replace(old, new, 1) if old is not None else text + new).encode('utf-8'))
                try:
                    with patch:
                        bad = failing(validator.validate(copy, PROVENANCE))
                finally:
                    shutil.rmtree(copy)
                self.assertTrue(any(expected in name for name in bad), bad)

    def test_unslop_policy_enforced(self):
        for label, old, new, check in (
                ('implicit', b'allow_implicit_invocation: false', b'allow_implicit_invocation: true',
                 'unslop:ui_invocation_policy'),
                ('prompt', b'  icon_large: assets/icon.svg\n',
                 b'  icon_large: assets/icon.svg\n  default_prompt: "Use $unslop"\n', 'unslop:ui_no_default_prompt')):
            with self.subTest(label):
                copy = self.copy()
                ui = copy / 'unslop' / 'agents' / 'openai.yaml'
                data = ui.read_bytes()
                self.assertEqual(data.count(old), 1)
                ui.write_bytes(data.replace(old, new))
                self.assertEqual(set(failing(validator.validate(copy))), {check})
                shutil.rmtree(copy)

    def test_unsupported_ui_construct_refused(self):
        copy = self.copy()
        ui = copy / 'gpt-prompt-optimizer' / 'agents' / 'openai.yaml'
        ui.write_bytes(ui.read_bytes() + b'extra: {a: b}\n')
        self.assertIn('gpt-prompt-optimizer:ui_subset', failing(validator.validate(copy)))

    def test_rc_rules_preserved(self):
        copy = self.copy()
        ui = copy / 'rc-coordinate-development' / 'agents' / 'openai.yaml'
        data = ui.read_bytes()
        old = b'"Choisir, lancer et poursuivre le travail pr\xc3\xaat"'
        self.assertEqual(data.count(old), 1)
        ui.write_bytes(data.replace(old, b'"' + b'x' * 70 + b'"'))
        self.assertEqual(set(failing(validator.validate(copy))), {'rc-coordinate-development:ui_short_description'})
        ui.write_bytes(data.replace(old, b'Choisir sans guillemets'))
        self.assertIn('rc-coordinate-development:ui_string:short_description', failing(validator.validate(copy)))
        ui.write_bytes(data.replace(old, b'12345'))
        self.assertEqual(set(failing(validator.validate(copy))), {'rc-coordinate-development:ui_short_description'})
        for policy in (b'allow_implicit_invocation:  false', b'"allow_implicit_invocation": false'):
            ui.write_bytes(data + b'policy:\n  ' + policy + b'\n')
            self.assertEqual([k.split(':')[1] for k in failing(validator.validate(copy))], ['ui_line'])

    def test_dependency_metadata_as_delivered(self):
        result = validator.validate(PACKAGE)
        checks = {c['check']: c for c in result['checks']}
        opus = checks['claude-opus-prompt-optimizer:ui_short_description']
        self.assertTrue(opus['passed'])
        self.assertGreater(int(opus['detail'].split()[0]), 64)  # accepté tel que livré
        self.assertTrue(checks['unslop:ui_invocation_policy']['passed'])
        self.assertEqual(checks['unslop:ui_invocation_policy']['detail'], 'allow_implicit_invocation=False')

    def test_unregistered_skill_red(self):
        copy = self.copy()
        (copy / 'autre-skill').mkdir()
        (copy / 'autre-skill' / 'SKILL.md').write_bytes(b'---\nname: autre-skill\ndescription: x\n---\n')
        self.assertIn('distribution_directories', failing(validator.validate(copy)))

    def test_rewritten_dependency_detected(self):
        copy = self.copy()
        path = copy / 'unslop' / 'references' / 'patterns.md'
        path.write_bytes(path.read_bytes() + b' ')
        provenance = json.loads(PROVENANCE.read_text(encoding='utf-8'))
        self.assertEqual(set(failing(validator.validate(copy, PROVENANCE))),
                         {'provenance:unslop/references/patterns.md'})
        self.assertTrue(any(f['path'] == 'package/unslop/references/patterns.md' for f in provenance['files']))


class DependencyRecordTests(Base):
    def test_dependency_provenance_complete(self):
        provenance = json.loads(PROVENANCE.read_text(encoding='utf-8'))
        records = [f for f in provenance['files'] if f['path'].split('/')[1:2] and f['path'].split('/')[1] in DEPS]
        counts = {d: sum(1 for f in records if f['path'].split('/')[1] == d) for d in DEPS}
        self.assertEqual(counts, {'gpt-prompt-optimizer': 15, 'claude-opus-prompt-optimizer': 15,
                                  'claude-fable-prompt-optimizer': 14, 'unslop': 4})
        for f in records:
            if f['path'].split('/')[1] not in MAINTAINED_HERE and f['path'] not in ADAPTED_HERE:
                self.assertEqual(f['adaptation'], 'byte-identical', f['path'])
                self.assertEqual(f['sha256'], f['source_sha256'], f['path'])
            data = (ROOT / f['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), f['sha256'], f['path'])
            self.assertEqual(len(data), f['bytes'], f['path'])

    def test_registry_consistency(self):
        self.assertEqual(set(validator.DEPENDENCY_POLICY), set(DEPS))
        self.assertEqual(tuple(validator.NAMES), rc_update.SKILLS)
        self.assertEqual(validator.DISTRIBUTIONS, rc_update.DISTRIBUTIONS)


class VendoredScriptTests(Base):
    def run_script(self, rel, *args):
        return subprocess.run([sys.executable, '-I', '-B', str(PACKAGE / rel), *args], cwd=self.dir,
                              capture_output=True, text=True, encoding='utf-8', timeout=120)

    def test_scripts_cli_help(self):
        for rel in SCRIPTS:
            with self.subTest(rel):
                proc = self.run_script(rel, '--help')
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn('usage', proc.stdout)

    def test_french_rubrics_recognized(self):
        """Chaque détecteur de rubrique manquante des trois prompt_lint.py lit la rubrique dans un
        mandat français : présente, aucun avertissement ; retirée, l'avertissement revient."""
        sections = {
            'task': '## Résultat attendu\n\nAjoute une commande de lecture au journal.\n',
            'scope': '## Domaine\n\nÀ toi : journal/cli.py. Hors domaine : tout autre fichier.\n',
            'permissions': '## Effets permis\n\nEffets permis : lancer les tests. Interdits : réseau.\n',
            'delegation': '## Délégation\n\nTu ne lances aucun sous-agent.\n',
            'stop': '## Remontées\n\nRemonte une décision que ce texte ne tranche pas, sans t\'arrêter sur le reste.\n',
            'done': '## Terminé quand\n\nLa suite est verte sur le dernier commit.\n',
        }
        context = ('# Mandat\n\nTu es l\'agent champion du lot, travail long-running, dans le shell. Tu peux modifier '
                   'les fichiers ; chaque étape finit par un commit. Le pilote répartit le travail entre les '
                   'subagents de la vague.\n\n' + ' '.join(f'mot{i}' for i in range(400)) + '\n\n')
        rows = (
            ('gpt', 'missing_task', 'task'), ('gpt', 'missing_done_criteria', 'done'),
            ('gpt', 'missing_permission_boundary', 'permissions'), ('gpt', 'missing_delegation_merge', 'delegation'),
            ('claude-opus', 'generic_missing_task', 'task'), ('claude-opus', 'opus_missing_scope_boundary', 'scope'),
            ('claude-opus', 'opus_missing_done_criterion', 'done'), ('claude-opus', 'opus_missing_stop_rule', 'stop'),
            ('claude-opus', 'generic_missing_permission_boundary', 'permissions'),
            ('claude-opus', 'opus_unbounded_delegation', 'delegation'),
            ('claude-fable', 'generic_missing_task', 'task'), ('claude-fable', 'generic_missing_done_criteria', 'done'),
            ('claude-fable', 'generic_missing_scope_boundary', 'scope'),
            ('claude-fable', 'fable_missing_autonomy_contract', 'stop'),
            ('claude-fable', 'generic_missing_permission_boundary', 'permissions'),
            ('claude-fable', 'generic_missing_delegation_contract', 'delegation'))

        def codes(script, without=None):
            path = self.dir / f'mandat-{script}-{without}.md'
            path.write_text(context + ''.join(v for k, v in sections.items() if k != without), encoding='utf-8')
            proc = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-B',
                                   str(PACKAGE / f'{script}-prompt-optimizer/scripts/prompt_lint.py'),
                                   str(path), '--format', 'json'],
                                  capture_output=True, text=True, encoding='utf-8', timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return {w['code'] for w in json.loads(proc.stdout)['warnings']}

        for script, code, rubric in rows:
            with self.subTest(script=script, code=code):
                self.assertNotIn(code, codes(script))
                self.assertIn(code, codes(script, rubric))

    def test_scripts_synthetic_inputs(self):
        (self.dir / 'p.txt').write_text('You are a helpful assistant. Think step by step.\n', encoding='utf-8')
        (self.dir / 'd.jsonl').write_text('{"input": "a", "expected": "b"}\n{"input": "c", "expected": "d"}\n',
                                          encoding='utf-8')
        (self.dir / 'h.py').write_text('client.messages.create(model="claude-opus-5-5", max_tokens=10)\n',
                                       encoding='utf-8')
        cases = [(SCRIPTS[0], 'p.txt'), (SCRIPTS[2], 'p.txt'), (SCRIPTS[1], 'd.jsonl'), (SCRIPTS[3], 'd.jsonl'),
                 (SCRIPTS[4], 'h.py'), (SCRIPTS[5], 'p.txt'), (SCRIPTS[6], 'd.jsonl'), (SCRIPTS[7], 'h.py')]
        before = sorted(p.name for p in self.dir.iterdir())
        for rel, arg in cases:
            with self.subTest(rel):
                proc = self.run_script(rel, arg, '--format', 'json')
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIsInstance(json.loads(proc.stdout), dict)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), before)  # aucun fichier écrit
        self.assertFalse(list(PACKAGE.rglob('__pycache__')))


class RunnerR1Tests(Base):
    def collect_synthetic(self, expected_failure=False, unexpected_success=False):
        module = self.dir / 'test_synthetic.py'
        lines = ['import unittest', 'class Synthetic(unittest.TestCase):']
        for i in range(25):
            if i == 24 and (expected_failure or unexpected_success):
                lines.append('    @unittest.expectedFailure')
            lines.append(f'    def test_{i:02d}(self):')
            lines.append("        self.fail('known red')" if i == 24 and expected_failure
                         else '        self.assertTrue(True)')
        module.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        report = self.dir / 'results.json'
        proc = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'tools' / 'check.py'),
                               '--collect', str(self.dir), str(self.dir), str(report)],
                              cwd=self.dir, capture_output=True, text=True, encoding='utf-8', timeout=30)
        return proc, json.loads(report.read_text(encoding='utf-8'))

    def test_expected_failure_recorded(self):
        """R1-02 : le vrai collecteur conserve et refuse l'obligation connue rouge."""
        proc, report = self.collect_synthetic(expected_failure=True)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report['tests_run'], 25)
        self.assertEqual(report['failures'], [])
        self.assertEqual(len(report['expected_failures']), 1)
        self.assertTrue(report['expected_failures'][0].endswith('Synthetic.test_24'))

    def test_clean_collection_passes(self):
        """Témoin propre : les 25 vrais succès restent acceptés."""
        proc, report = self.collect_synthetic()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report['tests_run'], 25)
        self.assertEqual(report.get('expected_failures', []), [])
        runner = _load('check_r1_clean', ROOT / 'tools' / 'check.py')
        # Le compte est propre à l'étape de production, pas à cette fixture de 25 cas.
        with mock.patch.dict(runner.EXPECTED, {'updater-v8': 25}):
            passed, reasons = runner.judge('updater-v8', 0, report)
        self.assertTrue(passed, reasons)

    def test_judge_rules(self):
        """Chaque règle du juge refuse un résultat synthétique qui la viole ; le témoin passe (R3B-C04)."""
        runner = _load('check_judge_rules', ROOT / 'tools' / 'check.py')
        v7 = {'module_sha256': hashlib.sha256((ROOT / 'tools' / 'rc_update.py').read_bytes()).hexdigest(),
              'new_manifest_sha256': hashlib.sha256((ROOT / 'tests' / 'fixtures' / 'v7' / 'manifest.json')
                                                    .read_bytes()).hexdigest()}
        junction = 'test_rc_update_v8.PlanV8Tests.test_dependency_junction_refused'
        for label, step, change, code, system, expected in (
                ('témoin', 'updater-v8', {}, 0, 'nt', None),
                ('code de sortie', 'updater-v8', {}, 1, 'nt', 'exit code'),
                ('résultats absents ou illisibles', 'updater-v8', None, 0, 'nt', 'no readable results file'),
                ('compte attendu', 'updater-v8', {'tests_run': 1, 'collected': ['a']}, 0, 'nt', 'collection'),
                ('identifiants collectés', 'updater-v8', {'collected': ['a']}, 0, 'nt', 'collected ids differ'),
                ('échec', 'updater-v8', {'failures': ['a']}, 0, 'nt', 'failures or errors'),
                ('erreur', 'updater-v8', {'errors': ['a']}, 0, 'nt', 'failures or errors'),
                ('succès inattendu', 'updater-v8', {'unexpected_successes': ['a']}, 0, 'nt', 'failures or errors'),
                ('échec attendu', 'updater-v8', {'expected_failures': ['a']}, 0, 'nt', 'expected failure'),
                ('skip sous Windows', 'updater-v8', {'skipped': [{'id': junction}]}, 0, 'nt', 'undeclared skips'),
                ('skip déclaré hors Windows', 'updater-v8', {'skipped': [{'id': junction}]}, 0, 'posix', None),
                ('skip homonyme hors Windows', 'updater-v8',
                 {'skipped': [{'id': junction.replace('PlanV8Tests', 'OtherTests')}]}, 0, 'posix', 'undeclared skips'),
                ('entrées v7', 'updater-v7', {'inputs': v7}, 0, 'nt', None),
                ('autres entrées v7', 'updater-v7', {'inputs': {**v7, 'module_sha256': '0' * 64}}, 0, 'nt',
                 'other inputs')):
            count = runner.EXPECTED[step]
            report = None if change is None else {
                'tests_run': count, 'collected': [f'test_{i}' for i in range(count)], 'failures': [], 'errors': [],
                'skipped': [], 'unexpected_successes': [], 'expected_failures': [], **change}
            with self.subTest(label), mock.patch.object(runner, 'os', mock.NonCallableMock(name=system)):
                runner.os.name = system
                passed, reasons = runner.judge(step, code, report)
                if expected is None:
                    self.assertTrue(passed, reasons)
                else:
                    self.assertFalse(passed)
                    self.assertTrue(any(expected in reason for reason in reasons), reasons)

    def test_collect_refuses_non_isolated(self):
        """T2-08, T2-10 : le collecteur lancé hors de python -I ne produit pas de résultats."""
        (self.dir / 'test_synthetic.py').write_text('import unittest\n', encoding='utf-8')
        report = self.dir / 'results.json'
        proc = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'check.py'), '--collect', str(self.dir),
                               str(self.dir), str(report)], cwd=self.dir, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['tests_run'], 0)

    def test_unexpected_success_rejected(self):
        """Garde existante : une attente d'échec devenue fausse reste signalée."""
        proc, report = self.collect_synthetic(unexpected_success=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(len(report['unexpected_successes']), 1)


class CheckPreflightTests(Base):
    def mini_repo(self, name='repo', sources=None, reading=b'mot\n'):
        """check.py, un paquet de trois fichiers de lecture et les sources données, toutes inventoriées."""
        repo = self.dir / name
        (repo / 'tools').mkdir(parents=True)
        (repo / 'tests').mkdir()
        shutil.copyfile(ROOT / 'tools' / 'check.py', repo / 'tools' / 'check.py')
        for rel, text in (sources or {}).items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text, encoding='utf-8')
        entries = []
        for name in ('SKILL.md', 'references/program-contract.md', 'references/operating-loop.md'):
            path = repo / 'package' / 'rc-coordinate-development' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(reading)
            entries.append({'path': 'rc-coordinate-development/' + name,
                            'sha256': hashlib.sha256(reading).hexdigest(), 'bytes': len(reading)})
        (repo / 'manifest.json').write_text(json.dumps({'files': entries}), encoding='utf-8')
        listed = [{'path': 'package/' + e['path'], 'sha256': e['sha256']} for e in entries]
        listed += [{'path': rel, 'sha256': hashlib.sha256((repo / rel).read_bytes()).hexdigest()}
                   for rel in ['tools/check.py', *(sources or {})]]
        (repo / 'provenance.json').write_text(json.dumps({'files': listed}), encoding='utf-8')
        return repo

    def run_check(self, repo, fixtures_root, **env):
        proc = subprocess.run([sys.executable, '-B', str(repo / 'tools' / 'check.py')], cwd=repo,
                              env={**os.environ, 'RC_CHECK_FIXTURES_ROOT': str(fixtures_root), **env},
                              capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn('Traceback', proc.stderr)
        summaries = list((repo / '.local').glob('*/summary.json'))
        self.assertEqual(len(summaries), 1, proc.stdout + proc.stderr)
        return proc, summaries[0].parent, json.loads(summaries[0].read_text(encoding='utf-8'))

    @unittest.skipUnless(os.name == 'nt', 'the fixture root length preflight applies to Windows only')
    def test_preflight_refusal_writes_summary(self):
        """R08-02, R06-12 : une base trop longue, même écrite courte en relatif, est refusée par le
        préflight avec son summary.json, sans lancer d'étape."""
        for label, root in (('absolu', self.dir / ('x' * 100)), ('relatif', 'y' * 70)):
            with self.subTest(label):
                repo = self.mini_repo('repo-' + label)
                long_root = (repo / root).resolve()
                proc, _, summary = self.run_check(repo, root)
                self.assertEqual(summary['inventory_problems'], [])
                self.assertEqual(summary['candidate']['package_files'], 3)
                self.assertTrue(str(summary['preflight_problem']['root']).startswith(str(long_root)))
                self.assertEqual(summary['results'], [])
                self.assertFalse(summary['all_passed'])
                self.assertFalse(long_root.exists())

    def test_inventory_refusal_writes_summary(self):
        """Chaque règle de l'inventaire, et des étapes sur la copie : refus nommé, summary.json, copie
        retirée, aucune trace (R06-13, R06-17, R3B-C04, R4-C02 à C05, R4-C07)."""
        reading = 'package/rc-coordinate-development/SKILL.md'

        def provenance(repo, change):
            doc = json.loads((repo / 'provenance.json').read_text(encoding='utf-8'))
            change(doc['files'])
            (repo / 'provenance.json').write_text(json.dumps(doc), encoding='utf-8')

        def append(repo, rel, data=b'x\n'):
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_bytes(((repo / rel).read_bytes() if (repo / rel).exists() else b'') + data)

        def extra_listed(repo):
            append(repo, 'package/rc-coordinate-development/extra.md')
            provenance(repo, lambda files: files.append(
                {'path': 'package/rc-coordinate-development/extra.md', 'sha256': hashlib.sha256(b'x\n').hexdigest()}))

        def lock(repo):
            path = repo / 'docs/x.md'
            if os.name != 'nt':
                path.chmod(0)
                return lambda: path.chmod(0o644)
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateFileW.restype = ctypes.c_void_p
            kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                           ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)  # lecture, sans partage
            return lambda: kernel.CloseHandle(handle)

        bad_results = ("import atexit, pathlib, sys\n"
                       "atexit.register(lambda: pathlib.Path(sys.argv[4]).write_text('{'))\n")
        rewrite = ("import pathlib\np = pathlib.Path(__file__).resolve().parents[2] / 'tools' / 'check.py'\n"
                   "p.write_bytes(p.read_bytes() + b'\\n')\n")

        def extra_in_manifest(repo):
            append(repo, 'package/rc-coordinate-development/extra.md')
            doc = json.loads((repo / 'manifest.json').read_text(encoding='utf-8'))
            doc['files'].append({'path': 'rc-coordinate-development/extra.md',
                                 'sha256': hashlib.sha256(b'x\n').hexdigest(), 'bytes': 2})
            (repo / 'manifest.json').write_text(json.dumps(doc), encoding='utf-8')

        for label, sources, words, change, check in (
                ('chemin qui remonte', None, 1, lambda repo: provenance(repo, lambda files: files.append(
                    {'path': '../outside.py', 'sha256': '0' * 64})), 'provenance_path'),
                ('chemin absolu', None, 1, lambda repo: provenance(repo, lambda files: files.append(
                    {'path': str(repo / 'tools' / 'check.py'), 'sha256': '0' * 64})), 'provenance_path'),
                ('destination en double', None, 1, lambda repo: provenance(repo, lambda files: files.append(
                    {**files[-1], 'path': files[-1]['path'].upper()})), 'provenance_duplicate'),
                ('entrée illisible', {'docs/x.md': 'x\n'}, 1, lock, 'unreadable'),
                ('résultat d\'étape illisible', {'tests/state/test_bad.py': bad_results}, 1, lambda repo: None,
                 'no readable results file'),
                ('copie modifiée par une étape', {'tests/state/test_rewrite.py': rewrite}, 1, lambda repo: None,
                 'copy_changed'),
                ('lecture obligatoire retirée', None, 1, lambda repo: (repo / reading).unlink(), 'pilot_reading_missing'),
                ('budget de lecture', None, 4000, lambda repo: None, 'pilot_reading'),
                ('provenance à BOM', None, 1, lambda repo: (repo / 'provenance.json').write_bytes(
                    codecs.BOM_UTF8 + (repo / 'provenance.json').read_bytes()), 'unreadable'),
                ('manifeste à BOM', None, 1, lambda repo: (repo / 'manifest.json').write_bytes(
                    codecs.BOM_UTF8 + (repo / 'manifest.json').read_bytes()), 'unreadable'),
                ('octets du paquet', None, 1, lambda repo: append(repo, reading), 'package_bytes'),
                ('octets hors paquet', {'docs/x.md': 'x\n'}, 1, lambda repo: append(repo, 'docs/x.md'),
                 'provenance_sha256'),
                ('fichier listé absent', {'docs/x.md': 'x\n'}, 1, lambda repo: (repo / 'docs/x.md').unlink(),
                 'provenance_missing'),
                ('copie identique à sa source', None, 1, lambda repo: provenance(repo, lambda files: files[0].update(
                    adaptation='byte-identical', source_sha256='0' * 64)), 'provenance_source'),
                ('fichier hors manifeste', None, 1, extra_listed, 'package_inventory'),
                ('fichier du paquet hors provenance', None, 1, extra_in_manifest, 'provenance_inventory')):
            with self.subTest(label):
                repo = self.mini_repo('repo-' + str(abs(hash(label)) % 10 ** 6), sources, b'mot ' * words + b'\n')
                release = change(repo)
                try:
                    proc, _, summary = self.run_check(repo, FIXTURES)
                finally:
                    if callable(release):
                        release()
                found = [p['check'] for p in summary['inventory_problems']] + \
                    [reason for result in summary['results'] for reason in result['reasons']]
                self.assertTrue(any(check in item for item in found), found)
                self.assertEqual(summary['results'] == [], check not in ('copy_changed', 'no readable results file'))
                self.assertFalse(summary['copy'] and Path(summary['copy']).exists())

    def test_unlisted_step_folder_writes_summary(self):
        """R06-17 : une étape dont le dossier manque dans la copie échoue, et summary.json est écrit."""
        _, _, summary = self.run_check(self.mini_repo(), FIXTURES)
        self.assertEqual(summary['inventory_problems'], [])
        self.assertEqual([r['step'] for r in summary['results']][0], 'state')
        self.assertFalse(summary['results'][0]['passed'])

    def test_tree_bytecode_not_loaded(self):
        """R06-16, T2-10, R3B-C01 : les étapes tournent sur la copie des fichiers listés, sous -I -S -B ;
        ni un .pyc forgé, ni un module hors provenance, ni un sitecustomize.py atteint par PYTHONPATH n'y
        entrent, et la copie est retirée à la fin."""
        repo = self.mini_repo(sources={'tests/state/test_mini.py': (
            'import sys\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n'
            '        self.assertTrue(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)\n')})
        (repo / 'tests' / 'state' / 'test_unlisted.py').write_text("print('MODULE HORS PROVENANCE')\n",
                                                                   encoding='utf-8')
        source = repo / 'tests' / 'state' / 'test_mini.py'
        code = compile(source.read_text(encoding='utf-8') + "\nprint('PYC FORGE CHARGE')\n", str(source), 'exec')
        stat = source.stat()
        cache = source.parent / '__pycache__' / f'{source.stem}.{sys.implementation.cache_tag}.pyc'  # hors préfixe
        cache.parent.mkdir()
        cache.write_bytes(importlib.util.MAGIC_NUMBER + bytes(4) + (int(stat.st_mtime) & 0xFFFFFFFF).to_bytes(4, 'little')
                          + (stat.st_size & 0xFFFFFFFF).to_bytes(4, 'little') + marshal.dumps(code))
        (repo / 'sitecustomize.py').write_text("print('SITECUSTOMIZE CHARGE')\n", encoding='utf-8')
        _, out, summary = self.run_check(repo, FIXTURES, PYTHONPATH=str(repo))
        self.assertEqual(summary['results'][0]['step'], 'state')
        self.assertEqual(summary['results'][0]['tests_run'], 1)
        self.assertNotIn('PYTHONPATH', summary['results'][0]['environment'])
        state = json.loads((out / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual((state['failures'], state['errors']), ([], []))
        self.assertTrue(summary['results'][0]['cwd'].startswith(summary['copy']))
        self.assertFalse(Path(summary['copy']).exists())
        log = (out / 'state.txt').read_text(encoding='utf-8')
        for marker in ('PYC FORGE CHARGE', 'MODULE HORS PROVENANCE', 'SITECUSTOMIZE CHARGE'):
            self.assertNotIn(marker, log)


class QualificationScenarioTests(unittest.TestCase):
    def test_scenarios_frozen_and_not_executed(self):
        raw = SCENARIOS.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        doc = json.loads(raw.decode('utf-8'))
        ids = [s['id'] for s in doc['scenarios']]
        self.assertEqual(len(ids), len(set(ids)))
        for prefix in ('Q1-ordinaire', 'Q2-faux-positif', 'Q3-doublon', 'Q4-bloquant', 'Q5-delta-sensible',
                       'Q6-refus-runtime', 'Q7-interruption-push', 'Q8-routage'):
            self.assertTrue(any(i.startswith(prefix) for i in ids), prefix)
        for s in doc['scenarios']:
            self.assertTrue(s['situation'] and s['oracle']['must'] and s['oracle']['must_not'], s['id'])
            self.assertTrue(set(s['skills']) <= set(rc_update.ALL_SKILLS), s['id'])
        self.assertIn('Aucun essai', doc['status'])
        qualification = (ROOT / 'docs' / 'qualification.md').read_text(encoding='utf-8')
        self.assertIn(digest, qualification)  # empreinte figée et citée avant tout essai


if __name__ == '__main__':
    unittest.main(verbosity=2)
