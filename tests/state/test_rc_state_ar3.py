"""Corrected properties for AR3-01 and AR3-02 (stack-accept-r3-20261104/rapport.md).

Partial journal states are produced by the real v6 module (candidats/v6) or the historical v2 CLI (candidats/v2);
every discovery, refusal and recovery afterwards runs in a NEW Python process with the package selected by
RC_STATE_PACKAGE. No journal or state is edited or deleted to get out of a case. Expected to fail on v6.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from test_rc_state import OWNER, SCRIPT, Base, program, rc, wave2

LOT = Path(__file__).resolve().parents[2]
V6 = LOT / 'tests/fixtures/v6/package/rc-coordinate-development/scripts/rc_state.py'
V2 = LOT / 'tests/fixtures/v2/package/rc-coordinate-development/scripts/rc_state.py'
_spec = importlib.util.spec_from_file_location('rc_state_v6_for_ar3', V6)
v6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v6)


def run(script, *args):
    proc = subprocess.run([sys.executable, '-B', str(script), *map(str, args)], capture_output=True, text=True,
                          encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    return proc.returncode, json.loads(proc.stdout)


def cold(*args):
    return run(SCRIPT, *args)


def journal(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def in_module(module, *args):
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main([str(a) for a in args])
    return code, json.loads(out.getvalue())


class AttachedFixture(Base):
    """Wave migrated from v1 (program_ref null) with pre-existing local and shared journals."""

    def setUp(self):
        super().setUp()
        v1 = wave2()
        for key in ('revision', 'program_ref', 'candidate', 'envelope', 'actors', 'intents'):
            v1.pop(key)
        v1['schema_version'] = 1
        v1['state'].pop('waiting')
        source = self.root / 'v1-wave.json'
        self.write(source, v1)
        self.wave_path.unlink()
        self.assertEqual(cold('migrate', source, self.wave_path)[0], 0)
        self.local_j = self.wave_path.parent / 'journal.jsonl'
        self.shared_j = self.root / 'journal.jsonl'
        self.assertEqual(cold('event', self.wave_path, '--actor', OWNER, '--id', 'local-done', '--kind', 'completion')[0], 0)
        self.assertEqual(cold('ack', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--id', 'local-done')[0], 0)
        self.assertEqual(cold('write', self.program_path, '--actor', OWNER, '--expect-revision', 0, '--ops',
                              json.dumps([{'op': 'set', 'path': 'status_reason', 'value': 'shared exists'}]))[0], 0)
        self.attach_ops = json.dumps([{'op': 'set', 'path': 'program_ref', 'value': '../../program.json'}])

    def revision(self):
        return json.loads(self.wave_path.read_text(encoding='utf-8'))['revision']

    def next_write(self):
        return cold('write', self.wave_path, '--actor', OWNER, '--expect-revision', self.revision(),
                    '--ops', json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'next write probe'}]))

    def recover(self, op_id, expected_outcome):
        """Discovery, refusal, complete CLI exit and repeatability, all in fresh processes."""
        code, res = cold('resume', self.program_path)
        self.assertEqual(code, 1, res)
        self.assertIn(op_id, [op['id'] for op in res['uncertain_operations']])
        code, res = self.next_write()
        self.assertEqual(code, 1, res)
        self.assertIn('unresolved state operation', res['error'])
        code, res = cold('reconcile', self.wave_path, '--actor', 'thread:synthetic-other', '--op', op_id, '--evidence', 'x')
        self.assertEqual(code, 1, res)
        code, res = cold('reconcile', self.wave_path, '--actor', OWNER, '--op', op_id,
                         '--evidence', 'state sha compared with the prepare in every participating journal')
        self.assertEqual((code, res['outcome']), (0, expected_outcome), res)
        size = [len(journal(self.local_j)), len(journal(self.shared_j))]
        code, again = cold('reconcile', self.wave_path, '--actor', OWNER, '--op', op_id, '--evidence', 'repeat')
        self.assertEqual((code, again['already_resolved'], again['outcome']), (0, True, expected_outcome), again)
        self.assertEqual([len(journal(self.local_j)), len(journal(self.shared_j))], size)  # repeat changes nothing
        code, res = cold('resume', self.program_path)
        self.assertEqual((code, res['uncertain_operations']), (0, []), res)
        return res


class AR3_01_PartialStatesFromV6(AttachedFixture):
    def v6_attach(self, failing):
        real = v6.append_journal

        def inject(j, e):
            if failing(Path(j).resolve(), e):
                raise OSError('injected into the v6 attachment')
            return real(j, e)
        with mock.patch.object(v6, 'append_journal', side_effect=inject):
            return in_module(v6, 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', self.attach_ops)

    def test_v6_partial_validation_is_found_blocked_and_completed(self):
        code, res = self.v6_attach(lambda j, e: bool(e.get('commits')) and j == self.local_j.resolve())
        self.assertEqual(code, 1, res)
        self.assertEqual(json.loads(self.wave_path.read_text(encoding='utf-8'))['program_ref'], '../../program.json')
        op = [e for e in journal(self.local_j) if e.get('kind') == 'prepare' and e.get('wave') == 'wave.json'][-1]
        self.assertTrue(any(e.get('commits') == op['id'] for e in journal(self.shared_j)))      # shared closed
        self.assertFalse(any(e.get('commits') == op['id'] for e in journal(self.local_j)))      # local open
        self.recover(op['id'], 'committed')
        self.assertTrue(any(e.get('resolves') == op['id'] and e.get('completes_closure') for e in journal(self.local_j)))
        code, res = self.next_write()
        self.assertEqual(code, 0, res)
        code, res = cold('event', self.wave_path, '--actor', OWNER, '--id', 'local-done', '--kind', 'completion')
        self.assertEqual(res['classification'], 'duplicate')

    def test_v6_partial_reconciliation_is_found_blocked_and_completed(self):
        with mock.patch.object(v6.os, 'replace', side_effect=OSError('injected before v6 replace')):
            code, res = in_module(v6, 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', self.attach_ops)
        self.assertEqual(code, 1, res)
        op = [e for e in journal(self.local_j) if e.get('kind') == 'prepare' and e.get('wave') == 'wave.json'][-1]
        real = v6.append_journal

        def fail_shared(j, e):
            if e.get('kind') == 'resolve' and Path(j).resolve() == self.shared_j.resolve():
                raise OSError('injected on the shared resolution')
            return real(j, e)
        with mock.patch.object(v6, 'append_journal', side_effect=fail_shared):
            code, res = in_module(v6, 'reconcile', self.wave_path, '--actor', OWNER, '--op', op['id'], '--evidence', 'v6')
        self.assertEqual(code, 1, res)
        self.assertTrue(any(e.get('resolves') == op['id'] for e in journal(self.local_j)))       # local closed
        self.assertFalse(any(e.get('resolves') == op['id'] for e in journal(self.shared_j)))     # shared open
        self.assertIsNone(json.loads(self.wave_path.read_text(encoding='utf-8'))['program_ref'])
        code, res = cold('write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', self.attach_ops)
        self.assertEqual(code, 1, res)
        self.recover(op['id'], 'not_committed')
        code, res = cold('write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', self.attach_ops)
        self.assertEqual(code, 0, res)
        code, res = cold('event', self.wave_path, '--actor', OWNER, '--id', 'local-done', '--kind', 'completion')
        self.assertEqual(res['classification'], 'duplicate')

    def test_recorded_closure_imposes_its_outcome(self):
        self.v6_attach(lambda j, e: bool(e.get('commits')) and j == self.local_j.resolve())
        op = [e for e in journal(self.local_j) if e.get('kind') == 'prepare' and e.get('wave') == 'wave.json'][-1]
        code, res = cold('reconcile', self.wave_path, '--actor', OWNER, '--op', op['id'], '--evidence', 'x',
                         '--declare', 'not_committed')
        self.assertEqual(code, 1, res)
        self.assertIn('contrary declaration', res['error'])


class AR3_01_V7States(AttachedFixture):
    """States C and D of the v7 table, single copy in the local journal."""

    def attach_with(self, patcher):
        with patcher:
            return self.run_cli('write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', self.attach_ops)

    def test_state_c_prepare_before_replacement(self):
        code, res = self.attach_with(mock.patch.object(rc.os, 'replace', side_effect=OSError('injected')))
        self.assertEqual(code, 1, res)
        op = [e for e in journal(self.local_j) if e.get('kind') == 'prepare' and e.get('wave') == 'wave.json'][-1]
        self.assertEqual(op['journals'], [str(self.local_j.resolve())])
        self.recover(op['id'], 'not_committed')
        self.assertEqual(cold('write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', self.attach_ops)[0], 0)

    def test_state_d_replaced_without_validation(self):
        real = rc.append_journal

        def fail_commit(j, e):
            if e.get('commits'):
                raise OSError('injected')
            return real(j, e)
        code, res = self.attach_with(mock.patch.object(rc, 'append_journal', side_effect=fail_commit))
        self.assertEqual(code, 1, res)
        op = [e for e in journal(self.local_j) if e.get('kind') == 'prepare' and e.get('wave') == 'wave.json'][-1]
        self.recover(op['id'], 'committed')
        self.assertEqual(self.next_write()[0], 0)


class AR3_02_LegacyAttribution(Base):
    """A (wave.json, migrated) and B (other.json) share a directory and its local journal; legacy-B is received
    and acknowledged on B by the historical v2 CLI."""

    def setUp(self):
        super().setUp()
        d = self.wave_path.parent
        self.a, self.b = d / 'wave.json', d / 'other.json'
        v1 = wave2()
        for key in ('revision', 'program_ref', 'candidate', 'envelope', 'actors', 'intents'):
            v1.pop(key)
        v1['schema_version'] = 1
        v1['state'].pop('waiting')
        source = self.root / 'v1-wave.json'
        self.write(source, v1)
        self.a.unlink()
        self.assertEqual(cold('migrate', source, self.a)[0], 0)
        b = wave2()
        b['program_ref'] = None
        self.write(self.b, b)
        p = program()
        p['outcomes'][1].update(depends_on=[], status='admitted', state_ref='waves/a/other.json')
        self.write(self.program_path, p)
        self.assertEqual(run(V2, 'event', self.b, '--actor', OWNER, '--id', 'legacy-B', '--kind', 'completion')[0], 0)
        self.assertEqual(run(V2, 'ack', self.b, '--actor', OWNER, '--expect-revision', 0, '--id', 'legacy-B')[0], 0)
        self.local_j = d / 'journal.jsonl'
        self.shared_j = self.root / 'journal.jsonl'
        self.original = self.local_j.read_bytes()
        self.ops = json.dumps([{'op': 'set', 'path': 'program_ref', 'value': '../../program.json'}])

    def test_attaching_a_does_not_take_b_legacy_event(self):
        self.assertEqual(cold('check', self.program_path)[0], 0)
        code, res = cold('write', self.a, '--actor', OWNER, '--expect-revision', 0, '--ops', self.ops)
        self.assertEqual(code, 0, res)
        self.assertNotIn('legacy-B', rc._event_status(journal(self.shared_j)))
        code, res = cold('event', self.a, '--actor', OWNER, '--id', 'legacy-B', '--attach-legacy', '--kind', 'completion',
                         '--evidence', 'wrong file on purpose')
        self.assertEqual(code, 1, res)
        code, res = cold('event', self.b, '--actor', OWNER, '--id', 'legacy-B', '--kind', 'completion')
        self.assertEqual(res['classification'], 'legacy-unattached')
        code, res = cold('write', self.b, '--actor', OWNER, '--expect-revision', 1, '--ops', self.ops)
        self.assertEqual(code, 1, res)
        self.assertIn('legacy-B', res['error'])
        code, res = cold('event', self.b, '--actor', OWNER, '--id', 'legacy-B', '--kind', 'completion', '--attach-legacy',
                         '--evidence', 'v2 receipt file=other.json, acknowledged on other.json')
        self.assertEqual((code, res['classification']), (0, 'attached'), res)
        code, res = cold('write', self.b, '--actor', OWNER, '--expect-revision', 1, '--ops', self.ops)
        self.assertEqual(code, 0, res)
        status = rc._event_status(journal(self.shared_j))['legacy-B']
        self.assertEqual((status['wave'], status['applied']), ('waves/a/other.json', True))
        self.assertEqual(cold('event', self.b, '--actor', OWNER, '--id', 'legacy-B', '--kind', 'completion')[1]['classification'],
                         'duplicate')
        code, res = cold('event', self.a, '--actor', OWNER, '--id', 'legacy-B', '--kind', 'completion')
        self.assertEqual(code, 1, res)
        self.assertIn('belongs to waves/a/other.json', res['error'])
        self.assertTrue(self.local_j.read_bytes().startswith(self.original))

    def test_legacy_receipt_of_the_file_itself_requires_sourced_attachment(self):
        self.assertEqual(run(V2, 'event', self.a, '--actor', OWNER, '--id', 'legacy-A', '--kind', 'completion')[0], 0)
        self.assertEqual(run(V2, 'ack', self.a, '--actor', OWNER, '--expect-revision', 0, '--id', 'legacy-A')[0], 0)
        code, res = cold('write', self.a, '--actor', OWNER, '--expect-revision', 1, '--ops', self.ops)
        self.assertEqual(code, 1, res)
        self.assertIn('legacy-A', res['error'])
        self.assertNotIn('legacy-B', res['error'])
        self.assertEqual(cold('event', self.a, '--actor', OWNER, '--id', 'legacy-A', '--kind', 'completion', '--attach-legacy',
                              '--evidence', 'v2 receipt file=wave.json')[0], 0)
        code, res = cold('write', self.a, '--actor', OWNER, '--expect-revision', 1, '--ops', self.ops)
        self.assertEqual(code, 0, res)
        self.assertEqual(cold('event', self.a, '--actor', OWNER, '--id', 'legacy-A', '--kind', 'completion')[1]['classification'],
                         'duplicate')


if __name__ == '__main__':
    unittest.main()
