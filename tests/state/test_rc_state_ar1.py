"""Corrected properties for the acceptance findings AR1-01 to AR1-04 (stack-accept-r1-20261104/rapport.md).

Run against a package with RC_STATE_PACKAGE; these tests are expected to fail on v4 and pass on v5.
All fixtures are synthetic files under tests/_fixtures.
"""
import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from test_rc_state import OWNER, Base, program, rc, wave2

LAUNCHER = 'thread:synthetic-launcher'
SUPERVISOR = 'thread:synthetic-supervisor'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class AR1Base(Base):
    def wave(self):
        return json.loads(self.wave_path.read_text(encoding='utf-8'))

    def journal(self):
        path = self.root / 'journal.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def set_next(self, rev, value='next'):
        return self.run_cli('write', self.wave_path, '--actor', OWNER, '--expect-revision', rev,
                            '--ops', json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': value}]))


class AR1_01_ThirdPartyFiles(AR1Base):
    def test_preexisting_tmp_hardlink_is_neither_used_nor_altered(self):
        victim = self.root / 'foreign.txt'
        victim.write_bytes(b'foreign bytes to preserve')
        before = sha(victim)
        tmp = Path(str(self.wave_path) + '.tmp')
        os.link(victim, tmp)
        code, result = self.set_next(0)
        self.assertEqual(code, 0, result)
        self.assertEqual(sha(victim), before)
        self.assertEqual(sha(tmp), before)  # unknown pre-existing entry preserved
        self.assertEqual(self.wave()['state']['next_action'], 'next')
        leftovers = [p.name for p in self.wave_path.parent.iterdir() if p.name.endswith('.tmp') and p != tmp]
        self.assertEqual(leftovers, [])

    def test_hardlinked_journal_is_refused_before_any_state_change(self):
        victim = self.root / 'foreign.jsonl'
        victim.write_bytes(b'')
        before = sha(victim)
        os.link(victim, self.root / 'journal.jsonl')
        code, result = self.set_next(0)
        self.assertEqual(code, 1, result)
        self.assertIn('single link', result['error'])
        self.assertEqual(sha(victim), before)
        self.assertEqual(self.wave()['revision'], 0)
        self.assertEqual([p.name for p in self.wave_path.parent.iterdir() if p.name.endswith('.tmp')], [])

    def test_hardlinked_state_file_keeps_third_party_bytes(self):
        victim = self.root / 'other-copy.json'
        os.link(self.wave_path, victim)
        before = sha(victim)
        code, result = self.set_next(0)
        self.assertEqual(code, 0, result)
        self.assertEqual(sha(victim), before)

    def test_hardlinked_event_journal_refused(self):
        victim = self.root / 'foreign.jsonl'
        victim.write_bytes(b'')  # empty, hence a readable journal: only the link check can protect it
        os.link(victim, self.root / 'journal.jsonl')
        code, result = self.run_cli('event', self.wave_path, '--actor', OWNER, '--id', 'e1', '--kind', 'completion')
        self.assertEqual(code, 1, result)
        self.assertEqual(victim.read_bytes(), b'')

    def test_junction_in_ancestors_is_refused(self):
        link = self.root / 'via-junction'
        made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(self.wave_path.parent)],
                              capture_output=True, text=True)
        if made.returncode != 0:
            self.skipTest('junction creation unavailable: ' + made.stderr.strip())
        try:
            code, result = self.run_cli('write', link / 'wave.json', '--actor', OWNER, '--expect-revision', 0,
                                        '--ops', json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'x'}]))
            self.assertEqual(code, 1, result)
            self.assertIn('reparse', result['error'])
            self.assertEqual(self.wave()['revision'], 0)
        finally:
            os.rmdir(link)


class AR1_02_UncertainApplication(AR1Base):
    OPS = [{'op': 'append', 'path': 'decisions', 'value': 'effect of event-1'}]

    def receive(self):
        code, result = self.run_cli('event', self.wave_path, '--actor', OWNER, '--id', 'event-1', '--kind', 'completion')
        self.assertEqual((code, result['classification']), (0, 'new'))

    def apply(self, rev):
        return self.run_cli('write', self.wave_path, '--actor', OWNER, '--expect-revision', rev,
                            '--ops', json.dumps(self.OPS), '--applies-event', 'event-1')

    def fail_after_replace(self):
        """Fail every journal append except 'prepare': the state replacement happens, the commit line does not."""
        real = rc.append_journal

        def append(jpath, entry):
            if entry.get('kind') != 'prepare':
                raise OSError('injected failure after state replacement')
            return real(jpath, entry)
        return mock.patch.object(rc, 'append_journal', side_effect=append)

    def uncertain_op(self):
        code, result = self.run_cli('resume', self.program_path)
        return code, result

    def test_cold_resume_exposes_uncertain_application_and_blocks_replay(self):
        self.receive()
        before = sha(self.wave_path)
        with self.fail_after_replace():
            code, result = self.apply(0)
        self.assertEqual(code, 1, result)
        self.assertNotEqual(sha(self.wave_path), before)            # state really replaced
        self.assertEqual(self.wave()['revision'], 1)
        self.assertEqual(self.wave()['decisions'].count('effect of event-1'), 1)
        self.assertFalse(any(e.get('commits') for e in self.journal()))  # commit line really missing
        code, cold = self.uncertain_op()                              # fresh process view, no error in memory
        self.assertEqual(code, 1)
        self.assertEqual([e['id'] for e in cold['unapplied_events']], [])
        self.assertEqual(len(cold['uncertain_operations']), 1)
        self.assertEqual(cold['uncertain_operations'][0]['pending_applies_event'], 'event-1')
        code, again = self.run_cli('event', self.wave_path, '--actor', OWNER, '--id', 'event-1', '--kind', 'completion')
        self.assertEqual(again['classification'], 'uncertain')
        self.refused('unresolved state operation', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 1,
                     '--ops', json.dumps(self.OPS), '--applies-event', 'event-1')
        self.refused('unresolved state operation', 'ack', self.wave_path, '--actor', OWNER, '--expect-revision', 1,
                     '--id', 'event-1')
        op = cold['uncertain_operations'][0]['id']
        result = self.ok('reconcile', self.wave_path, '--actor', OWNER, '--op', op,
                         '--evidence', 'state sha compared with prepare entry')
        self.assertEqual((result['outcome'], result['declared'], result['event_marked_applied']),
                         ('committed', False, 'event-1'))
        code, after = self.uncertain_op()
        self.assertEqual((code, after['uncertain_operations'], after['unapplied_events']), (0, [], []))
        code, again = self.run_cli('event', self.wave_path, '--actor', OWNER, '--id', 'event-1', '--kind', 'completion')
        self.assertEqual(again['classification'], 'duplicate')
        self.refused('already applied', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 1,
                     '--ops', json.dumps(self.OPS), '--applies-event', 'event-1')
        self.assertEqual(self.wave()['decisions'].count('effect of event-1'), 1)

    def test_crash_before_replacement_resolves_as_not_committed(self):
        self.receive()
        before = sha(self.wave_path)
        with mock.patch.object(rc.os, 'replace', side_effect=OSError('injected failure before replacement')):
            code, result = self.apply(0)
        self.assertEqual(code, 1, result)
        self.assertEqual(sha(self.wave_path), before)
        code, cold = self.uncertain_op()
        op = cold['uncertain_operations'][0]
        own_tmp = self.wave_path.parent / op['tmp']
        self.assertTrue(own_tmp.is_file())
        result = self.ok('reconcile', self.wave_path, '--actor', OWNER, '--op', op['id'], '--evidence', 'sha check')
        self.assertEqual((result['outcome'], result['event_marked_applied']), ('not_committed', None))
        self.assertEqual(result['removed_own_temporary'], own_tmp.name)
        code, after = self.uncertain_op()
        self.assertEqual([e['id'] for e in after['unapplied_events']], ['event-1'])
        self.ok(*['write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', json.dumps(self.OPS),
                  '--applies-event', 'event-1'])
        self.assertEqual(self.wave()['decisions'].count('effect of event-1'), 1)

    def test_unestablished_effect_needs_sourced_declaration(self):
        self.receive()
        with self.fail_after_replace():
            self.apply(0)
        doc = self.wave()
        doc['state']['next_action'] = 'edited outside the tool after the crash'
        self.write(self.wave_path, doc)
        op = self.uncertain_op()[1]['uncertain_operations'][0]['id']
        self.refused('uncertain application', 'reconcile', self.wave_path, '--actor', OWNER, '--op', op,
                     '--evidence', 'look')
        self.refused('not the owner', 'reconcile', self.wave_path, '--actor', 'thread:other', '--op', op,
                     '--evidence', 'look', '--declare', 'committed')
        result = self.ok('reconcile', self.wave_path, '--actor', OWNER, '--op', op, '--declare', 'committed',
                         '--evidence', 'decisions contain the effect; next_action edited by hand afterwards')
        self.assertEqual((result['outcome'], result['declared']), ('committed', True))

    def test_contrary_declaration_refused(self):
        self.receive()
        with self.fail_after_replace():
            self.apply(0)
        op = self.uncertain_op()[1]['uncertain_operations'][0]['id']
        self.refused('contrary declaration', 'reconcile', self.wave_path, '--actor', OWNER, '--op', op,
                     '--declare', 'not_committed', '--evidence', 'wrong')

    def test_prepare_failure_leaves_state_and_no_temporary(self):
        self.receive()
        before = sha(self.wave_path)
        with mock.patch.object(rc, 'append_journal', side_effect=OSError('journal unwritable')):
            code, result = self.apply(0)
        self.assertEqual(code, 1, result)
        self.assertEqual(sha(self.wave_path), before)
        self.assertEqual([p.name for p in self.wave_path.parent.iterdir() if p.name.endswith('.tmp')], [])
        code, cold = self.uncertain_op()
        self.assertEqual((cold['uncertain_operations'], [e['id'] for e in cold['unapplied_events']]), ([], ['event-1']))

    def test_damaged_journal_line_is_reported_not_crashing(self):
        self.receive()
        with open(self.root / 'journal.jsonl', 'a', encoding='utf-8') as stream:
            stream.write('{"id": "half-writ')
        code, result = self.run_cli('resume', self.program_path)
        self.assertEqual(code, 1)
        self.assertIn('line 2 is not valid JSON', result['error'])


class AR1_03_TerminalDisposition(AR1Base):
    def close_coherently(self):
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'stopped')
        p = program()
        p['outcomes'][0].update(status='abandoned', closure={'source': 'synthetic stop', 'remaining': 'stopped'})
        p['outcomes'][1].update(depends_on=[])
        self.write(self.program_path, p)
        code, result = self.run_cli('check', self.program_path)
        self.assertEqual(code, 0, result)

    def test_event_received_before_closure_can_be_disposed_without_reopening(self):
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'pending-on-close', '--kind', 'completion')
        self.close_coherently()
        frozen = sha(self.wave_path)
        code, cold = self.run_cli('resume', self.program_path)
        self.assertTrue(any('dispose' in a and 'pending-on-close' in a for a in cold['actions']), cold['actions'])
        self.refused('not the owner', 'dispose', self.wave_path, '--actor', 'thread:other', '--id', 'pending-on-close',
                     '--disposition', 'late', '--evidence', 'x')
        self.refused('never received', 'dispose', self.wave_path, '--actor', OWNER, '--id', 'ghost',
                     '--disposition', 'late', '--evidence', 'x')
        self.ok('dispose', self.wave_path, '--actor', OWNER, '--id', 'pending-on-close', '--disposition', 'late',
                '--evidence', 'received before the explicit stop; no effect required')
        self.assertEqual(sha(self.wave_path), frozen)
        code, cold = self.run_cli('resume', self.program_path)
        self.assertEqual(cold['unapplied_events'], [])
        code, again = self.run_cli('event', self.wave_path, '--actor', OWNER, '--id', 'pending-on-close', '--kind', 'completion')
        self.assertEqual(again['classification'], 'duplicate')

    def test_dispose_refused_on_active_wave_and_other_wave(self):
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'e1', '--kind', 'completion')
        self.refused('terminal waves', 'dispose', self.wave_path, '--actor', OWNER, '--id', 'e1',
                     '--disposition', 'late', '--evidence', 'x')
        other = self.root / 'waves/b/wave.json'
        other.parent.mkdir(parents=True)
        b = wave2('stopped')
        self.write(other, b)
        p = program()
        p['outcomes'][1].update(status='abandoned', depends_on=[], state_ref='waves/b/wave.json',
                                closure={'source': 's', 'remaining': 'r'})
        self.write(self.program_path, p)
        self.refused('belongs to waves/a/wave.json', 'dispose', other, '--actor', OWNER, '--id', 'e1',
                     '--disposition', 'late', '--evidence', 'x')

    def test_legacy_event_attached_after_closure_can_be_disposed(self):
        legacy = {'id': 'legacy-1', 'at': 't', 'kind': 'event:review', 'file': 'wave.json', 'actor': OWNER,
                  'classification': 'new', 'candidate_seq': None, 'wave_revision': 0, 'detail': None}
        (self.root / 'journal.jsonl').write_text(json.dumps(legacy) + '\n', encoding='utf-8')
        self.close_coherently()
        base = ['--actor', OWNER, '--id', 'legacy-1', '--kind', 'review']
        self.ok('event', self.wave_path, *base, '--attach-legacy', '--evidence', 'receipt shows wave a')
        self.ok('dispose', self.wave_path, '--actor', OWNER, '--id', 'legacy-1', '--disposition', 'not_applicable',
                '--evidence', 'review of a stopped wave')
        code, cold = self.run_cli('resume', self.program_path)
        self.assertEqual(cold['unapplied_events'], [])


class AR1_04_SeparateRelay(AR1Base):
    def test_launcher_records_quota_wait_in_its_index_and_supervisor_keeps_the_wave(self):
        p = program()
        p['owner'] = {'role': 'pilot', 'ref': LAUNCHER}
        self.write(self.program_path, p)
        w = self.wave()
        w['state']['owner'] = {'role': 'pilot', 'ref': LAUNCHER}
        self.write(self.wave_path, w)
        transfer = json.dumps([{'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'},
                                'value': {'next_action': f'wave registry transferred to supervisor {SUPERVISOR}'}}])
        self.ok('write', self.program_path, '--actor', LAUNCHER, '--expect-revision', 0, '--ops', transfer)
        self.ok('claim', self.wave_path, '--actor', SUPERVISOR, '--role', 'supervisor', '--expect-revision', 0,
                '--takeover', '--evidence', 'transfer recorded by the launcher in program.json revision 1')
        self.refused('not the owner', 'transition', self.wave_path, '--actor', LAUNCHER, '--expect-revision', 1,
                     '--to', 'waiting_quota', '--waiting-kind', 'quota', '--detail', 'd', '--trigger', 't', '--resume', 'r')
        wait = json.dumps([
            {'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {
                'waiting_on': {'kind': 'quota', 'detail': 'supervisor hit a rate limit before persisting its wave',
                               'trigger': 'capacity restored'},
                'next_action': 'resume the same supervisor; it reconciles its wave from this index'}},
            {'op': 'set', 'path': 'status', 'value': 'waiting_quota'},
            {'op': 'set', 'path': 'status_reason', 'value': 'supervisor quota recorded by the launcher'}])
        self.ok('write', self.program_path, '--actor', LAUNCHER, '--expect-revision', 1, '--ops', wait)
        self.ok('transition', self.wave_path, '--actor', SUPERVISOR, '--expect-revision', 1, '--to', 'integrating')
        clear = json.dumps([
            {'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {'waiting_on': None,
                                                                              'next_action': 'supervise A'}},
            {'op': 'set', 'path': 'status', 'value': 'active'}])
        self.ok('write', self.program_path, '--actor', LAUNCHER, '--expect-revision', 2, '--ops', clear)
        self.assertEqual(self.wave()['state']['owner']['ref'], SUPERVISOR)


if __name__ == '__main__':
    unittest.main()
