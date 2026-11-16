"""Defects reproduced by the v10 campaign, each checked at command level."""
import contextlib
import hashlib
import io
import json
import unittest
from unittest import mock

from test_rc_state import OWNER, Base, rc, wave2

EVENT = 'task-7:run1'
WAVE_SPEC = {'authorization': {'exclusions': []}, 'state': {'next_action': 'prepare documents'}}
PROGRAM_SPEC = {'mandate': {'ref': 'synthetic mandate', 'scope': ['synthetic'], 'exclusions': [],
                            'end_criteria': 'A accepted'},
                'outcomes': [{'id': 'A', 'outcome': 'Lot A', 'next_action': 'prepare A'}]}


class Campaign(Base):
    def init(self, name, kind, spec):
        folder = self.root / name
        folder.mkdir()
        (folder / 'spec.json').write_text(json.dumps(spec), encoding='utf-8')
        path = folder / ('program.json' if kind == 'program' else 'wave.json')
        code, result = self.run_cli('init', path, '--kind', kind, '--actor', OWNER, '--role', 'pilot',
                                    '--spec', folder / 'spec.json')
        return path, code, result

    def solo(self, spec=WAVE_SPEC):
        path, code, result = self.init('solo', 'wave', spec)
        self.assertEqual(code, 0, result)
        return path

    def doc(self, path):
        return json.loads(path.read_text(encoding='utf-8'))

    def journal(self, path):
        return [json.loads(line) for line in (path.parent / 'journal.jsonl').read_text(encoding='utf-8').splitlines()]

    def ops(self, path, rev, ops, *extra):
        return self.run_cli('write', path, '--actor', OWNER, '--expect-revision', rev, '--ops', json.dumps(ops), *extra)

    def short(self, path, rev, *extra):
        return self.run_cli('write', path, '--actor', OWNER, '--expect-revision', rev, '--resolve-intent', 'c1',
                            '--status', 'confirmed', '--result-ref', 'task-7', '--record-event', EVENT,
                            '--kind', 'return', *extra)

    def send_intent(self, path):
        self.ok('intent', path, 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'c1',
                '--op', 'send', '--target', 'T')

    def received(self, path):
        return [e['id'] for e in self.journal(path) if e.get('kind', '').startswith('event:')]

    def applied(self, path):
        return [e['applies_event'] for e in self.journal(path) if e.get('applies_event')]


class ShortForm(Campaign):
    def test_R13_01_invalid_ops_json_keeps_the_signal_received(self):
        wave = self.solo()
        self.send_intent(wave)
        before = wave.read_bytes()
        code, result = self.short(wave, 1, '--ops', '[')
        self.assertEqual(code, 1, result)
        self.assertIn('not valid JSON', result['error'])
        self.assertIn(f'event {EVENT} is recorded and stays unapplied', result['error'])
        self.assertEqual(wave.read_bytes(), before)
        self.assertEqual((self.received(wave), self.applied(wave)), ([EVENT], []))

    def test_R13_02_ops_cannot_reopen_the_intent_just_resolved(self):
        wave = self.solo()
        self.send_intent(wave)
        reopen = [{'op': 'update', 'path': 'intents', 'match': {'correlation': 'c1'},
                   'value': {'status': 'pending', 'result_ref': None}}]
        code, result = self.short(wave, 1, '--ops', json.dumps(reopen))
        self.assertEqual(code, 1, result)
        self.assertIn('intent c1 is resolved and immutable', result['error'])
        self.assertEqual(self.doc(wave)['revision'], 1)
        self.assertEqual(self.applied(wave), [])
        code, result = self.short(wave, 1)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['event']['classification'], 'unapplied')
        self.assertEqual(self.doc(wave)['intents'][0]['status'], 'confirmed')
        self.assertEqual(self.applied(wave), [EVENT])

    def test_R13_03_failure_after_prepare_reports_uncertain_not_rerun(self):
        wave = self.solo()
        self.send_intent(wave)
        original = rc.append_journal

        def failing(path, entry):
            if entry.get('kind') == 'write' and entry.get('commits'):
                raise OSError('injected commit failure')
            return original(path, entry)

        with mock.patch.object(rc, 'append_journal', side_effect=failing):
            code, result = self.short(wave, 1)
        self.assertEqual(code, 1, result)
        self.assertIn(f'event {EVENT} is now uncertain: run reconcile', result['error'])
        self.assertNotIn('rerun this command once', result['error'])
        code, result = self.run_cli('event', wave, '--actor', OWNER, '--id', EVENT, '--kind', 'return')
        self.assertEqual(result['classification'], 'uncertain')


class StaleEvents(Campaign):
    def test_R01_01_event_of_an_older_candidate_applies_to_nothing(self):
        wave = self.solo()

        def candidate(seq):
            return {'seq': seq, 'ref': f'manifest-{seq}', 'artifact': 'manifest', 'sha256': 'c' * 64}

        self.assertEqual(self.ops(wave, 0, [{'op': 'set', 'path': 'artifacts', 'value': {'manifest': 'm.json'}},
                                            {'op': 'set', 'path': 'candidate', 'value': candidate(1)}])[0], 0)
        self.ok('event', wave, '--actor', OWNER, '--id', EVENT, '--kind', 'stop', '--candidate-seq', 1)
        self.assertEqual(self.ops(wave, 1, [{'op': 'set', 'path': 'candidate', 'value': candidate(2)}])[0], 0)
        before = wave.read_bytes()
        for argv in (('transition', wave, '--actor', OWNER, '--expect-revision', 2, '--to', 'stopped',
                      '--applies-event', EVENT),
                     ('write', wave, '--actor', OWNER, '--expect-revision', 2, '--applies-event', EVENT, '--ops',
                      json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'old signal'}])),
                     ('ack', wave, '--actor', OWNER, '--expect-revision', 2, '--id', EVENT)):
            with self.subTest(command=argv[0]):
                result = self.refused('older than the current candidate 2', *argv)
                self.assertIn('stale', result['error'])
        self.assertEqual(wave.read_bytes(), before)
        self.assertEqual(self.ok('event', wave, '--actor', OWNER, '--id', EVENT, '--kind', 'stop')['classification'],
                         'stale')


class Acceptance(Campaign):
    def test_R01_02_accepted_without_wave_nor_closure_refused(self):
        program, code, result = self.init('prog', 'program', PROGRAM_SPEC)
        self.assertEqual(code, 0, result)
        accept = [{'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {'status': 'accepted'}},
                  {'op': 'set', 'path': 'status', 'value': 'completed'}]
        code, result = self.ops(program, 0, accept)
        self.assertEqual(code, 1, result)
        self.assertIn('A: accepted requires state_ref', result['error'])
        self.assertEqual(self.doc(program)['revision'], 0)
        accept[0]['value']['closure'] = {'source': 'accepted in a review of the adopted history', 'remaining': 'none'}
        self.assertEqual(self.ops(program, 0, accept)[0], 0)
        self.assertEqual(self.ok('check', program)['errors'], [])

    def test_R07_02_init_refuses_accepted_dependency_without_wave(self):
        spec = dict(PROGRAM_SPEC, outcomes=[
            {'id': 'A', 'outcome': 'Contract', 'next_action': 'none', 'status': 'accepted'},
            {'id': 'B', 'outcome': 'Consume A', 'next_action': 'prepare B', 'depends_on': ['A']}])
        program, code, result = self.init('prog', 'program', spec)
        self.assertEqual(code, 1, result)
        self.assertIn('A: accepted requires state_ref', result['error'])
        self.assertFalse(program.exists())


class PrepareMode(Campaign):
    def test_R01_03_no_champion_actor_without_launch_authorization(self):
        wave = self.solo()
        self.ok('intent', wave, 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'l1',
                '--op', 'launch', '--target', 'product')
        resolve = ('intent', wave, 'resolve', '--actor', OWNER, '--expect-revision', 1, '--correlation', 'l1',
                   '--status', 'confirmed', '--result-ref', 'task-1')
        for role in ('champion', 'Superviseur', 'integrator-B'):
            with self.subTest(role=role):
                self.refused(f'live {role} actor in a wave without launch authorization', *resolve, '--role', role)
        done = [{'op': 'update', 'path': 'actors', 'match': {'correlation': 'l1'},
                 'value': {'status': 'completed', 'evidence': 'report r.md'}}]
        self.refused("actor l1: role 'champion' refused in a wave without launch authorization", 'write', wave,
                     '--actor', OWNER, '--expect-revision', 1, '--resolve-intent', 'l1', '--status', 'confirmed',
                     '--result-ref', 'task-1', '--role', 'champion', '--ops', json.dumps(done))
        self.assertEqual((self.doc(wave)['revision'], self.doc(wave)['actors']), (1, []))
        self.ok(*resolve, '--role', 'reviewer')
        self.assertEqual([(a['role'], a['status']) for a in self.doc(wave)['actors']], [('reviewer', 'running')])

    def test_R01_03_live_champion_invalid_once_authorization_is_withdrawn(self):
        w = wave2()
        w['actors'] = [{'role': 'champion', 'model': None, 'ref': 'task-1', 'correlation': 'l1',
                        'status': 'running', 'target': 'A'}]
        self.write(self.wave_path, w)
        self.assertEqual(self.ok('check', self.wave_path)['errors'], [])
        self.refused('live champion actor in a wave without launch authorization', 'write', self.wave_path,
                     '--actor', OWNER, '--expect-revision', 0, '--ops',
                     json.dumps([{'op': 'set', 'path': 'authorization.launch', 'value': False}]))


class LaunchReady(Campaign):
    def test_R03_02_context_change_and_launch_ready_need_two_writes(self):
        w = wave2('ready')
        w['reviews'] = [{'artifact': 'prompt_a', 'sha256': 'a' * 64, 'status': 'done', 'disposition': 'ok',
                         'reference': 'r.md'}]
        self.write(self.wave_path, w)
        result = self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', json.dumps(
            [{'op': 'set', 'path': 'project.baseline', 'value': 'new-base'},
             {'op': 'set', 'path': 'state.launch_ready', 'value': True}]))
        self.assertEqual(result['launch_ready_reset']['changed'], ['project'])
        self.assertIs(self.doc(self.wave_path)['state']['launch_ready'], False)
        result = self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--ops', json.dumps(
            [{'op': 'set', 'path': 'state.launch_ready', 'value': True}]))
        self.assertNotIn('launch_ready_reset', result)
        self.assertIs(self.doc(self.wave_path)['state']['launch_ready'], True)


class ReviewHashes(Campaign):
    def test_R03_03_check_paths_compares_documentary_reviews(self):
        actual = hashlib.sha256(b'actual').hexdigest()
        review = {'artifact': 'doc', 'sha256': 'a' * 64, 'status': 'done', 'disposition': 'reviewed',
                  'reference': 'report.md'}
        wave = self.solo(dict(WAVE_SPEC, artifacts={'doc': 'doc.txt'}, reviews=[review]))
        (wave.parent / 'doc.txt').write_bytes(b'actual')
        code, result = self.run_cli('check', wave, '--check-paths')
        self.assertEqual(code, 1, result)
        self.assertIn('doc: no documentary review sha256 matches the local artifact', ' '.join(result['errors']))
        self.assertEqual(self.ok('check', wave)['errors'], [])
        self.ok('write', wave, '--actor', OWNER, '--expect-revision', 0, '--ops', json.dumps(
            [{'op': 'append', 'path': 'reviews', 'value': dict(review, sha256=actual)}]))
        self.assertEqual(self.ok('check', wave, '--check-paths')['errors'], [])

    def test_init_and_append_default_review_disposition_and_reference_to_null(self):
        review = {'artifact': 'doc', 'sha256': 'a' * 64, 'status': 'pending'}
        wave = self.solo(dict(WAVE_SPEC, artifacts={'doc': 'doc.txt'}, reviews=[review]))
        self.ok('write', wave, '--actor', OWNER, '--expect-revision', 0, '--ops', json.dumps(
            [{'op': 'append', 'path': 'reviews', 'value': dict(review, sha256='b' * 64)}]))
        self.assertEqual([(r['disposition'], r['reference']) for r in self.doc(wave)['reviews']],
                         [(None, None), (None, None)])
        template = self.ok('init', '--template', 'wave')['spec']['reviews']
        self.assertIn('disposition: default null', template)


class Resources(Campaign):
    def test_R03_04_outcome_resources_must_be_strings(self):
        spec = dict(PROGRAM_SPEC, outcomes=[dict(PROGRAM_SPEC['outcomes'][0], resources=[{'name': 'db'}, 42])])
        program, code, result = self.init('prog', 'program', spec)
        self.assertEqual(code, 1, result)
        self.assertIn('A: resources must be a list of strings, got list with object at [0]', result['error'])


class ActorEvidence(Campaign):
    def test_R03_05_actor_requalification_needs_new_evidence(self):
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'l1',
                '--op', 'launch', '--target', 'champion-A')
        self.ok('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1, '--correlation', 'l1',
                '--status', 'confirmed', '--result-ref', 'task-1', '--role', 'champion')

        def requalify(rev, value):
            return self.ops(self.wave_path, rev, [{'op': 'update', 'path': 'actors', 'match': {'correlation': 'l1'},
                                                   'value': value}])

        code, result = requalify(2, {'status': 'completed'})
        self.assertEqual(code, 1, result)
        self.assertIn('actor l1: running -> completed needs its evidence', result['error'])
        self.assertEqual(requalify(2, {'status': 'waiting', 'evidence': 'task_status=waiting'})[0], 0)
        code, result = requalify(3, {'status': 'completed'})
        self.assertEqual(code, 1, result)
        self.assertIn('needs its evidence', result['error'])
        self.assertEqual(requalify(3, {'status': 'completed', 'evidence': 'delivered report r.md'})[0], 0)
        self.assertEqual(self.doc(self.wave_path)['actors'][0]['status'], 'completed')


class Journal(Campaign):
    def test_R02_01_contradictory_closures_in_one_journal_refused(self):
        wave = self.solo()
        prepare = self.journal(wave)[0]
        with (wave.parent / 'journal.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'id': 'conflict', 'kind': 'resolve', 'resolves': prepare['id'],
                                     'wave': prepare['wave'], 'outcome': 'not_committed', 'actor': OWNER}) + '\n')
        before = (wave.parent / 'journal.jsonl').read_bytes()
        self.refused('contradictory closures', 'reconcile', wave, '--actor', OWNER, '--op', prepare['id'],
                     '--evidence', 'synthetic contradiction')
        self.assertEqual((wave.parent / 'journal.jsonl').read_bytes(), before)

    def test_R02_02_journal_without_final_line_feed_stays_readable(self):
        wave = self.solo()
        jpath = wave.parent / 'journal.jsonl'
        jpath.write_bytes(jpath.read_bytes().rstrip(b'\n'))
        self.ok('write', wave, '--actor', OWNER, '--expect-revision', 0, '--ops',
                json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'after repair'}]))
        lines = jpath.read_bytes().split(b'\n')
        self.assertEqual(lines[-1], b'')
        self.assertEqual([json.loads(line)['kind'] for line in lines[:-1]], ['prepare', 'init', 'prepare', 'write'])

    def test_R02_03_and_R03_06_unusable_line_reported_by_number(self):
        for name, damage, fragment in (('utf8', b'\xff\n', 'line 3 is not valid UTF-8'),
                                       ('array', b'[]\n', 'line 3 is a JSON list, not an entry object')):
            with self.subTest(damage=damage):
                wave, code, result = self.init(name, 'wave', WAVE_SPEC)
                with (wave.parent / 'journal.jsonl').open('ab') as stream:
                    stream.write(damage)
                result = self.refused(fragment, 'write', wave, '--actor', OWNER, '--expect-revision', 0, '--ops',
                                      json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'x'}]))
                self.assertIn('move the damaged line aside', result['error'])
                self.assertEqual(self.doc(wave)['revision'], 0)


class Phases(Campaign):
    def test_R07_01_wait_entered_from_planning_resumes_to_preparing(self):
        wave = self.solo()
        self.ok('transition', wave, '--actor', OWNER, '--expect-revision', 0, '--to', 'blocked', '--waiting-kind',
                'dependency', '--detail', 'input missing', '--trigger', 'input delivered', '--resume', 'prepare')
        self.assertIsNone(self.doc(wave)['state']['waiting']['from'])
        self.refused('resumes to preparing', 'transition', wave, '--actor', OWNER, '--expect-revision', 1,
                     '--to', 'planning')
        self.ok('transition', wave, '--actor', OWNER, '--expect-revision', 1, '--to', 'preparing')

    def test_wait_without_origin_cannot_resume_to_launched_unarmed(self):
        w = wave2('planning')
        w['state']['launch_ready'] = False
        self.write(self.wave_path, w)
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'blocked',
                '--waiting-kind', 'dependency', '--detail', 'input missing', '--trigger', 'input delivered',
                '--resume', 'prepare')
        self.refused('launch_ready', 'transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1,
                     '--to', 'launched')
        self.assertEqual(self.doc(self.wave_path)['state']['phase'], 'blocked')


class Help(Campaign):
    def test_command_help_gives_a_complete_example(self):
        expected = {'transition': ('transition FILE --actor A --expect-revision N --to preparing',),
                    'ack': ('ack FILE --actor A --expect-revision N --id task-1:run-1',),
                    'claim': ('claim FILE --actor A --role pilot --expect-revision N',),
                    'event': ('event FILE --actor A --id task-1:run-1 --kind review', 'no --expect-revision')}
        for command, fragments in expected.items():
            with self.subTest(command=command):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                    rc.main([command, '--help'])
                for fragment in fragments:
                    self.assertIn(fragment, out.getvalue())


if __name__ == '__main__':
    unittest.main()
