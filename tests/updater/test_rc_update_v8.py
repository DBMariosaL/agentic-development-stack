"""Tests de distribution v8 de rc_update.py : trois skills RC -> six skills, sur profils factices.

Lancer depuis la racine du dépôt :
  python -B tools/check.py                       (avec les autres suites)
  python -B -m unittest tests/updater/test_rc_update_v8.py

Variables :
  RC_UPDATE_MODULE    rc_update.py éprouvé (défaut : tools/rc_update.py du dépôt)
  RC_UPDATE_FIXTURES  racine courte des profils factices (défaut : .local/g-tests du dépôt)

Ancienne version : fixture figée tests/fixtures/v7 (paquet, manifeste au format 1 et outil
v7). Nouvelle version : package/ et manifest.json du dépôt. Aucun profil actif n'est lu ni
modifié ; chaque test supprime uniquement son propre dossier sous la racine de fixtures.
"""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(os.environ.get('RC_UPDATE_MODULE') or ROOT / 'tools' / 'rc_update.py').resolve()
FIXTURES = Path(os.environ.get('RC_UPDATE_FIXTURES') or ROOT / '.local' / 'g-tests').resolve()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rc_update = _load('rc_update_v8_under_test', SCRIPT)

V7 = ROOT / 'tests' / 'fixtures' / 'v7'
OLD_PKG, OLD_MANIFEST = V7 / 'package', V7 / 'manifest.json'
NEW_PKG, NEW_MANIFEST = ROOT / 'package', ROOT / 'manifest.json'
PREVIOUS = ROOT / 'tests' / 'fixtures' / 'previous'
# Listes figées ici, indépendantes de l'outil éprouvé (un outil v7 échoue alors cas par cas).
RC = ('rc-coordinate-development', 'rc-prepare-socle-prompts', 'rc-prepare-supervisor')
DEPS = ('gpt-prompt-optimizer', 'claude-opus-prompt-optimizer', 'unslop')
ALL = RC + DEPS
UNKNOWN = {'rc-coordinate-development/notes-locales.md': b'notes locales\n'}
OUTSIDE = {'autre-skill/SKILL.md': b'skill sans rapport\n'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(root):
    """Fichiers (sha, taille, mtime) et dossiers d'un arbre."""
    files, dirs = {}, set()
    for dirpath, dirnames, names in os.walk(root):
        for d in dirnames:
            dirs.add(Path(dirpath, d).relative_to(root).as_posix())
        for n in names:
            p = Path(dirpath, n)
            st = p.stat()
            files[p.relative_to(root).as_posix()] = (sha(p.read_bytes()), st.st_size, st.st_mtime_ns)
    return files, dirs


def contents(root):
    files, dirs = tree(root)
    return {k: v[0] for k, v in files.items()}, dirs


def read_manifest(path):
    """Lecture directe, indépendante de l'outil éprouvé."""
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    return {f['path']: {'sha256': f['sha256'], 'bytes': f['bytes']} for f in doc['files']}


def copy_tree(src, dest):
    for p in sorted(src.rglob('*')):
        if p.is_file():
            out = dest / p.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(p.read_bytes())


class Base(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.dir = FIXTURES / self._testMethodName[5:]
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.dir.mkdir()
        self.junctions = []
        self.addCleanup(self.cleanup)  # même si setUp échoue ensuite
        self.profiles = {'codex': self.dir / 'codex', 'claude': self.dir / 'claude'}
        self.targets = [self.profiles['codex'] / 'skills', self.profiles['claude'] / 'skills']
        for t in self.targets:
            self.build_profile(t, OLD_PKG)
        self.state = self.dir / 'etat'
        self.plan = self.dir / 'plan.json'
        self.new = read_manifest(NEW_MANIFEST)
        self.old = read_manifest(OLD_MANIFEST)

    def cleanup(self):
        for j in self.junctions:
            if os.path.lexists(j):
                os.rmdir(j)  # retire la jonction sans toucher sa cible
        shutil.rmtree(self.dir)

    def build_profile(self, target, package):
        if target.exists():
            shutil.rmtree(target)
        copy_tree(package, target)
        for rel, data in {**UNKNOWN, **OUTSIDE}.items():
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)

    def install_dep(self, target, skill):
        copy_tree(NEW_PKG / skill, target / skill)

    def run_main(self, *args, module=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = (module or rc_update).main([str(a) for a in args])
        text = out.getvalue() or err.getvalue()
        return code, (json.loads(text) if text.strip() else None)

    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, args)],
                              capture_output=True, text=True, encoding='utf-8')
        text = proc.stdout or proc.stderr
        return proc.returncode, (json.loads(text) if text.strip() else None)

    def preflight(self, prev=OLD_MANIFEST, pkg=NEW_PKG, manifest=NEW_MANIFEST, plan=None, cli=False):
        args = ['preflight', '--previous-manifest', prev, '--new-package', pkg,
                '--target', self.targets[0], '--target', self.targets[1], '--plan-out', plan or self.plan]
        if manifest:
            args += ['--new-manifest', manifest]
        return (self.run_cli if cli else self.run_main)(*args)

    def apply(self, *extra):
        return self.run_main('apply', '--plan', self.plan, '--state-dir', self.state, *extra)

    def rollback(self):
        return self.run_main('rollback', '--plan', self.plan, '--state-dir', self.state)

    def resume(self):
        return self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)

    def plan_doc(self):
        return json.loads(self.plan.read_text(encoding='utf-8'))

    def journal(self):
        path = self.state / self.plan_doc()['plan_id'] / 'journal.jsonl'
        return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]

    def trees(self):
        return {k: tree(v) for k, v in self.profiles.items()}

    def snapshot(self):
        return {k: contents(v) for k, v in self.profiles.items()}

    def sub(self, target, skill):
        return {k: v for k, v in tree(target)[0].items() if k.startswith(skill + '/')}

    def assert_new(self, target, skills=ALL):
        for rel, item in self.new.items():
            if rel.split('/')[0] in skills:
                self.assertEqual(sha((target / rel).read_bytes()), item['sha256'], rel)

    def assert_clean_targets(self):
        for t in self.targets:
            for dirpath, dirnames, names in os.walk(t):
                self.assertNotIn('__pycache__', dirnames, dirpath)
                for n in names:
                    self.assertFalse(n.startswith(rc_update.TMP_PREFIX) or n.endswith('.tmp'), n)

    def assert_foreign_intact(self):
        for t in self.targets:
            for rel, data in {**UNKNOWN, **OUTSIDE}.items():
                self.assertEqual((t / rel).read_bytes(), data, rel)

    def fail_target_swap(self, at):
        real_swap = rc_update._swap
        n = [0]

        def failing_swap(tmp, dest, exclusive):
            if self.state in Path(dest).parents:
                return real_swap(tmp, dest, exclusive)
            n[0] += 1
            if n[0] == at:
                raise OSError('panne injectée')
            return real_swap(tmp, dest, exclusive)
        return mock.patch.object(rc_update, '_swap', failing_swap)


class ManifestV2Tests(Base):
    def test_manifest_v2_matches_package(self):
        doc = json.loads(NEW_MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(doc['format'], 'rc-update-manifest/2')
        self.assertEqual(doc['distribution'], 'rc-core-with-dependencies')
        self.assertEqual({s['name']: s['role'] for s in doc['skills']},
                         {**{s: 'rc' for s in RC}, **{d: 'dependency' for d in DEPS}})
        self.assertEqual(rc_update.compute_manifest(NEW_PKG), self.new)
        self.assertEqual(len(self.new), sum(1 for p in NEW_PKG.rglob('*') if p.is_file()))
        code, out = self.run_cli('manifest', '--package', NEW_PKG)
        self.assertEqual(code, 0)
        self.assertEqual(out, doc)
        code, out = self.run_cli('manifest', '--package', OLD_PKG)
        self.assertEqual(out, json.loads(OLD_MANIFEST.read_text(encoding='utf-8')))  # format 1 inchangé

    def test_forged_manifest_refused(self):
        base = json.loads(NEW_MANIFEST.read_text(encoding='utf-8'))
        extra = {'path': 'evil-skill/SKILL.md', 'sha256': '0' * 64, 'bytes': 1}
        forged = {
            'extra_skill': {**base, 'files': base['files'] + [extra]},
            'role_swapped': {**base, 'skills': [dict(s, role='rc') if s['name'] == 'unslop' else s
                                                for s in base['skills']]},
            'unknown_distribution': {**base, 'distribution': 'custom'},
            'unknown_format': {**base, 'format': 'rc-update-manifest/9'},
            'digest': {**base, 'digest': '0' * 64},
            'escape': {**base, 'files': [dict(base['files'][0], path='unslop/../../evil.md')] + base['files'][1:]},
            'legacy_with_dependency': {'files': json.loads(OLD_MANIFEST.read_text(encoding='utf-8'))['files']
                                       + [base['files'][0]]},
        }
        before = self.trees()
        for label, doc in forged.items():
            with self.subTest(label):
                path = self.dir / f'{label}.json'
                path.write_text(json.dumps(doc), encoding='utf-8')
                plan = self.dir / f'plan-{label}.json'
                prev, manifest = (path, NEW_MANIFEST) if label == 'legacy_with_dependency' else (OLD_MANIFEST, path)
                code, out = self.preflight(prev=prev, manifest=manifest, plan=plan)
                self.assertEqual(code, 1, out)
                self.assertFalse(plan.exists())
        self.assertEqual(self.trees(), before)

    def test_downgrade_refused(self):
        for t in self.targets:
            self.build_profile(t, NEW_PKG)
        before = self.trees()
        code, out = self.preflight(prev=NEW_MANIFEST, pkg=OLD_PKG, manifest=OLD_MANIFEST)
        self.assertEqual(code, 1, out)
        self.assertIn('Transition', out['error'])
        self.assertFalse(self.plan.exists())
        self.assertEqual(self.trees(), before)

    def test_unregistered_package_skill_refused(self):
        moved = self.dir / 'paquet'
        copy_tree(NEW_PKG, moved)
        (moved / 'autre-skill').mkdir()
        (moved / 'autre-skill' / 'SKILL.md').write_bytes(b'x')
        with self.assertRaises(rc_update.UpdateError):
            rc_update.compute_manifest(moved)
        (moved / 'autre-skill' / 'SKILL.md').unlink()
        (moved / 'autre-skill').rmdir()
        shutil.rmtree(moved / 'unslop')
        with self.assertRaises(rc_update.UpdateError):  # sous-ensemble non reconnu
            rc_update.compute_manifest(moved)


class PlanV8Tests(Base):
    def test_three_to_six_plan(self):
        before = self.trees()
        code, out = self.preflight(cli=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.trees(), before)  # le préflight n'écrit rien dans les cibles
        self.assertEqual(out['distributions'], {'previous': 'rc-core', 'new': 'rc-core-with-dependencies'})
        plan = self.plan_doc()
        self.assertEqual(plan['format'], 'rc-update-plan/2')
        expected = {}
        for rel in sorted(set(self.old) | set(self.new)):
            if rel not in self.old:
                expected[rel] = 'create'
            elif rel not in self.new:
                expected[rel] = 'remove'
            elif self.old[rel]['sha256'] != self.new[rel]['sha256']:
                expected[rel] = 'replace'
            else:
                expected[rel] = 'unchanged'
        expected.update({rel: 'preserve-unknown' for rel in UNKNOWN})
        for t in plan['targets']:
            self.assertEqual(t['status'], 'ok')
            status = {s['name']: s['status'] for s in t['skills']}
            self.assertEqual(status, {**{s: 'update' for s in RC}, **{d: 'install' for d in DEPS}})
            got = {f['path']: f['decision'] for s in t['skills'] for f in s['files']}
            self.assertEqual(got, expected)
            self.assertNotIn('autre-skill/SKILL.md', t['observed'])
        creates = sum(1 for r in self.new if r.split('/')[0] in DEPS)
        self.assertEqual(creates, 34)
        self.assertEqual(len(plan['actions']), 2 * sum(v != 'unchanged' and v != 'preserve-unknown'
                                                        for v in expected.values()))
        self.assertFalse(plan['blocked'])

    def test_identical_dependency_unchanged(self):
        self.install_dep(self.targets[1], 'unslop')
        code, out = self.preflight()
        self.assertEqual(code, 0, out)
        self.assertEqual(out['targets'][1]['skills']['unslop'], 'already-new')
        self.assertEqual([a for a in self.plan_doc()['actions']
                          if a['target'] == 1 and a['path'].startswith('unslop/')], [])
        before = self.sub(self.targets[1], 'unslop')
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(self.sub(self.targets[1], 'unslop'), before)  # octets et mtime inchangés
        self.assert_new(self.targets[1])

    def test_custom_dependency_conflict(self):
        self.install_dep(self.targets[1], 'gpt-prompt-optimizer')
        custom = self.targets[1] / 'gpt-prompt-optimizer' / 'SKILL.md'
        custom.write_bytes(custom.read_bytes() + b'\n<!-- personnalisation locale -->\n')
        code, out = self.preflight()
        self.assertEqual(code, 2, out)
        claude = out['targets'][1]
        self.assertEqual(claude['skills']['gpt-prompt-optimizer'], 'conflict')
        self.assertEqual(claude['conflicts'], ['gpt-prompt-optimizer/SKILL.md'])
        self.assertIn('personnalisée', claude['skill_reasons']['gpt-prompt-optimizer'][0])
        before = self.trees()
        self.assertEqual(self.apply()[0], 2)  # bloqué sans accord explicite
        self.assertEqual(self.trees(), before)
        self.assertFalse(self.state.exists())
        gpt_before = self.sub(self.targets[1], 'gpt-prompt-optimizer')
        code, out = self.apply('--allow-blocked')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.sub(self.targets[1], 'gpt-prompt-optimizer'), gpt_before)
        self.assert_new(self.targets[0])
        self.assert_new(self.targets[1], tuple(s for s in ALL if s != 'gpt-prompt-optimizer'))
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)

    def test_partial_dependency_conflict(self):
        (self.targets[1] / 'unslop').mkdir()
        (self.targets[1] / 'unslop' / 'SKILL.md').write_bytes((NEW_PKG / 'unslop' / 'SKILL.md').read_bytes())
        code, out = self.preflight()
        self.assertEqual(code, 2, out)
        self.assertEqual(out['targets'][1]['skills']['unslop'], 'conflict')
        self.assertEqual(sorted(out['targets'][1]['conflicts']),
                         sorted(r for r in self.new if r.startswith('unslop/') and r != 'unslop/SKILL.md'))
        before = self.sub(self.targets[1], 'unslop')
        self.assertEqual(self.apply('--allow-blocked')[0], 0)
        self.assertEqual(self.sub(self.targets[1], 'unslop'), before)  # aucun fichier manquant ajouté

    def test_same_name_unknown_dependency_conflict(self):
        mine = self.targets[1] / 'unslop' / 'notes.md'
        mine.parent.mkdir()
        mine.write_bytes(b'mon propre skill du meme nom\n')
        code, out = self.preflight()
        self.assertEqual(code, 2, out)
        self.assertEqual(out['targets'][1]['skills']['unslop'], 'conflict')
        self.assertIn('origine inconnue', out['targets'][1]['skill_reasons']['unslop'][0])
        self.assertIn('unslop/notes.md', out['targets'][1]['unknown'])
        self.assertEqual(self.apply('--allow-blocked')[0], 0)
        self.assertEqual(sorted(p.name for p in mine.parent.iterdir()), ['notes.md'])
        self.assertEqual(mine.read_bytes(), b'mon propre skill du meme nom\n')

    def test_unknown_file_in_identical_dependency(self):
        self.install_dep(self.targets[1], 'claude-opus-prompt-optimizer')
        extra = self.targets[1] / 'claude-opus-prompt-optimizer' / 'local.md'
        extra.write_bytes(b'ajout local\n')
        code, out = self.preflight()
        self.assertEqual(code, 0, out)
        self.assertEqual(out['targets'][1]['skills']['claude-opus-prompt-optimizer'], 'already-new')
        decisions = {f['path']: f['decision'] for s in self.plan_doc()['targets'][1]['skills'] for f in s['files']}
        self.assertEqual(decisions['claude-opus-prompt-optimizer/local.md'], 'preserve-unknown')
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(extra.read_bytes(), b'ajout local\n')
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)

    def test_dependency_case_collision_refused(self):
        odd = self.targets[0] / 'unslop' / 'skill.md'
        odd.parent.mkdir()
        odd.write_bytes(b'casse differente\n')
        code, out = self.preflight()
        self.assertEqual(code, 2, out)
        self.assertEqual(out['targets'][0]['status'], 'refused')
        self.assertEqual([a for a in self.plan_doc()['actions'] if a['target'] == 0], [])
        before = tree(self.profiles['codex'])
        self.assertEqual(self.apply('--allow-blocked')[0], 0)
        self.assertEqual(tree(self.profiles['codex']), before)

    def test_dependency_junction_refused(self):
        if os.name != 'nt':
            self.skipTest('jonction NTFS seulement sous Windows')
        import _winapi
        elsewhere = self.dir / 'ailleurs'
        elsewhere.mkdir()
        link = self.targets[0] / 'unslop'
        _winapi.CreateJunction(str(elsewhere), str(link))
        self.junctions.append(link)
        code, out = self.preflight()
        self.assertEqual(code, 1, out)
        self.assertIn('réparse', out['error'])
        self.assertFalse(self.plan.exists())
        self.assertEqual(list(elsewhere.iterdir()), [])


class ApplyV8Tests(Base):
    def test_apply_installs_and_verifies(self):
        self.assertEqual(self.preflight()[0], 0)
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        for t in self.targets:
            self.assert_new(t)
        self.assert_foreign_intact()
        self.assert_clean_targets()
        made = {Path(e['dir']).relative_to(self.dir).as_posix() for e in self.journal() if e['event'] == 'mkdir'}
        for prof in ('codex', 'claude'):
            for d in DEPS:
                self.assertIn(f'{prof}/skills/{d}', made)
        code, rep = self.run_cli('verify', '--plan', self.plan)
        self.assertEqual(code, 0, rep)

    def test_verify_detects_tampered_dependency(self):
        self.preflight()
        self.apply()
        (self.targets[1] / 'unslop' / 'references' / 'patterns.md').write_bytes(b'altere')
        code, rep = self.run_cli('verify', '--plan', self.plan)
        self.assertEqual(code, 1)
        self.assertEqual([m['path'] for m in rep['targets'][1]['mismatches']], ['unslop/references/patterns.md'])

    def test_interrupt_install_then_resume(self):
        self.preflight()
        actions = self.plan_doc()['actions']
        k = next(i for i, a in enumerate(actions) if a['op'] == 'create' and a['path'].split('/')[0] in DEPS)
        self.assertTrue(actions[k + 2]['path'].startswith('gpt-prompt-optimizer/'), actions[k + 2])
        with self.fail_target_swap(k + 3), mock.patch.object(rc_update, '_discard_tmp', lambda *a: False):
            code, out = self.apply()
        self.assertEqual(code, 1)
        left = [Path(d, n) for t in self.targets for d, _, ns in os.walk(t) for n in ns
                if n.startswith(rc_update.TMP_PREFIX)]
        self.assertEqual(len(left), 1, left)
        done = [e['step'] for e in self.journal() if e['event'] == 'verified']
        self.assertEqual(len(done), k + 2)
        code, _ = self.preflight(plan=self.dir / 'plan-2.json')
        self.assertEqual(code, 2)  # dépendance à moitié installée : conflit, pas d'écrasement
        code, out = self.resume()
        self.assertEqual(code, 0, out)
        self.assertEqual(out['cleaned_temps'], [str(left[0])])
        for t in self.targets:
            self.assert_new(t)
        self.assert_foreign_intact()
        self.assert_clean_targets()
        events = self.journal()
        for s in done:
            self.assertEqual(sum(e['event'] == 'written' and e['step'] == s for e in events), 1, s)
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)

    def test_resume_refuses_foreign_file_in_new_dependency(self):
        self.preflight()
        k = next(i for i, a in enumerate(self.plan_doc()['actions'])
                 if a['op'] == 'create' and a['path'].split('/')[0] in DEPS)
        with self.fail_target_swap(k + 5):
            self.assertEqual(self.apply()[0], 1)
        stray = self.targets[0] / 'gpt-prompt-optimizer' / 'tiers.md'
        self.assertTrue(stray.parent.is_dir())
        stray.write_bytes(b'depose par un tiers pendant la panne\n')
        before = self.trees()
        code, out = self.resume()
        self.assertEqual(code, 1, out)
        self.assertIn('inattendu', out['error'])
        self.assertEqual(self.trees(), before)
        self.assertEqual(stray.read_bytes(), b'depose par un tiers pendant la panne\n')

    def test_moved_package_without_source(self):
        moved = self.dir / 'm'
        copy_tree(NEW_PKG, moved / 'package')
        (moved / 'manifest.json').write_bytes(NEW_MANIFEST.read_bytes())
        code, out = self.preflight(pkg=moved / 'package', manifest=moved / 'manifest.json')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.plan_doc()['new_package'], str((moved / 'package').resolve()))
        self.assertEqual(self.apply()[0], 0)
        for t in self.targets:
            self.assert_new(t)
        missing = moved / 'package' / 'unslop' / 'assets' / 'icon.svg'
        missing.unlink()
        code, out = self.preflight(pkg=moved / 'package', manifest=moved / 'manifest.json',
                                   plan=self.dir / 'plan-3.json')
        self.assertEqual(code, 1, out)  # paquet déplacé incomplet : refus ciblé
        self.assertIn('unslop/assets/icon.svg', out['error'])


class RollbackV8Tests(Base):
    def test_rollback_after_install(self):
        initial = self.snapshot()
        self.preflight()
        self.assertEqual(self.apply()[0], 0)
        code, out = self.rollback()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), initial)  # fichiers et dossiers créés retirés
        self.assert_clean_targets()
        self.assertEqual(self.run_cli('verify', '--plan', self.plan, '--expect', 'previous')[0], 0)
        rmdirs = {Path(e['dir']).name for e in self.journal() if e['event'] == 'rollback-rmdir'}
        self.assertTrue(set(DEPS) <= rmdirs)

    def test_rollback_after_partial_install(self):
        initial = self.snapshot()
        self.preflight()
        per_target = len([a for a in self.plan_doc()['actions'] if a['target'] == 0 and a['op'] != 'remove'])
        with self.fail_target_swap(per_target + 10):
            self.assertEqual(self.apply()[0], 1)
        self.assert_clean_targets()
        code, out = self.rollback()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), initial)

    def test_rollback_refuses_foreign_file(self):
        self.preflight()
        self.assertEqual(self.apply()[0], 0)
        mine = self.targets[0] / 'unslop' / 'mine.md'
        mine.write_bytes(b'ajout tiers apres installation\n')
        before = self.trees()
        code, out = self.rollback()
        self.assertEqual(code, 1, out)
        self.assertEqual(self.trees(), before)
        self.assertEqual(mine.read_bytes(), b'ajout tiers apres installation\n')

    def test_rollback_refuses_edited_dependency(self):
        self.preflight()
        self.assertEqual(self.apply()[0], 0)
        edited = self.targets[1] / 'gpt-prompt-optimizer' / 'SKILL.md'
        edited.write_bytes(b'edition tierce posterieure')
        before = self.trees()
        self.assertEqual(self.rollback()[0], 1)
        self.assertEqual(self.trees(), before)

    def test_rollback_keeps_preexisting_dependency(self):
        self.install_dep(self.targets[1], 'unslop')
        initial = self.snapshot()
        self.preflight()
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(self.rollback()[0], 0)
        self.assertEqual(self.snapshot(), initial)
        self.assertTrue((self.targets[1] / 'unslop' / 'SKILL.md').is_file())
        self.assertFalse((self.targets[0] / 'unslop').exists())


class CompatTests(Base):
    def make_v1_plan(self):
        """Le véritable outil v7 produit le plan ; v8 ne normalise pas sa preuve."""
        v7 = _load('rc_update_v7_unapplied', V7 / 'tools' / 'rc_update.py')
        for target in self.targets:
            self.build_profile(target, PREVIOUS / 'package')
        code, out = self.run_main('preflight', '--previous-manifest', PREVIOUS / 'release-manifest.json',
                                  '--new-package', OLD_PKG, '--new-manifest', OLD_MANIFEST,
                                  '--target', self.targets[0], '--target', self.targets[1],
                                  '--plan-out', self.plan, module=v7)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.plan_doc()['format'], 'rc-update-plan/1')

    def test_v1_apply(self):
        """R1-01 : un préflight v7 encore frais s'applique, se vérifie et s'annule."""
        self.make_v1_plan()
        initial = self.snapshot()
        plan_bytes = self.plan.read_bytes()
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.plan.read_bytes(), plan_bytes)
        self.assertEqual((Path(out['state']) / 'plan.json').read_bytes(), plan_bytes)
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)
        code, out = self.rollback()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), initial)

    def test_v1_stale(self):
        """La compatibilité ne dispense pas de recontrôler les octets observés."""
        self.make_v1_plan()
        changed = self.targets[0] / RC[0] / 'SKILL.md'
        changed.write_bytes(changed.read_bytes() + b'\nthird-party edit\n')
        before = self.trees()
        code, out = self.apply()
        self.assertEqual(code, 3, out)
        self.assertEqual(self.trees(), before)
        self.assertFalse(self.state.exists())

    def test_v1_tampered(self):
        """Ne pas effacer un champ ajouté au plan fourni pour comparer sa preuve."""
        self.make_v1_plan()
        plan = self.plan_doc()
        plan['roles'] = {'unslop': 'rc'}
        plan['fingerprint'] = rc_update.plan_fingerprint(plan)
        plan['plan_id'] = plan['fingerprint'][:16]
        self.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        before = self.trees()
        code, out = self.apply()
        self.assertEqual(code, 3, out)
        self.assertEqual(self.trees(), before)
        self.assertFalse(self.state.exists())

    def test_v8_to_v8_already_new(self):
        for t in self.targets:
            self.build_profile(t, NEW_PKG)
        code, out = self.preflight(prev=NEW_MANIFEST)
        self.assertEqual(code, 0, out)
        for t in out['targets']:
            self.assertEqual(set(t['skills'].values()), {'already-new'})
        self.assertEqual(self.plan_doc()['actions'], [])
        before = self.trees()
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(self.trees(), before)

    def test_rc_core_transition_ignores_dependency_dirs(self):
        stray = self.targets[0] / 'unslop' / 'x.md'
        stray.parent.mkdir()
        stray.write_bytes(b'hors distribution rc-core\n')
        code, out = self.preflight(prev=OLD_MANIFEST, pkg=OLD_PKG, manifest=OLD_MANIFEST)
        self.assertEqual(code, 0, out)
        plan = self.plan_doc()
        self.assertEqual(plan['skills'], list(RC))
        self.assertEqual(plan['distributions'], {'previous': 'rc-core', 'new': 'rc-core'})
        self.assertNotIn('unslop/x.md', plan['targets'][0]['observed'])
        self.assertEqual(plan['actions'], [])

    def test_v7_tool_plan_resumed_and_rolled_back(self):
        """Plan au format 1 écrit et interrompu par l'outil v7, repris puis annulé par l'outil v8."""
        v7 = _load('rc_update_v7_fixture', V7 / 'tools' / 'rc_update.py')
        for t in self.targets:
            self.build_profile(t, PREVIOUS / 'package')
        initial = self.snapshot()
        code, out = self.run_main('preflight', '--previous-manifest', PREVIOUS / 'release-manifest.json',
                                  '--new-package', OLD_PKG, '--new-manifest', OLD_MANIFEST,
                                  '--target', self.targets[0], '--target', self.targets[1],
                                  '--plan-out', self.plan, module=v7)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.plan_doc()['format'], 'rc-update-plan/1')
        real_swap, n = v7._swap, [0]

        def failing_swap(tmp, dest, exclusive):
            if self.state not in Path(dest).parents:
                n[0] += 1
                if n[0] == 4:
                    raise OSError('panne injectée (outil v7)')
            return real_swap(tmp, dest, exclusive)
        with mock.patch.object(v7, '_swap', failing_swap):
            code, _ = self.run_main('apply', '--plan', self.plan, '--state-dir', self.state, module=v7)
        self.assertEqual(code, 1)
        code, out = self.resume()
        self.assertEqual(code, 0, out)
        old = read_manifest(OLD_MANIFEST)
        for t in self.targets:
            for rel, item in old.items():
                self.assertEqual(sha((t / rel).read_bytes()), item['sha256'], rel)
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)
        code, out = self.rollback()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), initial)


if __name__ == '__main__':
    unittest.main(verbosity=2)
