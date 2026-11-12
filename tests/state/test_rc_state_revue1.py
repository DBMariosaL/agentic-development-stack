"""Regression tests for the findings of pre-review 1 (revues/pre-revue-1-gpt/rapport.md, F01-F16, P15)."""
import json
import unittest
from pathlib import Path

from test_rc_state import OWNER, Base, program, rc, wave2


class Review1(Base):
    def wave(self):
        return json.loads(self.wave_path.read_text(encoding='utf-8'))

    def test_F01_owner_cannot_change_through_descendant_or_ancestor(self):
        ops = json.dumps([{'op': 'set', 'path': 'state.owner.ref', 'value': 'thread:other'}])
        self.refused('managed by claim', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)
        state = self.wave()['state']
        state['owner'] = {'role': 'pilot', 'ref': 'thread:other'}
        ops = json.dumps([{'op': 'set', 'path': 'state', 'value': state}])
        self.refused('owner changes only through claim', 'write', self.wave_path, '--actor', OWNER,
                     '--expect-revision', 0, '--ops', ops)

    def test_F02_journal_lock_refuses_before_commit(self):
        lock = self.root / 'journal.jsonl.lock'
        lock.write_text('held', encoding='utf-8')
        self.refused('lock present', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                     '--to', 'integrating')
        doc = self.wave()
        self.assertEqual((doc['revision'], doc['state']['phase']), (0, 'launched'))

    def test_F03_received_but_unapplied_event_is_replayed_and_listed(self):
        argv = ['event', self.wave_path, '--actor', OWNER, '--id', 'task:run1', '--kind', 'completion']
        self.assertEqual(self.ok(*argv)['classification'], 'new')
        self.assertEqual(self.ok(*argv)['classification'], 'unapplied')
        code, result = self.run_cli('resume', self.program_path)
        self.assertEqual([e['id'] for e in result['unapplied_events']], ['task:run1'])
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'integrating',
                '--applies-event', 'task:run1')
        self.assertEqual(self.ok(*argv)['classification'], 'duplicate')
        self.refused('already applied', 'ack', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--id', 'task:run1')
        self.refused('never received', 'ack', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--id', 'ghost')

    def test_F04_completion_needs_review_of_candidate_artifact_and_hash(self):
        manifest = self.wave_path.parent / 'candidate.json'
        manifest.write_text('{"candidate": 1}', encoding='utf-8')
        sha = rc.sha256_file(manifest)
        w = wave2('completed')
        w['candidate'] = {'seq': 1, 'ref': 'candidate.json', 'artifact': 'manifest', 'sha256': sha, 'frozen_at': 't'}
        w['reviews'] = [{'artifact': 'prompt_a', 'sha256': 'a' * 64, 'status': 'done', 'disposition': 'ok',
                         'reference': 'r.md', 'candidate_seq': 1}]
        errors = rc.validate_wave2(w, self.wave_path.parent)
        self.assertTrue(any('candidate artifact manifest' in e for e in errors), errors)
        w['reviews'].append({'artifact': 'manifest', 'sha256': sha, 'status': 'done', 'disposition': 'ok',
                             'reference': 'r2.md', 'candidate_seq': 1})
        self.assertEqual(rc.validate_wave2(w, self.wave_path.parent), [])
        manifest.write_text('{"candidate": "edited"}', encoding='utf-8')
        errors = rc.validate_wave2(w, self.wave_path.parent, check_paths=True)
        self.assertTrue(any('candidate artifact missing or sha256 mismatch' in e for e in errors), errors)

    def test_F05_pending_decision_and_waiting_on_must_agree(self):
        p = program()
        p['decisions_pending'] = [{'id': 'D1', 'question': 'q', 'option': 'o', 'effects': 'e', 'suspends': ['B']}]
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any('suspended by a pending decision but waiting_on is not human' in e for e in errors), errors)
        self.assertNotIn('B', rc.ready_view(p)['ready'])

    def test_F06_abandoned_dependency_does_not_satisfy_consumer(self):
        p = program()
        p['outcomes'][0].update(status='abandoned', state_ref=None, closure={'source': 'decision X', 'remaining': 'all'})
        p['outcomes'][1].update(status='admitted', state_ref='waves/a/wave.json')
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any('B: admitted while dependency A is not accepted' in e for e in errors), errors)

    def v1(self, phase):
        d = wave2()
        for key in ('revision', 'program_ref', 'candidate', 'envelope', 'actors', 'intents'):
            d.pop(key)
        d['schema_version'] = 1
        d['state'].pop('waiting')
        d['state']['phase'] = phase
        d['state']['runtime_refs'] = ['task-old']
        return d

    def test_F07_migration_keeps_runtime_refs_as_unknown_actors(self):
        src = self.root / 'v1.json'
        self.write(src, self.v1('waiting_quota'))
        dest = self.wave_path.parent / 'migrated.json'
        result = self.ok('migrate', src, dest)
        self.assertEqual(result['unknown_actors'], ['legacy/0'])
        doc = json.loads(dest.read_text(encoding='utf-8'))
        self.assertEqual(doc['actors'][0]['ref'], 'task-old')
        self.assertEqual(doc['actors'][0]['status'], 'unknown')
        p = program()
        p['outcomes'][0]['state_ref'] = 'waves/a/migrated.json'
        self.write(self.program_path, p)
        code, result = self.run_cli('resume', self.program_path)
        self.assertTrue(any('legacy/0' in a and 'task-old' in a for a in result['actions']), result['actions'])

    def test_F08_terminal_v1_is_kept_historical(self):
        src = self.root / 'v1.json'
        doc = self.v1('completed')
        doc['state']['runtime_refs'] = None
        self.write(src, doc)
        self.refused('historical v1 registry', 'migrate', src, self.root / 'out.json')
        self.assertFalse((self.root / 'out.json').exists())

    def test_F09_launch_ready_reset_on_context_change(self):
        w = wave2('ready')
        w['reviews'] = [{'artifact': 'prompt_a', 'sha256': 'a' * 64, 'status': 'done', 'disposition': 'ok', 'reference': 'r.md'}]
        w['state']['launch_ready'] = True
        self.write(self.wave_path, w)
        self.assertEqual(rc.validate_wave2(w, self.wave_path.parent), [])
        ops = json.dumps([{'op': 'set', 'path': 'project.baseline', 'value': 'changed-base'}])
        self.refused('launch_ready must be reset', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                     '--ops', ops)
        ops = json.dumps([{'op': 'set', 'path': 'project.baseline', 'value': 'changed-base'},
                          {'op': 'set', 'path': 'state.launch_ready', 'value': False}])
        self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)

    def test_F10_blocked_keeps_its_origin(self):
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'blocked',
                '--waiting-kind', 'resource', '--detail', 'device busy', '--trigger', 'device free', '--resume', 'relaunch')
        self.assertEqual(self.wave()['state']['waiting']['from'], 'launched')
        self.refused('resume to launched', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1,
                     '--to', 'preparing')
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--to', 'launched')

    def test_F11_conflict_with_admitted_holder(self):
        p = program()
        p['outcomes'][1].update(depends_on=[], resources=['port-1'])
        view = rc.ready_view(p)
        self.assertIn({'kind': 'ready-admitted', 'outcomes': ['B', 'A'], 'resources': ['port-1']}, view['resource_conflicts'])

    def test_F12_no_second_launch_while_actor_live(self):
        base = ['intent', self.wave_path, 'add', '--actor', OWNER, '--op', 'launch', '--target', 'champion-A']
        self.ok(*base[:3], '--actor', OWNER, '--expect-revision', 0, '--correlation', 'a/1', '--op', 'launch',
                '--target', 'champion-A')
        self.ok('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1, '--correlation', 'a/1',
                '--status', 'confirmed', '--result-ref', 'task-A', '--role', 'champion')
        self.refused('is running', 'intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 2,
                     '--correlation', 'a/2', '--op', 'launch', '--target', 'champion-A')
        ops = json.dumps([{'op': 'update', 'path': 'actors', 'match': {'correlation': 'a/1'}, 'value': {'status': 'interrupted'}}])
        self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 2, '--ops', ops)
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 3, '--correlation', 'a/2',
                '--op', 'launch', '--target', 'champion-A')

    def test_F13_malformed_types_return_json_errors(self):
        p = program()
        p['status'] = []
        p['outcomes'][0]['status'] = {'x': 1}
        p['decisions_pending'] = [{'id': [], 'suspends': [[]]}]
        self.write(self.program_path, p)
        code, result = self.run_cli('check', self.program_path)
        self.assertEqual(code, 1)
        self.assertFalse(result['valid'])
        w = wave2()
        w['actors'] = [{'status': []}]
        w['intents'] = ['x']
        self.write(self.wave_path, w)
        code, result = self.run_cli('check', self.wave_path)
        self.assertEqual(code, 1)
        self.assertFalse(result['valid'])

    def test_F14_program_ref_must_resolve_and_is_immutable(self):
        ops = json.dumps([{'op': 'set', 'path': 'program_ref', 'value': '../../elsewhere/not-an-index.json'}])
        self.refused('program_ref', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)
        w = wave2()
        w['program_ref'] = None
        self.write(self.wave_path, w)
        (self.root / 'elsewhere').mkdir()
        self.refused('must resolve to an existing program', 'write', self.wave_path, '--actor', OWNER,
                     '--expect-revision', 0, '--ops', ops)
        self.assertFalse((self.root / 'elsewhere' / 'journal.jsonl').exists())

    def test_F16_regression_package_is_discoverable(self):
        self.assertTrue((Path(__file__).resolve().parent / 'regression' / '__init__.py').is_file())

    def test_P15_ready_fails_when_state_is_inconsistent(self):
        p = program()
        p['decisions_pending'] = [{'id': 'D1', 'question': 'q', 'option': 'o', 'effects': 'e', 'suspends': ['B']}]
        self.write(self.program_path, p)
        code, result = self.run_cli('ready', self.program_path)
        self.assertEqual(code, 1)
        self.assertTrue(result['consistency_errors'])


if __name__ == '__main__':
    unittest.main()
