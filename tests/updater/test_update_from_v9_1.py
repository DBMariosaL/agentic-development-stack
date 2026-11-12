"""Mise à jour d'une installation v9.1 réelle vers le paquet courant, sur profils factices.

Lancer depuis la racine du dépôt :
  python -B tools/check.py                       (avec les autres suites)
  python -B -m unittest tests/updater/test_update_from_v9_1.py

Variables : celles de test_rc_update_v8.py (RC_UPDATE_MODULE, RC_UPDATE_FIXTURES), dont
les aides sont réutilisées.

Référence v9.1 figée et compacte : tests/fixtures/v9.1/manifest.json (manifeste v9.1 octet
pour octet) et, sous tests/fixtures/v9.1/package, les seuls fichiers RC v9.1 absents des
fixtures v9, v8 et v7. Chaque test recompose le paquet v9.1 complet dans son dossier : chaque
fichier est pris dans les fixtures v9.1, v9, v8, v7 ou le paquet courant, seulement si son empreinte est celle
du manifeste v9 ; sinon le test échoue et nomme le fichier à figer. Les attendus sont
calculés depuis manifest.json et package/ du dépôt, jamais écrits en dur.
"""
import sys

sys.dont_write_bytecode = True

import importlib.util  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('rc_update_v8_helpers_for_v9_1', HERE / 'test_rc_update_v8.py')
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)
rc_update, sha, tree, read_manifest = shared.rc_update, shared.sha, shared.tree, shared.read_manifest
RC, DEPS, ALL = shared.RC, shared.DEPS, shared.ALL
NEW_PKG, NEW_MANIFEST = shared.NEW_PKG, shared.NEW_MANIFEST

V91 = shared.ROOT / 'tests' / 'fixtures' / 'v9.1'
V91_MANIFEST = V91 / 'manifest.json'
SOURCES = (V91 / 'package', shared.ROOT / 'tests' / 'fixtures' / 'v9' / 'package',
           shared.ROOT / 'tests' / 'fixtures' / 'v8' / 'package', shared.V7 / 'package', NEW_PKG)


def compose_v91(dest):
    """Paquet v9.1 complet, chaque octet prouvé par le manifeste v9.1."""
    for rel, item in read_manifest(V91_MANIFEST).items():
        for src in SOURCES:
            path = src.joinpath(*rel.split('/'))
            if path.is_file() and sha(path.read_bytes()) == item['sha256']:
                out = dest.joinpath(*rel.split('/'))
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(path.read_bytes())
                break
        else:
            raise AssertionError(f'octets v9.1 introuvables pour {rel} : les figer sous tests/fixtures/v9.1/package')
    return dest


class FromV91Base(shared.Base):
    def setUp(self):
        super().setUp()
        self.v91_pkg = compose_v91(self.dir / 'v9.1')
        for t in self.targets:
            self.build_profile(t, self.v91_pkg)
        self.old = read_manifest(V91_MANIFEST)
        self.changes = {}
        for rel in sorted(set(self.old) | set(self.new)):
            if rel not in self.old:
                self.changes[rel] = 'create'
            elif rel not in self.new:
                self.changes[rel] = 'remove'
            elif self.old[rel]['sha256'] != self.new[rel]['sha256']:
                self.changes[rel] = 'replace'
        self.assertTrue(self.changes, 'manifest.json décrit encore les octets v9.1 : aucune mise à jour à éprouver')

    def preflight(self, **kw):
        kw.setdefault('prev', V91_MANIFEST)
        return super().preflight(**kw)

    def deps(self):
        return {(i, d): self.sub(t, d) for i, t in enumerate(self.targets) for d in DEPS}


class FromV91Tests(FromV91Base):
    def test_v91_reference_rebuilt_exactly(self):
        doc = json.loads(V91_MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(doc['distribution'], 'rc-core-with-dependencies')
        self.assertEqual(rc_update.manifest_doc(rc_update.compute_manifest(self.v91_pkg)), doc)

    def test_plan_replaces_rc_files_only(self):
        before = self.trees()
        code, out = self.preflight(cli=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.trees(), before)
        self.assertEqual(out['distributions'], {'previous': 'rc-core-with-dependencies',
                                                'new': 'rc-core-with-dependencies'})
        self.assertEqual({r.split('/')[0] for r in self.changes} - set(RC), set(),
                         'une dépendance a changé : la v9.1.1 doit la livrer octet pour octet')
        expected = {r: self.changes.get(r, 'unchanged') for r in set(self.old) | set(self.new)}
        expected.update({rel: 'preserve-unknown' for rel in shared.UNKNOWN})
        changed_skills = {r.split('/')[0] for r in self.changes}
        plan = self.plan_doc()
        for t in plan['targets']:
            self.assertEqual(t['status'], 'ok')
            self.assertEqual({s['name']: s['status'] for s in t['skills']},
                             {s: 'update' if s in changed_skills else 'already-new' for s in ALL})
            self.assertEqual({f['path']: f['decision'] for s in t['skills'] for f in s['files']}, expected)
        self.assertEqual(sorted((a['target'], a['path'], a['op']) for a in plan['actions']),
                         sorted((i, r, op) for i in (0, 1) for r, op in self.changes.items()))
        self.assertFalse(plan['blocked'])

    def test_apply_leaves_dependencies_untouched(self):
        deps = self.deps()
        self.assertEqual(self.preflight()[0], 0)
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        for t in self.targets:
            self.assert_new(t)
            for rel, op in self.changes.items():
                if op == 'remove':
                    self.assertFalse((t / rel).exists(), rel)
        self.assertEqual(self.deps(), deps)  # octets et mtime des dépendances inchangés
        self.assert_foreign_intact()
        self.assert_clean_targets()
        self.assertEqual(self.run_cli('verify', '--plan', self.plan)[0], 0)

    def test_local_edit_conflict_refused(self):
        rel = next(r for r, op in sorted(self.changes.items()) if op == 'replace')
        skill = rel.split('/')[0]
        edited = self.targets[1] / rel
        edited.write_bytes(edited.read_bytes() + b'\n<!-- retouche locale -->\n')
        code, out = self.preflight()
        self.assertEqual(code, 2, out)
        self.assertEqual(out['targets'][1]['skills'][skill], 'conflict')
        self.assertEqual(out['targets'][1]['conflicts'], [rel])
        before = self.trees()
        self.assertEqual(self.apply()[0], 2)  # bloqué sans accord explicite
        self.assertEqual(self.trees(), before)
        self.assertFalse(self.state.exists())
        kept = self.sub(self.targets[1], skill)
        self.assertEqual(self.apply('--allow-blocked')[0], 0)
        self.assertEqual(self.sub(self.targets[1], skill), kept)  # retouche locale conservée
        self.assert_new(self.targets[0])
        self.assert_new(self.targets[1], tuple(s for s in ALL if s != skill))
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)

    def test_interrupt_then_resume(self):
        self.preflight()
        per_target = len(self.plan_doc()['actions']) // 2
        with self.fail_target_swap(per_target + min(2, per_target)), \
                mock.patch.object(rc_update, '_discard_tmp', lambda *a: False):
            self.assertEqual(self.apply()[0], 1)
        left = [p for t in self.targets for p in t.rglob(rc_update.TMP_PREFIX + '*')]
        self.assertEqual(len(left), 1, left)
        done = {e['step'] for e in self.journal() if e['event'] == 'verified'}
        self.assertTrue(per_target <= len(done) < 2 * per_target, done)
        code, out = self.resume()
        self.assertEqual(code, 0, out)
        self.assertEqual(out['cleaned_temps'], [str(left[0])])
        for t in self.targets:
            self.assert_new(t)
        self.assert_foreign_intact()
        self.assert_clean_targets()
        events = self.journal()
        for s in done - {s for s in done if ':remove:' in s}:  # aucune réécriture d'une étape vérifiée
            self.assertEqual(sum(e['event'] == 'written' and e['step'] == s for e in events), 1, s)
        self.assertEqual(self.run_main('verify', '--plan', self.plan)[0], 0)

    def test_rollback_restores_v91_bytes(self):
        initial = self.snapshot()
        self.preflight()
        self.assertEqual(self.apply()[0], 0)
        code, out = self.rollback()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), initial)
        for t in self.targets:
            for rel, item in self.old.items():
                self.assertEqual(sha((t / rel).read_bytes()), item['sha256'], rel)
        self.assert_clean_targets()
        self.assertEqual(self.run_cli('verify', '--plan', self.plan, '--expect', 'previous')[0], 0)

    def test_rollback_after_interrupted_update(self):
        initial = self.snapshot()
        self.preflight()
        with self.fail_target_swap(len(self.plan_doc()['actions']) // 2 + 1):
            self.assertEqual(self.apply()[0], 1)
        self.assertNotEqual(self.snapshot(), initial)
        code, out = self.rollback()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), initial)
        self.assert_clean_targets()


if __name__ == '__main__':
    import unittest
    unittest.main(verbosity=2)
