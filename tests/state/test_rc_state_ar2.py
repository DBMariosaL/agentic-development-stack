"""Corrected properties for AR2-01 and AR2-02 (stack-accept-r2-20261104/rapport.md).

Failures are injected in-process; every recovery command afterwards (resume, reconcile, write, claim, event)
runs in a NEW Python process against the package selected by RC_STATE_PACKAGE. Expected to fail on v5.
"""
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from test_rc_state import OWNER, SCRIPT, Base, program, rc, wave2

OTHER = 'thread:synthetic-other'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cold(*args):
    proc = subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    return proc.returncode, json.loads(proc.stdout)


def journal(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


class AR2_01_InitialClaim(Base):
    def setUp(self):
        super().setUp()
        p = program()
        p['owner'] = None
        self.write(self.program_path, p)

    def claim_with(self, patcher):
        with patcher:
            return self.run_cli('claim', self.program_path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', 0)

    def op(self):
        code, res = cold('resume', self.program_path)
        self.assertEqual(code, 1, res)
        ops = res['uncertain_operations']
        self.assertEqual((len(ops), ops[0]['op_kind'], ops[0]['actor']), (1, 'claim', OWNER))
        return ops[0]

    def test_v6_prepare_records_previous_owner(self):
        """v6-only field (opposability of the claim author); not a v5 defect reproduction."""
        with mock.patch.object(rc.os, 'replace', side_effect=OSError('injected before replace')):
            self.run_cli('claim', self.program_path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', 0)
        self.assertIsNone(self.op()['previous_owner'])

    def test_failure_before_initial_replacement_is_resolved_by_the_claim_author_only(self):
        before = sha(self.program_path)
        code, res = self.claim_with(mock.patch.object(rc.os, 'replace', side_effect=OSError('injected before replace')))
        self.assertEqual(code, 1, res)
        self.assertEqual(sha(self.program_path), before)
        op = self.op()
        self.assertEqual(op['old_sha256'], before)
        code, res = cold('reconcile', self.program_path, '--actor', OTHER, '--op', op['id'], '--evidence', 'x')
        self.assertEqual(code, 1, res)
        self.assertIn('not the owner', res['error'])
        code, res = cold('reconcile', self.program_path, '--actor', OTHER, '--op', op['id'], '--evidence', 'x',
                         '--declare', 'not_committed')
        self.assertEqual(code, 1, res)
        code, res = cold('claim', self.program_path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', 0)
        self.assertEqual(code, 1, res)
        self.assertIn('unresolved state operation', res['error'])
        code, res = cold('reconcile', self.program_path, '--actor', OWNER, '--op', op['id'],
                         '--evidence', 'program.json sha equals old_sha256 of the claim prepare')
        self.assertEqual(code, 0, res)
        self.assertEqual((res['outcome'], res['by_claim_author'], res['declared']), ('not_committed', True, False))
        code, res = cold('resume', self.program_path)
        self.assertEqual((code, res['uncertain_operations']), (0, []))
        code, res = cold('claim', self.program_path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', 0)
        self.assertEqual(code, 0, res)
        doc = json.loads(self.program_path.read_text(encoding='utf-8'))
        self.assertEqual((doc['owner']['ref'], doc['revision']), (OWNER, 1))
        commits = [e for e in journal(self.root / 'journal.jsonl') if e.get('commits') and e.get('kind') == 'claim']
        self.assertEqual(len(commits), 1)

    def test_failure_after_initial_replacement_resolves_committed_without_second_claim(self):
        real = rc.append_journal

        def fail_commit(j, e):
            if e.get('commits'):
                raise OSError('injected after replace')
            return real(j, e)
        code, res = self.claim_with(mock.patch.object(rc, 'append_journal', side_effect=fail_commit))
        self.assertEqual(code, 1, res)
        op = self.op()
        self.assertEqual(sha(self.program_path), op['new_sha256'])
        code, res = cold('reconcile', self.program_path, '--actor', OTHER, '--op', op['id'], '--evidence', 'x')
        self.assertEqual(code, 1, res)
        code, res = cold('reconcile', self.program_path, '--actor', OWNER, '--op', op['id'], '--evidence', 'sha = new')
        self.assertEqual((code, res['outcome']), (0, 'committed'), res)
        code, res = cold('claim', self.program_path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', 0)
        self.assertEqual(code, 1, res)  # no second claim effect
        self.assertIn('revision conflict', res['error'])

    def test_failed_takeover_author_cannot_declare_a_commit_against_the_owner(self):
        p = json.loads(self.program_path.read_text(encoding='utf-8'))
        p['owner'] = {'role': 'pilot', 'ref': OTHER}
        self.write(self.program_path, p)
        with mock.patch.object(rc.os, 'replace', side_effect=OSError('injected before replace')):
            self.run_cli('claim', self.program_path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', 0,
                         '--takeover', '--evidence', 'synthetic stop of the previous owner')
        code, res = cold('resume', self.program_path)
        op = res['uncertain_operations'][0]
        p = json.loads(self.program_path.read_text(encoding='utf-8'))
        p['status_reason'] = 'edited outside the tool'
        self.write(self.program_path, p)
        code, res = cold('reconcile', self.program_path, '--actor', OWNER, '--op', op['id'], '--evidence', 'x',
                         '--declare', 'committed')
        self.assertEqual(code, 1, res)
        self.assertIn('only the owner', res['error'])


class AR2_02_Attachment(Base):
    """Wave produced by a real v1 -> v2 migration (program_ref null), with pre-existing local and shared journals."""

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
        self.ok('migrate', source, self.wave_path)
        self.local_j = self.wave_path.parent / 'journal.jsonl'
        self.shared_j = self.root / 'journal.jsonl'
        # local journal: an event received and applied while the wave was detached
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'local-done', '--kind', 'completion')
        self.ok('ack', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--id', 'local-done')
        # shared journal: an ordinary program write
        self.ok('write', self.program_path, '--actor', OWNER, '--expect-revision', 0,
                '--ops', json.dumps([{'op': 'set', 'path': 'status_reason', 'value': 'shared journal exists'}]))
        self.assertTrue(self.local_j.is_file() and self.shared_j.is_file())
        self.attach_ops = json.dumps([{'op': 'set', 'path': 'program_ref', 'value': '../../program.json'}])

    def attach(self, patcher=None):
        args = ['write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', self.attach_ops]
        if patcher is None:
            return self.run_cli(*args)
        with patcher:
            return self.run_cli(*args)

    def assert_blocked_everywhere(self):
        code, res = cold('resume', self.program_path)
        self.assertEqual(code, 1, res)
        self.assertEqual(len(res['uncertain_operations']), 1)
        op = res['uncertain_operations'][0]
        code, res = cold('write', self.wave_path, '--actor', OWNER, '--expect-revision',
                         json.loads(self.wave_path.read_text(encoding='utf-8'))['revision'],
                         '--ops', json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'must be refused'}]))
        self.assertEqual(code, 1, res)
        self.assertIn('unresolved state operation', res['error'])
        return op

    def test_failure_before_replacement(self):
        before = sha(self.wave_path)
        code, res = self.attach(mock.patch.object(rc.os, 'replace', side_effect=OSError('injected before replace')))
        self.assertEqual(code, 1, res)
        self.assertEqual(sha(self.wave_path), before)
        self.assertTrue(any(e.get('kind') == 'prepare' for e in journal(self.local_j)))
        self.assertTrue(any(e.get('kind') == 'prepare' for e in journal(self.shared_j)))
        op = self.assert_blocked_everywhere()
        code, res = cold('reconcile', self.wave_path, '--actor', OTHER, '--op', op['id'], '--evidence', 'x')
        self.assertEqual(code, 1, res)
        code, res = cold('reconcile', self.wave_path, '--actor', OWNER, '--op', op['id'], '--evidence', 'sha = old')
        self.assertEqual((code, res['outcome']), (0, 'not_committed'), res)
        resolved_in = res.get('resolved_in')
        code, res = cold('resume', self.program_path)
        self.assertEqual((code, res['uncertain_operations']), (0, []), res)
        code, res = cold('write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', self.attach_ops)
        self.assertEqual(code, 0, res)
        code, res = cold('event', self.wave_path, '--actor', OWNER, '--id', 'local-done', '--kind', 'completion')
        self.assertEqual(res['classification'], 'duplicate')  # protection carried into the shared journal
        self.assertEqual(len(resolved_in or []), 1)  # v7 structure: single copy, in the local journal

    def test_failure_after_replacement(self):
        real = rc.append_journal

        def fail_commit(j, e):
            if e.get('commits'):
                raise OSError('injected after replace')
            return real(j, e)
        code, res = self.attach(mock.patch.object(rc, 'append_journal', side_effect=fail_commit))
        self.assertEqual(code, 1, res)
        self.assertEqual(json.loads(self.wave_path.read_text(encoding='utf-8'))['program_ref'], '../../program.json')
        op = self.assert_blocked_everywhere()
        code, res = cold('reconcile', self.wave_path, '--actor', OWNER, '--op', op['id'], '--evidence', 'sha = new')
        self.assertEqual((code, res['outcome']), (0, 'committed'), res)
        resolved_in = res.get('resolved_in')
        code, res = cold('resume', self.program_path)
        self.assertEqual((code, res['uncertain_operations']), (0, []), res)
        code, res = cold('write', self.wave_path, '--actor', OWNER, '--expect-revision', 2,
                         '--ops', json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'after recovery'}]))
        self.assertEqual(code, 0, res)
        code, res = cold('event', self.wave_path, '--actor', OWNER, '--id', 'local-done', '--kind', 'completion')
        self.assertEqual(res['classification'], 'duplicate')
        self.assertEqual(len(resolved_in or []), 1)  # v7 structure: single copy, in the local journal

    def test_prepare_recorded_in_local_journal_only(self):
        """v7 structure: the attachment prepares only in the local journal (the v6 'second prepare' window is gone)."""
        real = rc.append_journal
        prepares = []

        def record(j, e):
            if e.get('kind') == 'prepare':
                prepares.append(Path(j).resolve())
            return real(j, e)
        code, res = self.attach(mock.patch.object(rc, 'append_journal', side_effect=record))
        self.assertEqual(code, 0, res)
        self.assertEqual(prepares, [self.local_j.resolve()])
        self.assertFalse(any(e.get('kind') == 'prepare' and e.get('wave') == 'waves/a/wave.json' for e in journal(self.shared_j)))
        code, res = cold('resume', self.program_path)
        self.assertEqual((code, res['uncertain_operations']), (0, []), res)

    def test_attach_refused_while_a_local_event_is_unsettled_then_preserved(self):
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'local-open', '--kind', 'completion')
        code, res = self.attach()
        self.assertEqual(code, 1, res)
        self.assertIn('local events not yet applied', res['error'])
        self.ok('ack', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--id', 'local-open')
        self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 2, '--ops', self.attach_ops)
        statuses = rc._event_status(journal(self.shared_j))
        self.assertTrue(statuses['local-open']['applied'] and statuses['local-done']['applied'])
        self.assertEqual(statuses['local-open']['wave'], 'waves/a/wave.json')
        self.refused('immutable', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 3,
                     '--ops', json.dumps([{'op': 'set', 'path': 'program_ref', 'value': None}]))


if __name__ == '__main__':
    unittest.main()
