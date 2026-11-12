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

import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
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
           'claude-opus-prompt-optimizer/scripts/opus_api_check.py']


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
        self.assertEqual(result['distribution'], 'rc-core-with-dependencies')
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
            self.assertTrue(str(detail).endswith('current-model.md'), (name, detail))
            self.assertTrue(name.startswith('gpt-prompt-optimizer'), name)

    def test_missing_script_resource_red(self):
        copy = self.copy()
        (copy / 'claude-opus-prompt-optimizer' / 'scripts' / 'opus_api_check.py').unlink()
        bad = failing(validator.validate(copy))
        self.assertTrue(bad)
        self.assertEqual(set(bad.values()), {'scripts/opus_api_check.py'})

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
        self.assertEqual(list(bad.values()), ['#no-such-section'])

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
        self.assertEqual(counts, {'gpt-prompt-optimizer': 15, 'claude-opus-prompt-optimizer': 15, 'unslop': 4})
        for f in records:
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

    def test_scripts_synthetic_inputs(self):
        (self.dir / 'p.txt').write_text('You are a helpful assistant. Think step by step.\n', encoding='utf-8')
        (self.dir / 'd.jsonl').write_text('{"input": "a", "expected": "b"}\n{"input": "c", "expected": "d"}\n',
                                          encoding='utf-8')
        (self.dir / 'h.py').write_text('client.messages.create(model="claude-opus-5-5", max_tokens=10)\n',
                                       encoding='utf-8')
        cases = [(SCRIPTS[0], 'p.txt'), (SCRIPTS[2], 'p.txt'), (SCRIPTS[1], 'd.jsonl'), (SCRIPTS[3], 'd.jsonl'),
                 (SCRIPTS[4], 'h.py')]
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

    def test_expected_failure_judge(self):
        """Même un code zéro ne permet pas au juge d'effacer un expectedFailure."""
        runner = _load('check_r1_judge', ROOT / 'tools' / 'check.py')
        count = runner.EXPECTED['updater-v8']
        report = {'tests_run': count, 'collected': [f'test_{i}' for i in range(count)],
                  'failures': [], 'errors': [], 'skipped': [], 'unexpected_successes': [],
                  'expected_failures': ['test_24']}
        passed, reasons = runner.judge('updater-v8', 0, report)
        self.assertFalse(passed)
        self.assertTrue(any('expected failure' in reason for reason in reasons), reasons)

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

    def test_unexpected_success_rejected(self):
        """Garde existante : une attente d'échec devenue fausse reste signalée."""
        proc, report = self.collect_synthetic(unexpected_success=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(len(report['unexpected_successes']), 1)


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
