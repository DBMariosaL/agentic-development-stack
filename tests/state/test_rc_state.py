"""Synthetic tests for rc_state.py. Fixtures live under tests/_fixtures and are removed."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE = Path(os.environ.get('RC_STATE_PACKAGE', str(ROOT.parent / 'package')))  # package under test
SCRIPT = PACKAGE / 'rc-coordinate-development/scripts/rc_state.py'
FIXTURES = ROOT / '_fixtures'
spec = importlib.util.spec_from_file_location('rc_state', SCRIPT)
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

OWNER = 'thread:synthetic-pilot'


def wave2(phase='launched'):
    return {
        'schema_version': 2, 'revision': 0, 'program_ref': '../../program.json',
        'mode': 'prepare-and-launch',
        'project': {'root': 'synthetic-root', 'baseline': 'synthetic-base', 'observed_at': 'synthetic-time'},
        'authorization': {'launch': True, 'source': 'synthetic mandate', 'scope': ['synthetic lots'],
                          'exclusions': ['real services']},
        'socles': [{'id': 'A', 'outcome': 'Synthetic lot A', 'depends_on': [], 'readiness': 'ready',
                    'resources': [], 'source_refs': [], 'prompt_artifact': 'prompt_a'}],
        'batches': [['A']], 'artifacts': {'prompt_a': 'socles/a.txt', 'manifest': 'candidate.json'},
        'reviews': [], 'decisions': ['synthetic decision'],
        'candidate': None, 'envelope': {'review_rounds': 2, 'reason': 'low synthetic risk'},
        'actors': [], 'intents': [],
        'state': {'phase': phase, 'owner': {'role': 'pilot', 'ref': OWNER}, 'next_action': 'synthetic next',
                  'blockers': [], 'runtime_refs': None,
                  'consumed': {'prompt_a': {'version': 'v1', 'sha256': 'a' * 64}},
                  'launch_ready': False, 'waiting': None}}


def program(status='active', outcome_status='admitted'):
    return {
        'schema': 'rc-program/1', 'revision': 0, 'owner': {'role': 'pilot', 'ref': OWNER},
        'mandate': {'ref': 'synthetic mandate', 'scope': ['synthetic'], 'exclusions': ['real'],
                    'end_criteria': 'A and B accepted'},
        'skills_consumed': [{'name': 'rc-coordinate-development', 'sha256': 'b' * 64}],
        'status': status, 'status_reason': 'synthetic',
        'outcomes': [
            {'id': 'A', 'outcome': 'Lot A', 'depends_on': [], 'status': outcome_status,
             'state_ref': 'waves/a/wave.json', 'waiting_on': None, 'resources': ['port-1'], 'next_action': 'supervise A'},
            {'id': 'B', 'outcome': 'Lot B', 'depends_on': ['A'], 'status': 'pending', 'state_ref': None,
             'waiting_on': None, 'resources': [], 'next_action': 'admit after A'}],
        'decisions_pending': [], 'last_milestone': None}


class Base(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='rc-state-', dir=FIXTURES)
        self.root = Path(self.temp.name)
        self.wave_path = self.root / 'waves/a/wave.json'
        self.wave_path.parent.mkdir(parents=True)
        self.program_path = self.root / 'program.json'
        self.write(self.wave_path, wave2())
        self.write(self.program_path, program())

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, doc):
        path.write_text(json.dumps(doc), encoding='utf-8')

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rc.main([str(a) for a in argv])
        return code, json.loads(out.getvalue())

    def ok(self, *argv):
        code, result = self.run_cli(*argv)
        self.assertEqual(code, 0, result)
        return result

    def refused(self, fragment, *argv):
        code, result = self.run_cli(*argv)
        self.assertEqual(code, 1, result)
        self.assertIn(fragment, json.dumps(result, ensure_ascii=False))
        return result

    def rev(self, path):
        return json.loads(path.read_text(encoding='utf-8'))['revision']


class Validation(Base):
    def test_valid_fixture(self):
        self.assertEqual(rc.validate_program(program(), self.root), [])
        self.assertEqual(rc.validate_wave2(wave2(), self.wave_path.parent), [])

    def test_contradictory_outcome_and_wave(self):
        w = wave2('stopped')
        w['state']['next_action'] = 'none'
        self.write(self.wave_path, w)
        errors = rc.validate_program(program(), self.root)
        self.assertTrue(any('admitted but wave is stopped' in e for e in errors), errors)
        self.write(self.wave_path, wave2('launched'))
        p = program(outcome_status='accepted')
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any('outcome accepted but wave is launched' in e for e in errors), errors)

    def test_waiting_status_with_ready_work_is_refused(self):
        p = program(status='waiting_quota', outcome_status='accepted')
        p['outcomes'][0]['state_ref'] = None
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any('while outcomes are ready: B' in e for e in errors), errors)

    def test_active_without_moving_work_is_refused(self):
        p = program()
        p['outcomes'][0]['waiting_on'] = {'kind': 'quota', 'detail': 'rate limit', 'trigger': 'capacity back'}
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any('active without ready' in e for e in errors), errors)
        p['status'] = 'waiting_quota'
        self.assertEqual(rc.validate_program(p, self.root), [])

    def test_human_wait_requires_concrete_decision(self):
        p = program()
        p['outcomes'][1]['waiting_on'] = {'kind': 'human', 'detail': 'licence', 'trigger': 'answer'}
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any('human wait requires a pending decision' in e for e in errors), errors)
        p['decisions_pending'] = [{'id': 'D1', 'question': 'Licence?', 'option': '', 'effects': 'x', 'suspends': ['B']}]
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any('concrete option' in e for e in errors), errors)
        p['decisions_pending'][0]['option'] = 'Use tool X v2 under MIT'
        self.assertEqual(rc.validate_program(p, self.root), [])

    def test_completed_program_requires_closed_outcomes(self):
        p = program(status='completed')
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any('completed with open outcomes' in e for e in errors), errors)

    def test_waiting_phase_requires_resume_instructions(self):
        w = wave2('waiting_quota')
        errors = rc.validate_wave2(w, self.wave_path.parent)
        self.assertTrue(any('requires state.waiting' in e for e in errors), errors)

    def test_completed_wave_requires_reviews_on_current_candidate(self):
        w = wave2('completed')
        w['candidate'] = {'seq': 2, 'ref': 'manifest-2', 'frozen_at': 'x', 'artifact': 'manifest', 'sha256': 'c' * 64}
        w['reviews'] = [{'artifact': 'manifest', 'sha256': 'c' * 64, 'status': 'done', 'disposition': 'ok',
                         'reference': 'review-1.md', 'candidate_seq': 1}]
        errors = rc.validate_wave2(w, self.wave_path.parent)
        self.assertTrue(any('on candidate_seq 2' in e for e in errors), errors)
        w['reviews'].append(dict(w['reviews'][0], candidate_seq=2, reference='review-2.md'))
        self.assertEqual(rc.validate_wave2(w, self.wave_path.parent), [])

    def test_terminal_wave_refuses_live_actor(self):
        w = wave2('failed')
        w['actors'] = [{'role': 'champion', 'model': 'm', 'ref': 'task-1', 'correlation': 'c1', 'status': 'running'}]
        errors = rc.validate_wave2(w, self.wave_path.parent)
        self.assertTrue(any('live or unknown actors' in e for e in errors), errors)


class Ownership(Base):
    def test_non_owner_write_refused(self):
        self.refused('is not the owner', 'transition', self.wave_path, '--actor', 'thread:other',
                     '--expect-revision', 0, '--to', 'integrating')

    def test_revision_conflict_between_two_writers(self):
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'integrating')
        self.refused('revision conflict', 'transition', self.wave_path, '--actor', OWNER,
                     '--expect-revision', 0, '--to', 'launched')

    def test_claim_requires_takeover_evidence(self):
        self.refused('takeover requires', 'claim', self.wave_path, '--actor', 'thread:new', '--role', 'pilot',
                     '--expect-revision', 0)
        result = self.ok('claim', self.wave_path, '--actor', 'thread:new', '--role', 'pilot', '--expect-revision', 0,
                         '--takeover', '--evidence', 'previous pilot cancelled, task_status=cancelled')
        self.assertEqual(result['previous_owner'], OWNER)

    def test_lock_present_refuses_without_breaking(self):
        lock = Path(str(self.wave_path) + '.lock')
        lock.write_text('other writer', encoding='utf-8')
        self.refused('lock present', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                     '--to', 'integrating')
        self.assertTrue(lock.exists())
        self.assertEqual(self.rev(self.wave_path), 0)

    def test_owner_cannot_be_changed_by_ops(self):
        ops = json.dumps([{'op': 'set', 'path': 'state.owner', 'value': {'role': 'x', 'ref': 'y'}}])
        self.refused('managed by claim', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)


class IntentsAndActors(Base):
    def add(self, rev, corr, target='champion-A'):
        return self.run_cli('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', rev,
                            '--correlation', corr, '--op', 'launch', '--target', target)

    def test_uncertain_launch_blocks_duplicate_until_reconciled(self):
        code, _ = self.add(0, 'w1/A/champion/1')
        self.assertEqual(code, 0)
        code, result = self.add(1, 'w1/A/champion/2')
        self.assertEqual(code, 1)
        self.assertIn('reconcile first', result['error'])
        self.ok('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1,
                '--correlation', 'w1/A/champion/1', '--status', 'absent')
        code, result = self.add(2, 'w1/A/champion/1')
        self.assertEqual(code, 1)
        self.assertIn('already used', result['error'])
        code, _ = self.add(2, 'w1/A/champion/2')
        self.assertEqual(code, 0)

    def test_confirmed_launch_records_actor_and_resolution_is_immutable(self):
        self.add(0, 'c1')
        self.ok('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1, '--correlation', 'c1',
                '--status', 'confirmed', '--result-ref', 'task-123', '--role', 'champion', '--model', 'opus')
        doc = json.loads(self.wave_path.read_text(encoding='utf-8'))
        self.assertEqual(doc['actors'][0]['ref'], 'task-123')
        ops = json.dumps([{'op': 'update', 'path': 'intents', 'match': {'correlation': 'c1'}, 'value': {'status': 'absent'}}])
        self.refused('resolved and immutable', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 2, '--ops', ops)
        ops = json.dumps([{'op': 'update', 'path': 'actors', 'match': {'correlation': 'c1'}, 'value': {'ref': 'task-999'}}])
        self.refused('known ref is immutable', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 2, '--ops', ops)

    def test_actor_without_confirmed_intent_refused(self):
        ops = json.dumps([{'op': 'append', 'path': 'actors', 'value': {
            'role': 'champion', 'model': 'm', 'ref': 'task-x', 'correlation': 'ghost', 'status': 'running'}}])
        self.refused('needs a confirmed launch intent', 'write', self.wave_path, '--actor', OWNER,
                     '--expect-revision', 0, '--ops', ops)

    def test_intent_cannot_be_born_resolved(self):
        ops = json.dumps([{'op': 'append', 'path': 'intents', 'value': {
            'correlation': 'late', 'op': 'launch', 'target': 't', 'status': 'confirmed', 'result_ref': 'r'}}])
        self.refused('must be created pending', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                     '--ops', ops)

    def test_actor_removal_refused(self):
        self.add(0, 'c1')
        self.ok('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1, '--correlation', 'c1',
                '--status', 'confirmed', '--result-ref', 'task-1', '--role', 'champion')
        ops = json.dumps([{'op': 'set', 'path': 'actors', 'value': []}])
        self.refused('actor c1 removed', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 2, '--ops', ops)

    def test_terminal_with_pending_intent_refused(self):
        self.add(0, 'c1')
        self.refused('unresolved intents', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1,
                     '--to', 'stopped')


class Transitions(Base):
    def test_forbidden_and_terminal(self):
        self.refused('not allowed', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'planning')
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'stopped')
        self.refused('wave is terminal', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1,
                     '--to', 'launched')

    def test_quota_wait_and_resume_to_origin(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            rc.main(['transition', str(self.wave_path), '--actor', OWNER, '--expect-revision', '0',
                     '--to', 'waiting_quota'])  # wait fields are mandatory
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'waiting_quota',
                '--waiting-kind', 'quota', '--detail', 'rate limit on champion', '--trigger', 'capacity restored',
                '--resume', 'send "reprends" in pilot thread; state path waves/a/wave.json')
        self.refused('resume to launched', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1,
                     '--to', 'integrating')
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--to', 'launched')
        doc = json.loads(self.wave_path.read_text(encoding='utf-8'))
        self.assertIsNone(doc['state']['waiting'])

    def test_candidate_seq_monotonic_and_frozen(self):
        ops = json.dumps([{'op': 'set', 'path': 'candidate', 'value': {'seq': 2, 'ref': 'm2', 'frozen_at': 't', 'artifact': 'manifest', 'sha256': 'd' * 64}}])
        self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)
        ops = json.dumps([{'op': 'set', 'path': 'candidate', 'value': {'seq': 1, 'ref': 'm1', 'frozen_at': 't', 'artifact': 'manifest', 'sha256': 'e' * 64}}])
        self.refused('cannot decrease', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', ops)
        ops = json.dumps([{'op': 'set', 'path': 'candidate.ref', 'value': 'm2-edited'}])
        self.refused('frozen candidate is immutable', 'write', self.wave_path, '--actor', OWNER,
                     '--expect-revision', 1, '--ops', ops)

    def test_program_closed_outcome_frozen(self):
        p = program(outcome_status='accepted')
        p['outcomes'][0]['state_ref'] = None
        self.write(self.program_path, p)
        ops = json.dumps([{'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {'status': 'pending'}}])
        self.refused('outcome A is closed', 'write', self.program_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)

    def test_program_waiting_refused_when_work_ready(self):
        p = program(outcome_status='accepted')
        p['outcomes'][0]['state_ref'] = None
        self.write(self.program_path, p)
        ops = json.dumps([{'op': 'set', 'path': 'status', 'value': 'waiting_human'}])
        self.refused('while outcomes are ready', 'write', self.program_path, '--actor', OWNER, '--expect-revision', 0,
                     '--ops', ops)


class Events(Base):
    def event(self, eid, seq=None):
        argv = ['event', self.wave_path, '--actor', OWNER, '--id', eid, '--kind', 'completion']
        if seq is not None:
            argv += ['--candidate-seq', seq]
        return self.ok(*argv)['classification']

    def test_duplicate_stale_late(self):
        w = wave2()
        w['candidate'] = {'seq': 3, 'ref': 'm3', 'frozen_at': 't', 'artifact': 'manifest', 'sha256': 'f' * 64}
        self.write(self.wave_path, w)
        self.assertEqual(self.event('task1:run2', 3), 'new')
        self.assertEqual(self.event('task1:run2', 3), 'unapplied')  # received, not yet applied
        self.ok('ack', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--id', 'task1:run2')
        self.assertEqual(self.event('task1:run2', 3), 'duplicate')
        self.assertEqual(self.event('review:run1', 2), 'stale')
        self.assertEqual(self.event('review:run1', 2), 'duplicate')  # stale needs no application
        w = json.loads(self.wave_path.read_text(encoding='utf-8'))
        w['state']['phase'] = 'stopped'
        self.write(self.wave_path, w)
        self.assertEqual(self.event('review:run9', 3), 'late')
        journal = [json.loads(line) for line in (self.root / 'journal.jsonl').read_text(encoding='utf-8').splitlines()]
        # v5: each guarded write also records a 'prepare' line before replacing the state (AR1-02)
        self.assertEqual(len([e for e in journal if e.get('kind') != 'prepare']), 4)


class Migration(Base):
    def v1_doc(self, phase='waiting_quota'):
        d = wave2()
        for key in ('revision', 'program_ref', 'candidate', 'envelope', 'actors', 'intents'):
            d.pop(key)
        d['schema_version'] = 1
        d['state'].pop('waiting')
        d['state']['phase'] = phase
        d['state']['runtime_refs'] = ['task-old']
        return d

    def test_migration_new_file_only(self):
        src = self.root / 'v1.json'
        self.write(src, self.v1_doc())
        before = hashlib.sha256(src.read_bytes()).hexdigest()
        dest = self.root / 'v2.json'
        result = self.ok('migrate', src, dest)
        self.assertEqual(result['from_sha256'], before)
        self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(), before)
        doc = json.loads(dest.read_text(encoding='utf-8'))
        self.assertEqual(doc['schema_version'], 2)
        self.assertEqual(doc['state']['legacy_runtime_refs'], ['task-old'])
        self.assertEqual(doc['state']['waiting']['kind'], 'quota')
        self.assertEqual(rc.validate_wave2(doc, self.root), [])
        self.refused('destination exists', 'migrate', src, dest)
        self.refused('never overwrite', 'migrate', src, src)

    def test_invalid_v1_not_migrated(self):
        src = self.root / 'bad.json'
        bad = self.v1_doc()
        bad['mode'] = 'prepare'
        self.write(src, bad)
        self.refused('v1 source invalid', 'migrate', src, self.root / 'out.json')
        self.assertFalse((self.root / 'out.json').exists())

    def test_guarded_write_refuses_v1(self):
        src = self.root / 'v1.json'
        self.write(src, self.v1_doc('launched'))
        self.refused('migrate v1 first', 'transition', src, '--actor', OWNER, '--expect-revision', 0, '--to', 'integrating')


class ReadyAndResume(Base):
    def test_ready_and_resource_conflicts(self):
        p = program(outcome_status='accepted')
        p['outcomes'][0]['state_ref'] = None
        p['outcomes'].append({'id': 'C', 'outcome': 'Lot C', 'depends_on': [], 'status': 'pending', 'state_ref': None,
                              'waiting_on': None, 'resources': ['device'], 'next_action': 'x'})
        p['outcomes'][1]['resources'] = ['device']
        view = rc.ready_view(p)
        self.assertEqual(view['ready'], ['B', 'C'])
        self.assertEqual(view['resource_conflicts'], [{'kind': 'ready-ready', 'outcomes': ['B', 'C'], 'resources': ['device']}])

    def test_resume_lists_reconciliation_before_relaunch(self):
        IntentsAndActors.add(self, 0, 'w1/A/champion/1')
        result = self.ok('resume', self.program_path)
        joined = ' '.join(result['actions'])
        self.assertIn('reconcile intent w1/A/champion/1', joined)
        self.assertEqual(result['waves'][0]['pending_intents'][0]['correlation'], 'w1/A/champion/1')


if __name__ == '__main__':
    unittest.main()
