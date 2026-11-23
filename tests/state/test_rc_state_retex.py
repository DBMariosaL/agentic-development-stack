"""First real project: refusals that say what to do, ops on standard input, closures reported apart from errors."""
import io
import json
from unittest import mock

from regression.test_wave_validator_v1 import launch, module as checker
from test_rc_state import OWNER, program, rc, wave2
from test_rc_state_v10_campagne import Campaign

ACTOR = {'role': 'champion', 'model': None, 'ref': 'task-1', 'correlation': 'c1', 'status': 'completed',
         'target': 'A', 'evidence': 'report r.md'}


class StdinOps(Campaign):
    def stdin(self, data):  # bytes, whatever the console code page
        return mock.patch.object(rc.sys, 'stdin', io.TextIOWrapper(io.BytesIO(data), encoding='cp1252'))

    def test_ops_dash_reads_the_list_from_standard_input_in_utf8(self):
        wave = self.solo()
        value = 'relire l’index révisé'
        with self.stdin(json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': value}],
                                   ensure_ascii=False).encode('utf-8')):
            self.ok('write', wave, '--actor', OWNER, '--expect-revision', 0, '--ops', '-')
        self.assertEqual(self.doc(wave)['state']['next_action'], value)
        for data, fragment in ((b'[', 'not valid JSON'), (b'[]', 'ops must be a nonempty list'),
                               (b'\xff[]', 'standard input')):
            with self.subTest(data=data), self.stdin(data):
                self.refused(fragment, 'write', wave, '--actor', OWNER, '--expect-revision', 1, '--ops', '-')
        self.assertEqual(self.doc(wave)['revision'], 1)


class Refusals(Campaign):
    def test_launch_ready_names_the_review_to_record_and_not_required(self):
        data = launch(self.root)
        sha = data['state']['consumed']['supervisor']['sha256']
        data['reviews'] = [r for r in data['reviews'] if r['artifact'] != 'supervisor']
        missing = [e for e in checker.validate(data, self.root, check_paths=False) if e.startswith('supervisor:')]
        self.assertIn(f'"artifact": "supervisor", "sha256": "{sha}"', missing[0])
        self.assertIn('"not_required", with its reason as disposition and its source as reference', missing[0])
        data['reviews'].append({'artifact': 'supervisor', 'sha256': sha, 'status': 'pending', 'disposition': None,
                                'reference': None})
        pending = [e for e in checker.validate(data, self.root, check_paths=False) if e.startswith('supervisor:')]
        self.assertIn("still 'pending'", pending[0])

    def test_resolution_announces_its_actor_and_a_second_append_names_it(self):
        wave = self.solo()
        self.ok('intent', wave, 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'r1',
                '--op', 'launch', '--target', 'review-A')
        result = self.ok('intent', wave, 'resolve', '--actor', OWNER, '--expect-revision', 1, '--correlation', 'r1',
                         '--status', 'confirmed', '--result-ref', 'task-1', '--role', 'reviewer')
        self.assertEqual((result['actor']['correlation'], result['actor']['role']), ('r1', 'reviewer'))
        self.assertIn('created running by this resolution', result['actor']['effect'])
        append = [{'op': 'append', 'path': 'actors', 'value': {'role': 'reviewer', 'model': None, 'ref': 'task-1',
                                                               'correlation': 'r1', 'status': 'running',
                                                               'target': 'review-A'}}]
        result = self.refused("actor r1 already exists (role 'reviewer', status 'running'", 'write', wave,
                              '--actor', OWNER, '--expect-revision', 2, '--ops', json.dumps(append))
        self.assertIn('{"op":"update","path":"actors","match":{"correlation":"r1"}', result['error'])

    def test_resume_on_a_wave_names_its_index(self):
        result = self.refused('resume takes the program index', 'resume', self.wave_path)
        self.assertIn(f'resume {self.program_path.resolve()}', result['error'])

    def test_write_in_a_terminal_wave_sends_the_receipt_to_the_index(self):
        self.write(self.wave_path, wave2('stopped'))
        self.refused('goes to the program index (program_ref ../../program.json)', 'write', self.wave_path,
                     '--actor', OWNER, '--expect-revision', 0,
                     '--ops', json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'push done'}]))


class Resume(Campaign):
    def test_closure_window_is_reported_apart_from_consistency_errors(self):
        self.write(self.wave_path, wave2('stopped'))
        p = program()
        p['outcomes'][1]['state_ref'] = 'waves/a/wave.json'  # B pending on the same closed wave
        self.write(self.program_path, p)
        result = self.ok('check', self.program_path)
        self.assertEqual((result['valid'], result['errors']), (True, []))
        self.assertEqual([(c['wave'], c['phase'], c['outcomes']) for c in result['closure_pending']],
                         [('waves/a/wave.json', 'stopped', ['A', 'B'])])
        self.assertIn('--expect-revision 0', result['closure_pending'][0]['write'])
        ready = self.ok('ready', self.program_path)
        self.assertEqual((ready['consistency_errors'], [c['outcomes'] for c in ready['closure_pending']]),
                         ([], [['A', 'B']]))
        self.write(self.wave_path, wave2('launched'))
        p['outcomes'][0]['status'] = 'accepted'
        self.write(self.program_path, p)
        self.refused('A: contradictory state: outcome accepted but wave is launched', 'check', self.program_path)

    def test_terminal_next_action_is_history_and_a_launched_wave_without_live_actor_is_signalled(self):
        self.write(self.wave_path, wave2('stopped'))
        wave = self.ok('resume', self.program_path)['waves'][0]
        self.assertEqual((wave['next_action'], wave['next_action_at_closure']), (None, 'synthetic next'))
        w = wave2('launched')
        w['actors'] = [ACTOR]
        self.write(self.wave_path, w)
        cold = self.ok('resume', self.program_path)
        self.assertEqual(cold['waves'][0]['next_action'], 'synthetic next')
        self.assertTrue(any('signal: wave launched but none of its 1 actors is alive any more (completed)' in a
                            for a in cold['actions']), cold['actions'])


class PartialWave(Campaign):
    def test_outcome_held_is_accepted_in_a_partial_wave_another_outcome_carries(self):
        w = wave2('completed_partial')
        w['candidate'] = {'seq': 1, 'ref': 'manifest-1', 'artifact': 'manifest', 'sha256': 'c' * 64}
        w['reviews'] = [{'artifact': 'manifest', 'sha256': 'c' * 64, 'status': 'done', 'disposition': 'ok',
                         'reference': 'review r.md', 'candidate_seq': 1}]
        self.write(self.wave_path, w)
        p = program(status='completed', outcome_status='accepted')
        p['outcomes'][1].update(status='accepted_partial', state_ref='waves/a/wave.json',
                                closure={'source': 'wave decisions', 'remaining': 'unqualified scope of B'})
        self.assertEqual(rc.validate_program(p, self.root), [])
        dependent = {'id': 'C', 'outcome': 'Lot C', 'depends_on': ['B'], 'status': 'admitted',
                     'state_ref': 'waves/a/wave.json', 'waiting_on': None, 'resources': [], 'next_action': 'x'}
        self.assertIn('C: admitted while dependency B is not accepted',
                      rc.validate_program(dict(p, outcomes=p['outcomes'] + [dependent]), self.root))
        p['outcomes'][1].update(status='accepted')
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any(e.startswith('A, B: contradictory state: wave waves/a/wave.json is completed_partial but '
                                         'every outcome referencing it is fully accepted') for e in errors), errors)
