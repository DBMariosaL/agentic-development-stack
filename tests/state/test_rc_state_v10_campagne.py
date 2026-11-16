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
        for role in ('champion', 'Superviseur', 'integrator-B', 'builder', 'reviewer-champion', 'legacy'):
            with self.subTest(role=role):
                self.refused(f"live actor with role '{role}' in a wave without launch authorization",
                             *resolve, '--role', role)
        with self.subTest(role=None):
            self.refused("live actor with role 'unspecified' in a wave without launch authorization", *resolve)
        done = [{'op': 'update', 'path': 'actors', 'match': {'correlation': 'l1'},
                 'value': {'status': 'completed', 'evidence': 'report r.md'}}]
        self.refused("actor l1: role 'champion' refused in a wave without launch authorization", 'write', wave,
                     '--actor', OWNER, '--expect-revision', 1, '--resolve-intent', 'l1', '--status', 'confirmed',
                     '--result-ref', 'task-1', '--role', 'champion', '--ops', json.dumps(done))
        self.assertEqual((self.doc(wave)['revision'], self.doc(wave)['actors']), (1, []))
        self.ok(*resolve, '--role', 'Reviewer')
        self.assertEqual([(a['role'], a['status']) for a in self.doc(wave)['actors']], [('Reviewer', 'running')])

    def test_R01_03_live_champion_invalid_once_authorization_is_withdrawn(self):
        w = wave2()
        w['actors'] = [{'role': 'champion', 'model': None, 'ref': 'task-1', 'correlation': 'l1',
                        'status': 'running', 'target': 'A'}]
        self.write(self.wave_path, w)
        self.assertEqual(self.ok('check', self.wave_path)['errors'], [])
        self.refused("live actor with role 'champion' in a wave without launch authorization", 'write',
                     self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops',
                     json.dumps([{'op': 'set', 'path': 'authorization.launch', 'value': False}]))

    def test_authorized_wave_runs_only_documentary_reviews_before_launched(self):
        self.write(self.wave_path, wave2('preparing'))
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'l1',
                '--op', 'launch', '--target', 'A')
        resolve = ('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1,
                   '--correlation', 'l1', '--status', 'confirmed', '--result-ref', 'task-1')
        self.refused("live actor with role 'champion' in a wave not launched yet (phase preparing)",
                     *resolve, '--role', 'champion')
        self.ok(*resolve, '--role', 'reviewer')
        champion = {'role': 'champion', 'model': None, 'ref': 'task-2', 'correlation': 'l2', 'status': 'running',
                    'target': 'B'}
        wait = {'kind': 'quota', 'detail': 'rate limit', 'trigger': 'capacity', 'resume': 'resume'}
        for phase, origin, valid in (('ready', None, False), ('waiting_quota', 'preparing', False),
                                     ('launched', None, True), ('waiting_quota', 'launched', True)):
            with self.subTest(phase=phase, origin=origin):
                w = wave2(phase)
                w['actors'] = [champion]
                if origin:
                    w['state']['waiting'] = dict(wait, **{'from': origin})
                self.write(self.wave_path, w)
                code, result = self.run_cli('check', self.wave_path)
                self.assertEqual(code == 0, valid, result)
                if not valid:
                    self.assertIn(f'not launched yet (phase {phase})', ' '.join(result['errors']))

    def test_unnamed_live_actor_of_an_older_prepare_wave_is_refused_then_closed_by_write(self):
        w = wave2('planning')
        w.update(mode='prepare', program_ref=None, authorization=dict(w['authorization'], launch=False))
        w['actors'] = [{'role': 'unspecified', 'model': None, 'ref': 'task-1', 'correlation': 'l1',
                        'status': 'running', 'target': 'A'}]
        self.write(self.wave_path, w)
        code, result = self.run_cli('check', self.wave_path)
        self.assertEqual(code, 1, result)
        self.assertIn("actors[0]: live actor with role 'unspecified'", ' '.join(result['errors']))
        self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', json.dumps(
            [{'op': 'update', 'path': 'actors', 'match': {'correlation': 'l1'},
              'value': {'status': 'interrupted', 'evidence': 'task_status=interrupted'}}]))
        self.assertEqual(self.ok('check', self.wave_path)['errors'], [])

    def test_migrated_legacy_actor_stays_valid_in_a_prepare_wave(self):
        source = self.root / 'v1.json'
        v1 = wave2('preparing')
        v1.update(schema_version=1, mode='prepare', authorization=dict(v1['authorization'], launch=False))
        for key in ('revision', 'program_ref', 'candidate', 'envelope', 'actors', 'intents'):
            v1.pop(key)
        v1['state'].pop('waiting')
        v1['state']['runtime_refs'] = ['task-old']
        self.write(source, v1)
        dest = self.root / 'migrated.json'
        self.ok('migrate', source, dest)
        doc = self.doc(dest)
        self.assertEqual([(a['role'], a['status'], a['correlation']) for a in doc['actors']],
                         [('legacy', 'unknown', 'legacy/0')])
        self.assertEqual(self.ok('check', dest)['errors'], [])
        doc['actors'][0]['ref'] = 'task-other'
        self.write(dest, doc)
        code, result = self.run_cli('check', dest)
        self.assertEqual(code, 1, result)
        self.assertIn("live actor with role 'legacy'", ' '.join(result['errors']))


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

    def test_closed_wave_keeps_passing_check_paths_when_a_reviewed_document_changed(self):
        for phase, errors in (('launched', 1), ('stopped', 0)):
            with self.subTest(phase=phase):
                w = wave2(phase)
                w['artifacts']['doc'] = 'doc.txt'
                w['reviews'].append({'artifact': 'doc', 'sha256': 'a' * 64, 'status': 'done',
                                     'disposition': 'reviewed', 'reference': 'report.md'})
                self.write(self.wave_path, w)
                (self.wave_path.parent / 'doc.txt').write_bytes(b'changed after review')
                code, result = self.run_cli('check', self.wave_path, '--check-paths')
                self.assertEqual(len([e for e in result['errors'] if 'documentary review' in e]), errors, result)

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
                                       ('array', b'[]\n', 'line 3 is a JSON list, not an entry object'),
                                       ('noid', b'{"kind": "event:review", "wave": "wave.json"}\n',
                                        'line 3 has no text id (got missing)'),
                                       ('listid', b'{"id": ["x"], "kind": "event:review"}\n',
                                        'line 3 has no text id (got list)'),
                                       ('commits', b'{"id": "w", "kind": "write", "commits": ["op"]}\n',
                                        'line 3 has malformed fields: commits (list)')):
            with self.subTest(damage=damage):
                wave, code, result = self.init(name, 'wave', WAVE_SPEC)
                with (wave.parent / 'journal.jsonl').open('ab') as stream:
                    stream.write(damage)
                result = self.refused(fragment, 'write', wave, '--actor', OWNER, '--expect-revision', 0, '--ops',
                                      json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'x'}]))
                self.assertIn('move the damaged line aside', result['error'])
                self.assertEqual(self.doc(wave)['revision'], 0)


    def test_event_without_id_reported_by_number_by_every_reader(self):
        with (self.root / 'journal.jsonl').open('ab') as stream:
            stream.write(b'{"kind": "event:review", "wave": "waves/a/wave.json"}\n')
        argvs = (('event', self.wave_path, '--actor', OWNER, '--id', EVENT, '--kind', 'review'),
                 ('resume', self.program_path),
                 ('ack', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--id', EVENT),
                 ('reconcile', self.wave_path, '--actor', OWNER, '--op', 'op:none', '--evidence', 'check'))
        for argv in argvs:
            with self.subTest(command=argv[0]):
                result = self.refused('line 1 has no text id', *argv)
                self.assertIn('move the damaged line aside', result['error'])
                self.assertNotIn('internal', result)


class MalformedState(Campaign):
    def test_malformed_fields_refused_by_name_without_internal_error(self):
        blocked = {'kind': 'dependency', 'detail': 'd', 'trigger': 't', 'resume': 'r'}
        cases = (('state.owner', 'thread:x', 'owner is malformed (got str',
                  ('write', '--actor', OWNER, '--expect-revision', 0, '--ops',
                   json.dumps([{'op': 'set', 'path': 'state.next_action', 'value': 'n'}]))),
                 ('state.owner', ['x'], 'owner is malformed (got list',
                  ('event', '--actor', OWNER, '--id', EVENT, '--kind', 'review')),
                 ('intents', {'c': 1}, 'intents must be a list, got object',
                  ('intent', 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'c',
                   '--op', 'send', '--target', 'T')),
                 ('state.waiting', 'from launched', 'refused',
                  ('transition', '--actor', OWNER, '--expect-revision', 0, '--to', 'launched')),
                 ('candidate.seq', 'one', None,
                  ('event', '--actor', OWNER, '--id', EVENT, '--kind', 'review', '--candidate-seq', 1)),
                 ('actors', 'none', 'actors must be a list, got str',
                  ('intent', 'resolve', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'p1',
                   '--status', 'confirmed', '--result-ref', 'task-1', '--role', 'reviewer')),
                 ('state', 'broken', 'state must be an object, got str',
                  ('claim', '--actor', 'other', '--role', 'pilot', '--expect-revision', 0, '--takeover',
                   '--evidence', 'stop confirmed')))
        for field, value, fragment, argv in cases:
            with self.subTest(field=field, command=argv[0]):
                w = wave2('blocked')
                w['state']['waiting'] = dict(blocked, **{'from': 'launched'})
                w['candidate'] = {'seq': 1, 'ref': 'm1', 'artifact': 'manifest', 'sha256': 'a' * 64}
                w['intents'] = [{'correlation': 'p1', 'op': 'launch', 'target': 'T1', 'status': 'pending',
                                 'result_ref': None}]
                node, *keys = field.split('.')
                if keys:
                    w[node][keys[0]] = value
                else:
                    w[node] = value
                self.write(self.wave_path, w)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                head, rest = argv[0], argv[1:]
                if head == 'intent':
                    head, rest = ('intent', rest[0]), rest[1:]
                else:
                    head = (head,)
                code, result = self.run_cli(head[0], self.wave_path, *head[1:], *rest)
                self.assertNotIn('internal', result)
                if fragment is None:
                    self.assertEqual((code, result['classification']), (0, 'new'), result)
                else:
                    self.assertEqual(code, 1, result)
                    self.assertIn(fragment, result['error'])

    def test_malformed_owner_recorded_again_by_claim_takeover(self):
        w = wave2()
        w['state']['owner'] = 'thread:x'
        self.write(self.wave_path, w)
        claim = ('claim', self.wave_path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', 0)
        self.refused('takeover requires --takeover and --evidence', *claim)
        self.ok(*claim, '--takeover', '--evidence', 'owner field hand-edited; previous pilot stopped')
        self.assertEqual(self.doc(self.wave_path)['state']['owner'], {'role': 'pilot', 'ref': OWNER})
        self.assertEqual(self.journal(self.program_path)[-1]['kind'], 'claim')


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
