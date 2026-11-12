"""Tests de rc_update.py sur deux profils factices (Codex, Claude).

Lancer : python -B test_rc_update.py [--write-results] [--results-out CHEMIN]

Les fixtures sont créées sous <lot>/epreuves/mise-a-jour/profils-factices/ et supprimées
après chaque test. Les chemins ne dépendent pas de l'emplacement de ce fichier ; chacun
peut être imposé par une variable d'environnement :

  RC_UPDATE_LOT        racine du lot (défaut : premier ancêtre de ce fichier contenant
                       à la fois epreuves/ et candidats/)
  RC_UPDATE_PREVIOUS   version installée précédente, avec package/ et release-manifest.json
                       (défaut : <lot>/../skills-workflow-alpha-20261031)
  RC_UPDATE_CANDIDATE  candidat figé, avec package/ et manifest.json ; le préflight reçoit
                       alors --new-manifest <candidat>/manifest.json (ex. <lot>/candidats/v3)
  RC_NEW_PACKAGE       paquet nouveau sans manifeste figé, si RC_UPDATE_CANDIDATE est absent
                       (défaut : <lot>/package)
  RC_UPDATE_FIXTURES   racine des profils factices
                       (défaut : <lot>/epreuves/mise-a-jour/profils-factices)
  RC_UPDATE_MODULE     rc_update.py à éprouver (défaut : celui de ce dossier) ; sert à
                       montrer que les tests R2 échouent sur la version d'origine.
"""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

HERE = Path(__file__).resolve().parent


def _env_path(name, default):
    value = os.environ.get(name)
    return Path(value).resolve() if value else default


def _find_lot():
    for p in (HERE, *HERE.parents):
        if (p / 'epreuves').is_dir() and (p / 'candidats').is_dir():
            return p
    raise SystemExit('Racine du lot introuvable : définir RC_UPDATE_LOT')


SCRIPT = _env_path('RC_UPDATE_MODULE', HERE / 'rc_update.py')
_spec = importlib.util.spec_from_file_location('rc_update', SCRIPT)
rc_update = importlib.util.module_from_spec(_spec)
sys.modules['rc_update'] = rc_update
_spec.loader.exec_module(rc_update)

LOT = _env_path('RC_UPDATE_LOT', None) or _find_lot()
OLD = _env_path('RC_UPDATE_PREVIOUS', LOT.parent / 'skills-workflow-alpha-20261031')
OLD_PKG = OLD / 'package'
OLD_MANIFEST = OLD / 'release-manifest.json'
CANDIDATE = _env_path('RC_UPDATE_CANDIDATE', None)
if CANDIDATE:
    NEW_PKG = CANDIDATE / 'package'
    NEW_MANIFEST = CANDIDATE / 'manifest.json'
else:
    NEW_PKG = _env_path('RC_NEW_PACKAGE', LOT / 'package')
    NEW_MANIFEST = None
FIXTURES = _env_path('RC_UPDATE_FIXTURES', LOT / 'epreuves' / 'mise-a-jour' / 'profils-factices')

WAVE = 'rc-coordinate-development/references/wave-contract.md'
UNKNOWN = {
    'rc-coordinate-development/notes-locales.md': b'notes locales, hors manifeste\n',
    'rc-prepare-supervisor/references/local/extra.txt': b'fichier inconnu imbrique\n',
}
OUTSIDE = {'autre-skill/SKILL.md': b'skill sans rapport, ne doit pas bouger\n'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(root):
    """Empreinte complète d'un arbre : fichiers (sha, taille, mtime) et dossiers."""
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


def copy_package(src, dest):
    for p in sorted(src.rglob('*')):
        if p.is_file():
            out = dest / p.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(p.read_bytes())


class Base(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.dir = FIXTURES / self.id().split('.')[-1]
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.dir.mkdir()
        self.profiles = {'codex': self.dir / 'codex', 'claude': self.dir / 'claude'}
        self.targets = [self.profiles['codex'] / 'skills', self.profiles['claude'] / 'skills']
        for t in self.targets:
            self.build_profile(t, OLD_PKG)
        self.state = self.dir / 'etat'
        self.plan = self.dir / 'plan.json'
        self.junctions = []
        self.prev = rc_update.load_manifest(OLD_MANIFEST)
        self.new = rc_update.compute_manifest(NEW_PKG)

    def tearDown(self):
        for j in self.junctions:
            if os.path.lexists(j):
                os.rmdir(j)  # retire la jonction sans toucher sa cible
        shutil.rmtree(self.dir)

    def build_profile(self, target, package):
        if target.exists():
            shutil.rmtree(target)
        copy_package(package, target)
        for rel, data in {**UNKNOWN, **OUTSIDE}.items():
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rc_update.main([str(a) for a in args])
        text = out.getvalue() or err.getvalue()
        return code, (json.loads(text) if text.strip() else None)

    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, args)],
                              capture_output=True, text=True, encoding='utf-8')
        text = proc.stdout or proc.stderr
        return proc.returncode, (json.loads(text) if text.strip() else None)

    def preflight(self, plan=None, cli=False):
        args = ['preflight', '--previous-manifest', OLD_MANIFEST, '--new-package', NEW_PKG,
                '--target', self.targets[0], '--target', self.targets[1], '--plan-out', plan or self.plan]
        if NEW_MANIFEST:
            args += ['--new-manifest', NEW_MANIFEST]
        return (self.run_cli if cli else self.run_main)(*args)

    def apply(self, *extra):
        return self.run_main('apply', '--plan', self.plan, '--state-dir', self.state, *extra)

    def plan_doc(self):
        return json.loads(self.plan.read_text(encoding='utf-8'))

    def assert_clean_targets(self):
        for t in self.targets:
            for dirpath, dirnames, names in os.walk(t):
                self.assertNotIn('__pycache__', dirnames, dirpath)
                for n in names:
                    self.assertFalse(n.startswith(rc_update.TMP_PREFIX) or n.endswith('.tmp'), n)
                    self.assertFalse(n.endswith('.pyc'), n)

    def assert_new(self, target, skills=rc_update.SKILLS):
        for rel, item in self.new.items():
            if rel.split('/')[0] in skills:
                self.assertEqual(sha((target / rel).read_bytes()), item['sha256'], rel)
        for rel in self.prev:
            if rel not in self.new and rel.split('/')[0] in skills:
                self.assertFalse((target / rel).exists(), rel)

    def assert_previous(self, target, skills=rc_update.SKILLS):
        for rel, item in self.prev.items():
            if rel.split('/')[0] in skills:
                self.assertEqual(sha((target / rel).read_bytes()), item['sha256'], rel)
        for rel in self.new:
            if rel not in self.prev and rel.split('/')[0] in skills:
                self.assertFalse((target / rel).exists(), rel)

    def assert_unknown_and_outside_intact(self):
        for t in self.targets:
            for rel, data in {**UNKNOWN, **OUTSIDE}.items():
                self.assertEqual((t / rel).read_bytes(), data, rel)

    def journal(self):
        sid = self.plan_doc()['plan_id']
        path = self.state / sid / 'journal.jsonl'
        return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


class ManifestTests(Base):
    def test_manifest_matches_previous_release(self):
        self.assertEqual(rc_update.compute_manifest(OLD_PKG), self.prev)
        code, doc = self.run_cli('manifest', '--package', NEW_PKG)
        self.assertEqual(code, 0)
        self.assertEqual(len(doc['files']), 12)
        self.assertTrue(all('/' in f['path'] and '\\' not in f['path'] for f in doc['files']))
        self.assertNotIn(WAVE, {f['path'] for f in doc['files']})

    def test_candidate_manifest_matches_package(self):
        if not NEW_MANIFEST:
            self.skipTest('RC_UPDATE_CANDIDATE non défini')
        self.assertEqual(rc_update.compute_manifest(NEW_PKG), rc_update.load_manifest(NEW_MANIFEST))


class PreflightTests(Base):
    def test_preflight_writes_nothing_in_targets(self):
        before = {k: tree(v) for k, v in self.profiles.items()}
        code, out = self.preflight(cli=True)
        self.assertEqual(code, 0, out)
        self.assertEqual({k: tree(v) for k, v in self.profiles.items()}, before)
        self.assertTrue(self.plan.exists())
        self.assertFalse(self.state.exists())
        self.assert_clean_targets()
        code2, out2 = self.preflight(plan=self.dir / 'plan2.json')
        self.assertEqual(out2['fingerprint'], out['fingerprint'])  # empreinte stable

    def test_planned_differences(self):
        code, _ = self.preflight()
        self.assertEqual(code, 0)
        plan = self.plan_doc()
        expected = {}
        for rel in sorted(set(self.prev) | set(self.new)):
            if rel not in self.prev:
                expected[rel] = 'create'
            elif rel not in self.new:
                expected[rel] = 'remove'
            elif self.prev[rel]['sha256'] != self.new[rel]['sha256']:
                expected[rel] = 'replace'
            else:
                expected[rel] = 'unchanged'
        for rel in UNKNOWN:
            expected[rel] = 'preserve-unknown'
        self.assertEqual(expected[WAVE], 'remove')
        self.assertEqual(expected['rc-coordinate-development/references/program-contract.md'], 'create')
        self.assertEqual(expected['rc-coordinate-development/scripts/check_wave.py'], 'unchanged')
        self.assertEqual(expected['rc-prepare-supervisor/SKILL.md'], 'replace')
        for t in plan['targets']:
            self.assertEqual(t['status'], 'ok')
            got = {f['path']: f['decision'] for s in t['skills'] for f in s['files']}
            self.assertEqual(got, expected)
            self.assertNotIn('autre-skill/SKILL.md', t['observed'])
        self.assertEqual(len(plan['actions']), 2 * sum(v in ('create', 'replace', 'remove') for v in expected.values()))
        self.assertFalse(plan['blocked'])

    def test_customization_conflict_blocks_only_that_skill(self):
        custom = self.targets[1] / 'rc-prepare-supervisor' / 'SKILL.md'
        custom.write_bytes(custom.read_bytes() + b'\n<!-- personnalisation locale -->\n')
        code, out = self.preflight()
        self.assertEqual(code, 2)
        claude = out['targets'][1]
        self.assertEqual(claude['skills']['rc-prepare-supervisor'], 'conflict')
        self.assertEqual(claude['conflicts'], ['rc-prepare-supervisor/SKILL.md'])
        self.assertEqual(claude['skills']['rc-coordinate-development'], 'update')
        before = {k: tree(v) for k, v in self.profiles.items()}
        code, _ = self.apply()
        self.assertEqual(code, 2)  # bloqué sans accord explicite
        self.assertEqual({k: tree(v) for k, v in self.profiles.items()}, before)
        self.assertFalse(self.state.exists())
        sup_before = {k: v for k, v in contents(self.targets[1])[0].items() if k.startswith('rc-prepare-supervisor/')}
        code, out = self.apply('--allow-blocked')
        self.assertEqual(code, 0, out)
        self.assert_new(self.targets[0])
        self.assert_new(self.targets[1], ('rc-coordinate-development', 'rc-prepare-socle-prompts'))
        sup_after = {k: v for k, v in contents(self.targets[1])[0].items() if k.startswith('rc-prepare-supervisor/')}
        self.assertEqual(sup_after, sup_before)  # aucun écrasement
        self.assertIn(b'personnalisation locale', custom.read_bytes())

    def test_unexpected_previous_version_refused(self):
        (self.targets[0] / 'rc-prepare-supervisor' / 'references' / 'supervisor-template.md').unlink()
        code, out = self.preflight()
        self.assertEqual(code, 2)
        self.assertEqual(out['targets'][0]['status'], 'refused')
        self.assertTrue(any('absents' in r for r in out['targets'][0]['reasons']))
        self.assertEqual(out['targets'][1]['status'], 'ok')
        plan = self.plan_doc()
        self.assertEqual([a for a in plan['actions'] if a['target'] == 0], [])
        codex_before = tree(self.profiles['codex'])
        code, _ = self.apply('--allow-blocked')
        self.assertEqual(code, 0)
        self.assertEqual(tree(self.profiles['codex']), codex_before)
        self.assert_new(self.targets[1])

    def test_mixed_version_refused(self):
        rel = 'rc-prepare-socle-prompts/SKILL.md'
        (self.targets[1] / rel).write_bytes((NEW_PKG / rel).read_bytes())
        (self.targets[1] / 'rc-coordinate-development/references/program-contract.md').write_bytes(b'x')
        code, out = self.preflight()
        self.assertEqual(code, 2)
        self.assertEqual(out['targets'][1]['status'], 'refused')

    def test_profile_already_new_is_unchanged(self):
        self.build_profile(self.targets[1], NEW_PKG)
        code, out = self.preflight()
        self.assertEqual(code, 0, out)
        self.assertEqual(set(out['targets'][1]['skills'].values()), {'already-new'})
        plan = self.plan_doc()
        self.assertEqual([a for a in plan['actions'] if a['target'] == 1], [])
        claude_before = tree(self.profiles['claude'])
        code, _ = self.apply()
        self.assertEqual(code, 0)
        self.assertEqual(tree(self.profiles['claude']), claude_before)
        self.assert_new(self.targets[0])


class ApplyTests(Base):
    def test_apply_publishes_and_preserves_unknown(self):
        self.preflight()
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        for t in self.targets:
            self.assert_new(t)
        self.assert_unknown_and_outside_intact()
        self.assert_clean_targets()
        events = self.journal()
        backups = self.state / self.plan_doc()['plan_id'] / 'backups'
        self.assertEqual(sha((backups / 'T0' / WAVE).read_bytes()), self.prev[WAVE]['sha256'])
        self.assertEqual(sum(e['event'] == 'verified' for e in events), len(self.plan_doc()['actions']))

    def test_verify_rereads_published_bytes(self):
        self.preflight()
        self.apply()
        before = {k: tree(v) for k, v in self.profiles.items()}
        code, rep = self.run_cli('verify', '--plan', self.plan)
        self.assertEqual(code, 0, rep)
        self.assertTrue(all(t['checked'] > 0 and not t['mismatches'] for t in rep['targets']))
        self.assertEqual({k: tree(v) for k, v in self.profiles.items()}, before)  # lecture seule
        tampered = self.targets[1] / 'rc-prepare-supervisor' / 'SKILL.md'
        tampered.write_bytes(b'altere')
        code, rep = self.run_cli('verify', '--plan', self.plan)
        self.assertEqual(code, 1)
        self.assertEqual([m['path'] for m in rep['targets'][1]['mismatches']], ['rc-prepare-supervisor/SKILL.md'])

    def test_stale_plan_refused(self):
        self.preflight()
        (self.targets[0] / 'rc-coordinate-development' / 'notes-locales.md').write_bytes(b'change apres preflight\n')
        before = {k: tree(v) for k, v in self.profiles.items()}
        code, out = self.apply()
        self.assertEqual(code, 3, out)
        self.assertIn('périmé', out['error'])
        self.assertEqual({k: tree(v) for k, v in self.profiles.items()}, before)
        self.assertFalse(self.state.exists())

    def test_tampered_plan_refused(self):
        self.preflight()
        plan = self.plan_doc()
        plan['actions'][0]['after'] = '0' * 64
        self.plan.write_text(json.dumps(plan), encoding='utf-8')
        code, out = self.apply()
        self.assertEqual(code, 1)
        self.assertIn('altéré', out['error'])

    def test_partial_failure_then_resume(self):
        self.preflight()
        real_swap = rc_update._swap
        calls = []

        def failing_swap(tmp, dest, exclusive):
            if self.state in Path(dest).parents:  # écritures d'état et de sauvegarde : non comptées
                return real_swap(tmp, dest, exclusive)
            calls.append(dest)
            if len(calls) == 4:
                raise OSError('panne injectée par le test')
            return real_swap(tmp, dest, exclusive)

        # Arrêt brutal simulé : le nettoyage final du temporaire n'a pas lieu.
        with mock.patch.object(rc_update, '_swap', failing_swap),                 mock.patch.object(rc_update, '_discard_tmp', lambda *a: False, create=True):
            code, out = self.apply()
        self.assertEqual(code, 1)
        self.assertIn('panne injectée', out['error'])
        sid = self.plan_doc()['plan_id']
        left = [Path(d, n) for t in self.targets for d, _, ns in os.walk(t) for n in ns
                if n.startswith(rc_update.TMP_PREFIX)]
        self.assertEqual(len(left), 1, left)  # le temporaire consigné de l'étape interrompue
        self.assertTrue(left[0].name.startswith(f'{rc_update.TMP_PREFIX}{sid}-'))
        status = json.loads((self.state / sid / 'status.json').read_text(encoding='utf-8'))
        self.assertEqual(status['status'], 'partial')
        done = [e['step'] for e in self.journal() if e['event'] == 'verified']
        self.assertEqual(len(done), 3)
        mtimes = {s: os.stat(self.targets[0] / s.split(':', 2)[2]).st_mtime_ns for s in done}
        self.assertEqual(self.apply()[0], 1)  # pas de seconde application du même plan
        code, _ = self.preflight(plan=self.dir / 'plan-apres-panne.json')
        self.assertEqual(code, 2)  # profil à mi-chemin refusé par un nouveau préflight
        code, out = self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 0, out)
        self.assertEqual(out['cleaned_temps'], [str(left[0])])
        for t in self.targets:
            self.assert_new(t)
        self.assert_unknown_and_outside_intact()
        self.assert_clean_targets()
        for s, m in mtimes.items():
            self.assertEqual(os.stat(self.targets[0] / s.split(':', 2)[2]).st_mtime_ns, m, s)
        events = self.journal()
        for s in done:
            self.assertEqual(sum(e['event'] == 'written' and e['step'] == s for e in events), 1, s)
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)

    def test_crash_between_write_and_journal_then_resume(self):
        self.preflight()
        target_step = self.plan_doc()['actions'][1]['id']
        real_append = rc_update.Journal.append

        def failing_append(journal, event, step=None, **data):
            if event == 'written' and step == target_step:
                raise OSError('arrêt simulé après publication')
            return real_append(journal, event, step, **data)

        with mock.patch.object(rc_update.Journal, 'append', failing_append):
            self.assertEqual(self.apply()[0], 1)
        code, out = self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 0, out)
        events = [e for e in self.journal() if e['step'] == target_step]
        self.assertEqual([e['event'] for e in events if e['event'] in ('written', 'verified')], ['verified'])
        self.assertEqual(events[-1].get('note'), 'constaté sans réécriture')
        for t in self.targets:
            self.assert_new(t)


class RollbackTests(Base):
    def test_rollback_after_complete(self):
        initial = {k: contents(v) for k, v in self.profiles.items()}
        self.preflight()
        self.assertEqual(self.apply()[0], 0)
        code, out = self.run_main('rollback', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 0, out)
        self.assertEqual({k: contents(v) for k, v in self.profiles.items()}, initial)
        for t in self.targets:
            self.assert_previous(t)
        self.assert_clean_targets()
        self.assertEqual(self.run_cli('verify', '--plan', self.plan, '--expect', 'previous')[0], 0)
        self.assertEqual(self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)[0], 1)

    def test_rollback_after_partial(self):
        initial = {k: contents(v) for k, v in self.profiles.items()}
        self.preflight()
        n = [0]
        real_swap = rc_update._swap

        def failing_swap(tmp, dest, exclusive):
            if self.state in Path(dest).parents:  # écritures d'état et de sauvegarde : non comptées
                return real_swap(tmp, dest, exclusive)
            n[0] += 1
            if n[0] == 13:  # au milieu du second profil
                raise OSError('panne injectée')
            return real_swap(tmp, dest, exclusive)

        with mock.patch.object(rc_update, '_swap', failing_swap):
            self.assertEqual(self.apply()[0], 1)
        self.assert_clean_targets()  # panne ordinaire : le temporaire de l'étape est retiré
        code, out = self.run_main('rollback', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 0, out)
        self.assertEqual({k: contents(v) for k, v in self.profiles.items()}, initial)

    def test_rollback_refuses_after_later_edit(self):
        self.preflight()
        self.apply()
        edited = self.targets[0] / 'rc-coordinate-development' / 'SKILL.md'
        edited.write_bytes(b'edition posterieure a la mise a jour')
        before = {k: tree(v) for k, v in self.profiles.items()}
        code, out = self.run_main('rollback', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 1)
        self.assertEqual({k: tree(v) for k, v in self.profiles.items()}, before)


class GuardTests(Base):
    def test_reparse_point_refused(self):
        if os.name != 'nt':
            self.skipTest('jonction NTFS seulement sous Windows')
        import _winapi
        elsewhere = self.dir / 'ailleurs'
        elsewhere.mkdir()
        link = self.targets[0] / 'rc-coordinate-development' / 'lien'
        _winapi.CreateJunction(str(elsewhere), str(link))
        self.junctions.append(link)
        code, out = self.preflight()
        self.assertEqual(code, 1)
        self.assertIn('réparse', out['error'])
        self.assertFalse(self.plan.exists())

    def test_reparse_target_root_refused(self):
        if os.name != 'nt':
            self.skipTest('jonction NTFS seulement sous Windows')
        import _winapi
        link = self.dir / 'profil-jonction'
        _winapi.CreateJunction(str(self.profiles['claude']), str(link))
        self.junctions.append(link)
        code, out = self.run_main('preflight', '--previous-manifest', OLD_MANIFEST, '--new-package', NEW_PKG,
                                  '--target', link / 'skills', '--plan-out', self.plan)
        self.assertEqual(code, 1)
        self.assertIn('réparse', out['error'])

    def test_escaping_manifest_path_refused(self):
        evil = self.dir / 'manifeste-hostile.json'
        doc = json.loads(OLD_MANIFEST.read_text(encoding='utf-8'))
        doc['files'][0]['path'] = 'rc-coordinate-development\\..\\..\\evil.md'
        evil.write_text(json.dumps(doc), encoding='utf-8')
        code, out = self.run_main('preflight', '--previous-manifest', evil, '--new-package', NEW_PKG,
                                  '--target', self.targets[0], '--plan-out', self.plan)
        self.assertEqual(code, 1)
        self.assertIn('refusé', out['error'])

    def test_state_and_plan_inside_target_refused(self):
        code, out = self.preflight(plan=self.targets[0] / 'plan.json')
        self.assertEqual(code, 1)
        self.assertFalse((self.targets[0] / 'plan.json').exists())
        self.preflight()
        before = {k: tree(v) for k, v in self.profiles.items()}
        code, out = self.run_main('apply', '--plan', self.plan, '--state-dir', self.targets[1] / 'etat')
        self.assertEqual(code, 1)
        self.assertEqual({k: tree(v) for k, v in self.profiles.items()}, before)



class ReviewR2Tests(Base):
    """Scénarios de la pré-revue 2 (R2-05 à R2-07).

    Chaque test test_r20* échoue avec RC_UPDATE_MODULE pointant vers outils/rc_update.py
    d'origine. Les patchs create=True sont sans effet sur l'ancienne version.
    """

    def trees(self):
        return {k: tree(v) for k, v in self.profiles.items()}

    def crash_before_backup_publish(self):
        """Échec du renommage d'une sauvegarde, sans nettoyage final (arrêt brutal simulé)."""
        def guard(real):
            def f(src, dst, *a, **k):
                if 'backups' in Path(dst).parts:
                    raise OSError('arrêt simulé avant publication de la sauvegarde')
                return real(src, dst, *a, **k)
            return f
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(rc_update.os, 'replace', guard(os.replace)))
        stack.enter_context(mock.patch.object(rc_update.os, 'rename', guard(os.rename)))
        stack.enter_context(mock.patch.object(rc_update, '_discard_tmp', lambda *a: False, create=True))
        return stack

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

    # R2-05 -------------------------------------------------------------------------
    def test_r205_backup_tmp_resume(self):
        self.assertEqual(self.preflight()[0], 0)
        with self.crash_before_backup_publish():
            code, out = self.apply()
        self.assertEqual(code, 1, out)
        state = self.state / self.plan_doc()['plan_id']
        left = sorted(state.rglob('*.tmp'))
        self.assertTrue(left, 'le scénario doit laisser un temporaire de sauvegarde')
        code, out = self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(state.rglob('*.tmp')), [])
        self.assertEqual(sorted(out['cleaned_temps']), [str(p) for p in left])
        for t in self.targets:
            self.assert_new(t)
        self.assert_unknown_and_outside_intact()
        self.assert_clean_targets()
        for a in self.plan_doc()['actions']:
            if a['op'] in ('replace', 'remove'):
                bp = state / 'backups' / f"T{a['target']}" / a['path']
                self.assertEqual(sha(bp.read_bytes()), a['before'], a['id'])
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)

    # R2-06 -------------------------------------------------------------------------
    def test_r206_rollback_deletes_nothing(self):
        self.assertEqual(self.preflight()[0], 0)
        self.assertEqual(self.apply()[0], 0)
        pid = self.plan_doc()['plan_id']
        unknown = self.targets[0] / 'rc-coordinate-development' / f'{rc_update.TMP_PREFIX}{pid}-user.tmp'
        unknown.write_bytes(b'fichier inconnu, non cree par la mise a jour')
        (self.targets[0] / 'rc-coordinate-development' / 'SKILL.md').write_bytes(b'personnalisation posterieure')
        before = self.trees()
        code, out = self.run_main('rollback', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 1, out)
        self.assertEqual(self.trees(), before)  # ni suppression ni écriture
        self.assertEqual(unknown.read_bytes(), b'fichier inconnu, non cree par la mise a jour')

    def test_r206_resume_keeps_unlogged_tmp(self):
        self.assertEqual(self.preflight()[0], 0)
        with self.fail_target_swap(2):
            self.assertEqual(self.apply()[0], 1)
        pid = self.plan_doc()['plan_id']
        stray = self.targets[0] / 'rc-coordinate-development' / 'references' / f'{rc_update.TMP_PREFIX}{pid}-1-1.tmp'
        stray.write_bytes(b'non consigne par ce plan')
        before = self.trees()
        code, out = self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 1, out)
        self.assertIn('inattendu', out['error'])
        self.assertEqual(self.trees(), before)
        stray.unlink()  # décision humaine : le fichier est retiré à la main
        code, out = self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 0, out)
        self.assertEqual(out['cleaned_temps'], [])

    def test_rollback_cleans_logged_tmp_only(self):
        initial = {k: contents(v) for k, v in self.profiles.items()}
        self.assertEqual(self.preflight()[0], 0)
        with self.fail_target_swap(6), \
                mock.patch.object(rc_update, '_discard_tmp', lambda *a: False, create=True):
            self.assertEqual(self.apply()[0], 1)
        left = [str(Path(d, n)) for t in self.targets for d, _, ns in os.walk(t) for n in ns
                if n.startswith(rc_update.TMP_PREFIX)]
        self.assertEqual(len(left), 1)
        code, out = self.run_main('rollback', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 0, out)
        self.assertEqual(out['cleaned_temps'], left)
        self.assertEqual({k: contents(v) for k, v in self.profiles.items()}, initial)

    # R2-07 -------------------------------------------------------------------------
    def test_r207_preflight_hardlink_tmp(self):
        target = self.targets[0] / 'rc-coordinate-development' / 'SKILL.md'
        data = target.read_bytes()
        alias = Path(str(self.plan) + '.tmp')
        os.link(target, alias)
        before = self.trees()
        code, out = self.preflight()
        self.assertEqual(code, 0, out)
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(alias.read_bytes(), data)
        self.assertEqual(self.trees(), before)
        rc_update.load_plan(self.plan)

    def test_r207_plan_out_exists_refused(self):
        target = self.targets[0] / 'rc-coordinate-development' / 'SKILL.md'
        data = target.read_bytes()
        self.plan.write_bytes(b'plan anterieur a conserver')
        code, out = self.preflight()
        self.assertEqual(code, 1, out)
        self.assertIn('déjà présente', out['error'])
        self.assertEqual(self.plan.read_bytes(), b'plan anterieur a conserver')
        self.plan.unlink()
        os.link(target, self.plan)
        before = self.trees()
        code, out = self.preflight()
        self.assertEqual(code, 1, out)
        self.assertIn('Lien physique', out['error'])
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(self.trees(), before)

    def test_r207_tmp_collision_refused(self):
        target = self.targets[0] / 'rc-coordinate-development' / 'SKILL.md'
        data = target.read_bytes()
        os.link(target, self.dir / '.plan.json.fixe.tmp')
        before = self.trees()
        with mock.patch.object(rc_update, '_token', lambda: 'fixe', create=True):
            code, out = self.preflight()
        self.assertEqual(code, 1, out)
        self.assertIn('préexistante', out['error'])
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(self.trees(), before)
        self.assertFalse(self.plan.exists())

    def test_r207_journal_hardlink_refused(self):
        self.assertEqual(self.preflight()[0], 0)
        with self.fail_target_swap(2):
            self.assertEqual(self.apply()[0], 1)
        journal = self.state / self.plan_doc()['plan_id'] / 'journal.jsonl'
        victim = self.dir / 'victime.jsonl'
        victim.write_bytes(journal.read_bytes())
        journal.unlink()
        os.link(victim, journal)
        data, before = victim.read_bytes(), self.trees()
        code, out = self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 1, out)
        self.assertIn('Lien physique', out['error'])
        self.assertEqual(victim.read_bytes(), data)
        self.assertEqual(self.trees(), before)

    def test_status_hardlink_refused(self):
        self.assertEqual(self.preflight()[0], 0)
        with self.fail_target_swap(2):
            self.assertEqual(self.apply()[0], 1)
        status = self.state / self.plan_doc()['plan_id'] / 'status.json'
        victim = self.dir / 'victime.json'
        victim.write_bytes(status.read_bytes())
        status.unlink()
        os.link(victim, status)
        data = victim.read_bytes()
        code, out = self.run_main('resume', '--plan', self.plan, '--state-dir', self.state)
        self.assertEqual(code, 1, out)
        self.assertEqual(victim.read_bytes(), data)

def write_results(result, started, finished, out_path, argv):
    def sha_file(path):
        return sha(Path(path).read_bytes()) if path and Path(path).is_file() else None
    env = {k: os.environ[k] for k in ('RC_UPDATE_LOT', 'RC_UPDATE_PREVIOUS', 'RC_UPDATE_CANDIDATE',
                                      'RC_NEW_PACKAGE', 'RC_UPDATE_FIXTURES', 'RC_UPDATE_MODULE')
           if k in os.environ}
    data = {
        'command': ' '.join(['python', '-B', Path(sys.argv[0]).name, *argv]),
        'cwd': os.getcwd(),
        'started_at': started, 'finished_at': finished,
        'environment': {'python': platform.python_version(), 'implementation': platform.python_implementation(),
                        'os': f'{platform.system()} {platform.release()} ({platform.version()})',
                        'variables': env},
        'inputs': {'module_under_test': str(SCRIPT), 'module_sha256': sha_file(SCRIPT),
                   'test_file_sha256': sha_file(__file__),
                   'previous_manifest': str(OLD_MANIFEST), 'new_package': str(NEW_PKG),
                   'new_manifest': str(NEW_MANIFEST) if NEW_MANIFEST else None,
                   'new_manifest_sha256': sha_file(NEW_MANIFEST),
                   'fixtures_root': str(FIXTURES)},
        'tests_run': result.testsRun,
        'failures': [t.id() for t, _ in result.failures],
        'errors': [t.id() for t, _ in result.errors],
        'skipped': [t.id() for t, _ in result.skipped],
        'result': 'passed' if result.wasSuccessful() else 'failed',
        'fixtures_left': sorted(p.name for p in FIXTURES.iterdir()) if FIXTURES.exists() else None,
    }
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    argv = sys.argv[1:]
    out_path = None
    if '--results-out' in argv:
        out_path = argv[argv.index('--results-out') + 1]
    elif '--write-results' in argv:
        out_path = HERE / 'resultats-tests.json'
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if out_path:
        write_results(result, started, datetime.datetime.now(datetime.timezone.utc).isoformat(), out_path, argv)
    sys.exit(0 if result.wasSuccessful() else 1)
