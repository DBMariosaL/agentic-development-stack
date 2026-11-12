"""Regression tests for pre-review 2 findings on rc_state.py (revues/pre-revue-2-gpt/rapport.md, R2-01 to R2-04)."""
import json
import unittest

from test_rc_state import OWNER, Base, program, rc, wave2


class Review2(Base):
    def wave(self):
        return json.loads(self.wave_path.read_text(encoding='utf-8'))

    def launch(self, rev, corr, target='champion-A'):
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', rev, '--correlation', corr,
                '--op', 'launch', '--target', target)
        self.ok('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', rev + 1, '--correlation', corr,
                '--status', 'confirmed', '--result-ref', f'task-{corr}', '--role', 'champion')

    def test_R2_01_write_cannot_add_second_launch_on_live_target(self):
        self.launch(0, 'a/1')
        ops = json.dumps([{'op': 'append', 'path': 'intents', 'value': {
            'correlation': 'a/2', 'op': 'launch', 'target': 'champion-A', 'status': 'pending', 'result_ref': None}}])
        self.refused('reconcile it first', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 2, '--ops', ops)
        w = wave2()
        w['actors'] = [{'role': 'c', 'ref': 't1', 'correlation': 'x', 'status': 'running', 'target': 'champion-A'},
                       {'role': 'c', 'ref': 't2', 'correlation': 'y', 'status': 'running', 'target': 'champion-A'}]
        self.assertIn('two live actors on the same target', rc.validate_wave2(w))

    def test_R2_01_actor_target_must_match_intent(self):
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'a/1',
                '--op', 'launch', '--target', 'champion-A')
        ops = json.dumps([
            {'op': 'update', 'path': 'intents', 'match': {'correlation': 'a/1'}, 'value': {'status': 'confirmed', 'result_ref': 't'}},
            {'op': 'append', 'path': 'actors', 'value': {'role': 'c', 'ref': 't', 'correlation': 'a/1', 'status': 'running',
                                                         'target': 'champion-B'}}])
        self.refused('target must be its launch intent target', 'write', self.wave_path, '--actor', OWNER,
                     '--expect-revision', 1, '--ops', ops)

    def test_R2_02_wait_origin_is_derived_and_waiting_null_outside_waits(self):
        ops = json.dumps([{'op': 'set', 'path': 'state.phase', 'value': 'blocked'},
                          {'op': 'set', 'path': 'state.waiting', 'value': {
                              'kind': 'resource', 'detail': 'd', 'trigger': 't', 'resume': 'r', 'from': 'preparing'}}])
        self.refused('requires waiting.from=launched', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                     '--ops', ops)
        ops = json.dumps([{'op': 'set', 'path': 'state.waiting', 'value': []}])
        self.refused('state.waiting must be null', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                     '--ops', ops)

    def test_R2_03_event_is_applied_only_on_its_own_wave(self):
        other = self.root / 'waves/b/wave.json'
        other.parent.mkdir(parents=True)
        self.write(other, wave2())
        p = program()
        p['outcomes'][1].update(status='admitted', depends_on=[], state_ref='waves/b/wave.json')
        self.write(self.program_path, p)
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'task-A:run-1', '--kind', 'completion')
        self.refused('was received for waves/a/wave.json', 'ack', other, '--actor', OWNER, '--expect-revision', 0,
                     '--id', 'task-A:run-1')
        code, result = self.run_cli('resume', self.program_path)
        self.assertEqual([e['wave'] for e in result['unapplied_events']], ['waves/a/wave.json'])
        self.ok('ack', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--id', 'task-A:run-1')

    def test_R2_04_untargeted_unknown_actor_blocks_launch_and_stop(self):
        w = wave2()
        w['actors'] = [{'role': 'legacy', 'model': None, 'ref': 'task-old', 'correlation': 'legacy/0',
                        'status': 'unknown', 'target': None}]
        self.write(self.wave_path, w)
        self.refused('no known target', 'intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 0,
                     '--correlation', 'a/1', '--op', 'launch', '--target', 'champion-A')
        self.refused('live or unknown actors', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                     '--to', 'stopped')
        ops = json.dumps([{'op': 'update', 'path': 'actors', 'match': {'correlation': 'legacy/0'},
                           'value': {'status': 'interrupted', 'evidence': 'task_status=interrupted'}}])
        self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 1, '--correlation', 'a/1',
                '--op', 'launch', '--target', 'champion-A')

    def test_R2_D04_replayed_old_candidate_event_becomes_stale(self):
        w = wave2()
        w['candidate'] = {'seq': 1, 'ref': 'm1', 'artifact': 'manifest', 'sha256': 'a' * 64, 'frozen_at': 't'}
        self.write(self.wave_path, w)
        argv = ['event', self.wave_path, '--actor', OWNER, '--id', 'review-old', '--kind', 'review', '--candidate-seq', 1]
        self.assertEqual(self.ok(*argv)['classification'], 'new')
        ops = json.dumps([{'op': 'set', 'path': 'candidate', 'value': {
            'seq': 2, 'ref': 'm2', 'artifact': 'manifest', 'sha256': 'b' * 64, 'frozen_at': 't'}}])
        self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)
        self.assertEqual(self.ok(*argv)['classification'], 'stale')
        self.assertEqual(self.ok(*argv)['classification'], 'duplicate')
        code, result = self.run_cli('resume', self.program_path)
        self.assertEqual(result['unapplied_events'], [])

    def test_R2_D05_program_ref_immutable_with_second_valid_index(self):
        second = self.root / 'second.json'
        self.write(second, program())
        ops = json.dumps([{'op': 'set', 'path': 'program_ref', 'value': '../../second.json'}])
        self.refused('immutable', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)


if __name__ == '__main__':
    unittest.main()
