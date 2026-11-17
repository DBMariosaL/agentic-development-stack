"""Defects reproduced by the v10 campaign, each checked at command level."""
import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from test_rc_state import OWNER, SCRIPT, Base, rc, wave2
from test_rc_state import program as rc_program

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

    def pending_intent(self, path):
        self.ok('intent', path, 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'c1',
                '--op', 'write', '--target', 'T')

    def received(self, path):
        return [e['id'] for e in self.journal(path) if e.get('kind', '').startswith('event:')]

    def applied(self, path):
        return [e['applies_event'] for e in self.journal(path) if e.get('applies_event')]


class ShortForm(Campaign):
    def test_R13_01_invalid_ops_json_keeps_the_signal_received(self):
        wave = self.solo()
        self.pending_intent(wave)
        before = wave.read_bytes()
        code, result = self.short(wave, 1, '--ops', '[')
        self.assertEqual(code, 1, result)
        self.assertIn('not valid JSON', result['error'])
        self.assertIn(f'event {EVENT} is recorded and stays unapplied', result['error'])
        self.assertEqual(wave.read_bytes(), before)
        self.assertEqual((self.received(wave), self.applied(wave)), ([EVENT], []))

    def test_R13_02_ops_cannot_reopen_the_intent_just_resolved(self):
        wave = self.solo()
        self.pending_intent(wave)
        reopen = [{'op': 'update', 'path': 'intents', 'match': {'correlation': 'c1'},
                   'value': {'status': 'pending', 'result_ref': None}}]
        code, result = self.short(wave, 1, '--ops', json.dumps(reopen))
        self.assertEqual(code, 1, result)
        self.assertIn('intent c1 changes only through intent resolve or write --resolve-intent', result['error'])
        self.assertEqual(self.doc(wave)['revision'], 1)
        self.assertEqual(self.applied(wave), [])
        code, result = self.short(wave, 1)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['event']['classification'], 'unapplied')
        self.assertEqual(self.doc(wave)['intents'][0]['status'], 'confirmed')
        self.assertEqual(self.applied(wave), [EVENT])

    def test_R13_03_failure_after_prepare_reports_uncertain_not_rerun(self):
        wave = self.solo()
        self.pending_intent(wave)
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
        requalified = [{'op': 'update', 'path': 'actors', 'match': {'correlation': 'l1'},  # R01-08
                        'value': {'status': 'completed', 'evidence': 'task read', 'role': 'champion'}}]
        self.refused("actor l1: role 'champion' refused in a wave without launch authorization", 'write', wave,
                     '--actor', OWNER, '--expect-revision', 2, '--ops', json.dumps(requalified))

    def test_R01_07_intent_confirmed_only_by_the_path_that_records_or_revives_its_actor(self):
        """R01-07, R03-04 (launch without actor), E01 (send leaving its actor completed): ops never resolve an intent."""
        done = {'role': 'reviewer', 'model': None, 'ref': 'thread-1', 'correlation': 'r1', 'status': 'completed',
                'target': 'cible', 'evidence': 'returned'}
        for op, actors in (('launch', []), ('send', [done])):
            with self.subTest(op=op):
                w = wave2('planning')
                w.update(actors=actors, intents=[{'correlation': 'k1', 'op': op, 'target': 'cible',
                                                  'status': 'pending', 'result_ref': None}])
                self.write(self.wave_path, w)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                confirm = [{'op': 'update', 'path': 'intents', 'match': {'correlation': 'k1'},
                            'value': {'status': 'confirmed', 'result_ref': 'thread-2'}}]
                self.refused('intent k1 changes only through intent resolve or write --resolve-intent', 'write', self.wave_path, '--actor', OWNER,
                             '--expect-revision', 0, '--ops', json.dumps(confirm))
                self.assertEqual(self.doc(self.wave_path)['revision'], 0)

    def test_P05_confirmed_send_makes_the_actor_it_reaches_alive_again(self):
        champion = {'role': 'champion', 'model': None, 'ref': 'agent-1', 'correlation': 'champ/1',
                    'status': 'completed', 'target': 'copies/import', 'evidence': 'round 1 handed back'}
        for phase, actors, fragment in (('launched', [champion], None),
                                        ('preparing', [champion], "live actor with role 'champion'"),
                                        ('launched', [], 'reaches no recorded actor')):
            with self.subTest(phase=phase, actors=len(actors)):
                w = wave2(phase)
                w['actors'] = actors
                w['intents'] = [{'correlation': 'champ/2', 'op': 'send', 'target': 'copies/import',
                                 'status': 'pending', 'result_ref': None}]
                self.write(self.wave_path, w)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                argv = ('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 0,
                        '--correlation', 'champ/2', '--status', 'confirmed', '--result-ref', 'message-896093')
                if fragment:
                    self.refused(fragment, *argv)
                else:
                    self.ok(*argv)
                    actor = self.doc(self.wave_path)['actors'][0]
                    self.assertEqual((actor['status'], actor['evidence']),
                                     ('running', 'send champ/2 confirmed: message-896093'))

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
                                     ('waiting_quota', None, False),
                                     ('launched', None, True), ('waiting_quota', 'launched', True)):
            with self.subTest(phase=phase, origin=origin):
                w = wave2(phase)
                w['actors'] = [champion]
                if phase in rc.WAITLIKE:
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
        for phase, errors in (('launched', 3), ('stopped', 0)):  # R02-10: consumed mandate and its review too
            with self.subTest(phase=phase):
                w = wave2(phase)
                w['artifacts']['doc'] = 'doc.txt'
                for name in ('doc', 'prompt_a'):
                    w['reviews'].append({'artifact': name, 'sha256': 'a' * 64, 'status': 'done',
                                         'disposition': 'reviewed', 'reference': 'report.md'})
                self.write(self.wave_path, w)
                (self.wave_path.parent / 'doc.txt').write_bytes(b'changed after review')
                (self.wave_path.parent / 'socles').mkdir(exist_ok=True)
                (self.wave_path.parent / 'socles/a.txt').write_bytes(b'mandate changed after closure')
                code, result = self.run_cli('check', self.wave_path, '--check-paths')
                self.assertEqual(len([e for e in result['errors'] if 'documentary review' in e
                                      or 'sha256 mismatch' in e]), errors, result)

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
    def test_R03_05_actor_requalification_needs_its_own_new_evidence(self):
        """R03-05; v10.2 review round 3, A3-01 (evidence found elsewhere) and A3-02 (an applied event exempted)."""
        actor_b = {'role': 'reviewer', 'model': None, 'ref': 'thread-B', 'correlation': 'b1', 'status': 'completed',
                   'target': 'B', 'evidence': 'B returned report b.md'}
        update = 'actors', {'correlation': 'l1'}
        cases = (('no evidence', {'status': 'completed'}, ()),
                 ('copied from another actor', {'status': 'completed', 'evidence': 'B returned report b.md'}, ()),
                 ('carried by an intent', {'status': 'completed', 'evidence': 'message m1 delivered'}, ()),
                 ('own earlier evidence', {'status': 'completed', 'evidence': 'started on task-1'}, ()),
                 ('applied event instead', {'status': 'completed'}, ('--applies-event', 'thread-B/run-2')),
                 ('shared with another actor of the write', {'status': 'completed', 'evidence': 'one proof'}, ()),
                 ('new', {'status': 'completed', 'evidence': 'delivered report r.md'}, None))
        for label, value, extra in cases:
            with self.subTest(label):
                w = wave2()
                w['actors'] = [actor_b, {'role': 'champion', 'model': None, 'ref': 'task-1', 'correlation': 'l1',
                                         'status': 'running', 'target': 'A', 'evidence': 'started on task-1'}]
                w['intents'] = [{'correlation': 'm1', 'op': 'send', 'target': 'B', 'status': 'confirmed',
                                 'result_ref': None, 'evidence': 'message m1 delivered'}]
                self.write(self.wave_path, w)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'thread-B/run-2', '--kind', 'completed')
                ops = [{'op': 'update', 'path': update[0], 'match': update[1], 'value': value}]
                if label.startswith('shared'):
                    ops.insert(0, {'op': 'update', 'path': 'actors', 'match': {'correlation': 'b1'},
                                   'value': {'status': 'interrupted', 'evidence': 'one proof'}})
                argv = ('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', json.dumps(ops),
                        *(extra or ()))
                if extra is None:
                    self.ok(*argv)
                else:
                    self.refused('actor l1: running -> completed needs its own new evidence', *argv)
                    self.assertEqual(self.doc(self.wave_path)['revision'], 0)


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


class StrictInputs(Campaign):
    def test_values_the_format_does_not_allow_are_refused_before_any_write(self):
        """R13-03, R01-04, R13-04, R01-13, R01-12, R03-09, R01-10, R03-08, R01-09, init launch_ready 0."""
        (self.root / 'null.json').write_text('null', encoding='utf-8')
        w = wave2('launched')
        w['candidate'] = {'seq': 1, 'ref': 'm1', 'artifact': 'manifest', 'sha256': 'b' * 64}
        w['reviews'] = [{'artifact': 'manifest', 'sha256': 'b' * 64, 'status': 'done', 'disposition': 'ok',
                         'reference': 'r.md', 'candidate_seq': 1}]
        w['decisions'] = []
        mandate = dict(PROGRAM_SPEC['mandate'], sha256='not-a-digest')
        auth = {'launch': True, 'exclusions': []}
        cases = (
            ('event blank id', 'has no text id', ('event', self.wave_path, '--actor', OWNER, '--id', ' ', '--kind', 'k')),
            ('short form blank id', 'has no text id', ('write', self.wave_path, '--actor', OWNER, '--expect-revision',
                                                       0, '--ops', '[]', '--record-event', '  ', '--kind', 'k')),
            ('ops null', 'ops must be a nonempty list, got null',
             ('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', 'null')),
            ('ops file null', 'ops must be a nonempty list, got null',
             ('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops-file', self.root / 'null.json')),
            ('ops NaN', 'NaN is not JSON', ('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops',
                                             '[{"op":"set","path":"envelope","value":{"reason":"r","max":NaN}}]')),
            ('completed_partial without decision', 'completed_partial requires the unqualified scope named in decisions',
             ('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'completed_partial')),
            ('scope removed in a wait after launch (R01-10 b)', 'operational state requires a declared authorization.scope',
             ('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops',
              '[{"op":"set","path":"authorization.scope","value":null}]'), 'launched'))
        for label, fragment, argv, *origin in cases:
            with self.subTest(label):
                fixture = copy.deepcopy(w)
                if origin:  # the same wave, waiting after its launch
                    fixture['state'].update(phase='waiting_children', waiting={
                        'kind': 'children', 'detail': 'd', 'trigger': 't', 'resume': 'r', 'from': origin[0]})
                self.write(self.wave_path, fixture)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                self.refused(fragment, *argv)
                self.assertEqual(self.doc(self.wave_path)['revision'], 0)
                self.assertFalse((self.root / 'journal.jsonl').exists())
        for label, fragment, kind, spec in (
                ('mandate.sha256', 'mandate.sha256: expected 64 hex characters or absent, got str', 'program',
                 dict(PROGRAM_SPEC, mandate=mandate)),
                ('launch without source', 'authorization.source: expected nonempty text when authorization.launch is '
                 'true, got null', 'wave', dict(WAVE_SPEC, mode='prepare-and-launch', authorization=auth)),
                ('launch_ready 0', 'init sets these fields itself; remove them from the spec: state.launch_ready',
                 'wave', dict(WAVE_SPEC, state={'next_action': 'x', 'launch_ready': 0}))):
            with self.subTest(label):
                path, code, result = self.init(label.replace(' ', '-'), kind, spec)
                self.assertEqual(code, 1, result)
                self.assertIn(fragment, result['error'])
                self.assertFalse(path.exists())


class Messages(Campaign):
    """What a command says is what happened, and what it advises is a command that converges."""

    def test_R13_05_a_resolved_intent_is_refused_even_within_the_same_second(self):
        wave = self.solo()
        self.pending_intent(wave)
        resolve = ('intent', wave, 'resolve', '--actor', OWNER, '--correlation', 'c1', '--status', 'confirmed',
                   '--result-ref', 'task-7')
        with mock.patch.object(rc, 'now', return_value='2026-11-17T00:00:00+00:00'):
            self.ok(*resolve[:3], '--expect-revision', 1, *resolve[3:])
            self.refused('intent c1 is resolved and immutable (confirmed)', *resolve[:3], '--expect-revision', 2,
                         *resolve[3:])
        self.assertEqual(self.rev(wave), 2)

    def test_R13_06_candidate_seq_given_for_an_event_already_received(self):
        w = wave2()
        w['candidate'] = {'seq': 2, 'ref': 'm2', 'artifact': 'manifest', 'sha256': 'b' * 64}
        for received, given, outcome in ((None, 1, 'stale'), (2, 1, 'was received for candidate_seq 2, not 1')):
            with self.subTest(received=received):
                self.write(self.wave_path, w)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'ev1', '--kind', 'done',
                        *(('--candidate-seq', received) if received else ()))
                code, result = self.run_cli('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                                            '--ops', '[{"op":"set","path":"state.next_action","value":"x"}]',
                                            '--record-event', 'ev1', '--kind', 'done', '--candidate-seq', given)
                self.assertEqual(code, 1, result)
                self.assertIn(outcome, json.dumps(result))
                self.assertEqual(self.rev(self.wave_path), 0)

    def test_R13_07_R13_08_short_form_reports_what_happened_to_its_event(self):
        wave = self.solo()
        self.pending_intent(wave)
        code, result = self.short(wave, 1)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['event']['applied'], result['event']['effect']),
                         (True, 'applied by this write (revision 2)'))
        w = wave2('launched')  # an event received, then the wave closed before applying it
        w['intents'] = [{'correlation': 'c1', 'op': 'send', 'target': 'T', 'status': 'absent', 'result_ref': None}]
        self.write(self.wave_path, w)
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', EVENT, '--kind', 'return')
        w['state']['phase'] = 'stopped'
        self.write(self.wave_path, w)
        before = self.wave_path.read_bytes()
        code, result = self.run_cli('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                                    '--ops', '[{"op":"set","path":"state.next_action","value":"x"}]',
                                    '--record-event', EVENT, '--kind', 'return')
        self.assertEqual((code, result['written']), (1, None), result)
        self.assertIn('record its disposition with dispose', result['event']['effect'])
        self.assertEqual(self.wave_path.read_bytes(), before)

    def test_R07_05_R03_07_type_refusals_name_the_received_type(self):
        program_cases = (('last_milestone', 'jalon', 'last_milestone: expected object {at, summary, ref}, got str'),
                         ('decisions_pending', 'x', 'decisions_pending: expected list of objects, got str'),
                         ('decisions_pending', [{'id': 'D1', 'question': 'q', 'option': 'o', 'effects': 'e',
                                                 'suspends': 'A'}],
                          'decisions_pending[0].suspends: expected list of known outcome ids, empty when it suspends '
                          'nothing, got str'),
                         ('outcomes', 'A', 'outcomes: expected nonempty list of objects, got str'),
                         ('outcomes.0.depends_on', 'B', 'A: depends_on: expected list of known outcome ids, got str'),
                         ('outcomes.0.waiting_on', 'quota', 'outcomes.A.waiting_on: expected object {kind, detail, '
                          'trigger}, got str'),
                         ('outcomes.1.id', 5, 'outcomes[1].id: expected nonempty text, got int'))
        wave_cases = (('envelope', 3, 'envelope: expected object {reason}, got int'),
                      ('candidate', 'abc', 'candidate: expected object {seq, ref, artifact, sha256}, got str'),
                      ('socles.0.readiness', 'bad', "A: invalid readiness: expected one of blocked, partial, ready, "
                       "got 'bad'"),
                      ('socles.0.resources', 'x', 'A: resources must be a list, got str'),
                      ('artifacts', {'a': 5}, 'a: local relative artifact path required (no escape), got int'))
        for path, make, cases in ((self.program_path, rc_program, program_cases), (self.wave_path, wave2, wave_cases)):
            for field, value, fragment in cases:
                with self.subTest(field=field):
                    doc, (head, *rest) = make(), field.split('.')
                    if rest:
                        doc[head][int(rest[0])][rest[1]] = value
                    else:
                        doc[head] = value
                    self.write(path, doc)
                    code, result = self.run_cli('check', path)
                    self.assertIn(fragment, result['errors'])

    def test_R02_08_event_follows_an_attachment_made_while_it_waited(self):
        wave = self.solo()
        p = rc_program()
        p['outcomes'][0]['state_ref'] = 'solo/wave.json'
        self.write(self.program_path, p)
        real, done = rc.journal_path, []

        def attach_meanwhile(path, doc):
            if not done:
                done.append(None)
                done[0] = (self.run_cli('write', wave, '--actor', OWNER, '--expect-revision', 0, '--ops',
                                         '[{"op":"set","path":"program_ref","value":"../program.json"}]'))
            return real(path, doc)
        with mock.patch.object(rc, 'journal_path', side_effect=attach_meanwhile):
            self.assertEqual(self.ok('event', wave, '--actor', OWNER, '--id', EVENT, '--kind', 'review')
                             ['classification'], 'new')
        self.assertEqual(done[0][0], 0, done)
        self.assertIn(EVENT, [e['id'] for e in self.journal(self.program_path)])
        self.assertNotIn(EVENT, [e['id'] for e in self.journal(wave)])

    def test_R02_09_two_prepare_lines_of_one_operation_that_differ_are_refused(self):
        wave = self.solo()
        with mock.patch.object(rc.os, 'replace', side_effect=OSError('stopped')):
            self.ops(wave, 0, [{'op': 'set', 'path': 'state.next_action', 'value': 'next'}])
        journal = wave.parent / 'journal.jsonl'
        intact = journal.read_bytes()
        prepare = [e for e in self.journal(wave) if e['kind'] == 'prepare'][-1]
        for label, change in (('digests', {'old_sha256': '0' * 64,
                                           'new_sha256': hashlib.sha256(wave.read_bytes()).hexdigest()}),
                              ('author', {'actor': 'thread:someone-else'})):
            with self.subTest(label):
                journal.write_bytes(intact + (json.dumps(dict(prepare, **change)) + '\n').encode('utf-8'))
                self.refused('has prepare lines that differ (between or within journals)', 'reconcile', wave,
                             '--actor', OWNER, '--op', prepare['id'], '--evidence', 'bytes')

    def test_resume_lists_local_events_and_advises_commands_that_converge(self):
        """R02-07, R03-03 (local journal of a referenced detached wave), R03-10 (stale), R03-06 (closed v1)."""
        w = wave2('preparing')
        w['program_ref'] = None
        w['candidate'] = {'seq': 1, 'ref': 'm1', 'artifact': 'manifest', 'sha256': 'b' * 64}
        self.write(self.wave_path, w)
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'old-review', '--kind', 'review',
                '--candidate-seq', 1)
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'task-1:run-1', '--kind', 'review')
        w['candidate'] = dict(w['candidate'], seq=2)
        self.write(self.wave_path, w)
        v1 = self.root / 'old/wave.json'
        v1.parent.mkdir()
        legacy = wave2('completed')
        for key in ('revision', 'program_ref', 'candidate', 'envelope', 'actors', 'intents'):
            legacy.pop(key)
        legacy.update(schema_version=1)
        legacy['state']['runtime_refs'] = ['thread-1']
        self.write(v1, legacy)
        p = rc_program()
        p['outcomes'][1].update(status='accepted', depends_on=[], state_ref='old/wave.json')
        self.write(self.program_path, p)
        result = self.run_cli('resume', self.program_path)[1]
        self.assertEqual(sorted(e['id'] for e in result['unapplied_events']), ['old-review', 'task-1:run-1'])
        actions = ' | '.join(result['actions'])
        self.assertIn('event task-1:run-1 (event:review) for waves/a/wave.json was received but never applied', actions)
        self.assertIn(f'record it as stale with event {self.wave_path.resolve()} --actor <owner> --id old-review '
                      '--kind review', actions)
        self.assertNotIn('migrate', actions)


class Windows(Campaign):
    def test_R01_06_output_is_utf8_whatever_the_console_encoding(self):
        folder = self.root / 'vague_Ω'
        folder.mkdir()
        (folder / 'spec.json').write_text(json.dumps(dict(WAVE_SPEC, state={'next_action': 'lot B1 → B2'})),
                                          encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if k not in ('PYTHONUTF8', 'PYTHONIOENCODING')}
        env['PYTHONIOENCODING'] = 'ascii'  # a code page without these characters
        done = subprocess.run([sys.executable, '-B', str(SCRIPT), 'init', str(folder / 'wave.json'), '--kind', 'wave',
                               '--actor', OWNER, '--role', 'pilot', '--spec', str(folder / 'spec.json')],
                              capture_output=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(json.loads(done.stdout.decode('utf-8'))['written'].endswith('wave.json'))

    def test_state_replacement_retries_a_transient_permission_error(self):
        wave = self.solo()
        real, calls = rc.os.replace, []

        def busy_once(source, target):
            calls.append(target)
            if len(calls) == 1:
                raise PermissionError('a reader holds the file')
            return real(source, target)
        with mock.patch.object(rc.os, 'replace', side_effect=busy_once):
            self.assertEqual(self.ops(wave, 0, [{'op': 'set', 'path': 'state.next_action', 'value': 'n'}])[0], 0)
        self.assertEqual((len(calls), self.rev(wave)), (2, 1))


class ReadyView(Campaign):
    def test_P04_every_open_outcome_is_listed_with_what_it_waits_for(self):
        spec = dict(PROGRAM_SPEC, outcomes=[{'id': 'R1', 'outcome': 'o', 'next_action': 'n'},
                                            {'id': 'R2', 'outcome': 'o', 'next_action': 'n', 'depends_on': ['R1']},
                                            {'id': 'R3', 'outcome': 'o', 'next_action': 'n', 'depends_on': ['R1']},
                                            {'id': 'R4', 'outcome': 'o', 'next_action': 'n', 'status': 'failed',
                                             'closure': {'source': 'run failed', 'remaining': 'all'}}])
        path, code, result = self.init('index', 'program', spec)
        self.assertEqual(code, 0, result)
        view = self.ok('ready', path)
        self.assertEqual((view['ready'], view['admitted'], view['waiting'], view['blocked']),
                         (['R1'], [], {'R2': 'depends_on R1', 'R3': 'depends_on R1'}, ['R4']))


class Leads(Campaign):
    """Leads without replay script, corrected."""
    wait = ('--waiting-kind', 'quota', '--detail', 'rate limit', '--trigger', 'capacity back', '--resume', 'resume')

    def test_any_active_phase_can_wait_and_resumes_to_its_origin(self):
        for phase, origin, back in (('planning', None, 'preparing'), ('ready', 'ready', 'ready')):
            with self.subTest(phase=phase):
                w = wave2(phase)
                self.write(self.wave_path, w)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--to',
                        'waiting_quota', *self.wait)
                self.assertEqual(self.doc(self.wave_path)['state']['waiting']['from'], origin)
                self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--to', back)

    def test_new_blocker_before_launch_resets_launch_ready(self):
        w = wave2('ready')
        w['reviews'] = [{'artifact': 'prompt_a', 'sha256': 'a' * 64, 'status': 'done', 'disposition': 'ok',
                         'reference': 'r.md'}]
        w['state']['launch_ready'] = True
        self.write(self.wave_path, w)
        result = self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', json.dumps(
            [{'op': 'append', 'path': 'state.blockers', 'value': 'port taken'}]))
        self.assertEqual(result['launch_ready_reset']['changed'], ['state.blockers'])

    def test_state_refs_compared_as_the_platform_compares_paths(self):
        p = rc_program()
        p['outcomes'][1].update(status='admitted', depends_on=[], state_ref='waves/A/wave.json', resources=['port-1'])
        self.write(self.program_path, p)
        conflicts = self.run_cli('ready', self.program_path)[1]['resource_conflicts']
        self.assertEqual(len(conflicts), 0 if os.name == 'nt' else 1, conflicts)

    def test_role_and_model_only_with_a_confirmed_launch(self):
        wave = self.solo()
        self.pending_intent(wave)
        self.refused('--role and --model describe the actor of a confirmed launch', 'intent', wave, 'resolve',
                     '--actor', OWNER, '--expect-revision', 1, '--correlation', 'c1', '--status', 'confirmed',
                     '--result-ref', 'task-7', '--role', 'champion')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            rc.main(['intent', str(wave), 'add', '--actor', OWNER, '--expect-revision', '1', '--correlation', 'c2',
                     '--op', 'launch', '--target', 'B', '--role', 'champion'])


class LaunchReadyScope(Campaign):
    def test_R07_07_launch_ready_without_a_batch_names_batches(self):
        w = wave2('ready')
        w['batches'] = []
        self.write(self.wave_path, w)
        self.refused('a socle listed in batches', 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                     '--ops', json.dumps([{'op': 'set', 'path': 'state.launch_ready', 'value': True}]))


class Successor(Campaign):
    """A successor who has established the owner's stop always has a documented way on, named by resume."""
    OTHER = 'thread:successor'

    def takeover(self, path):
        return self.ok('claim', path, '--actor', self.OTHER, '--role', 'pilot', '--expect-revision', self.rev(path),
                       '--takeover', '--evidence', 'stop of the owner confirmed by the task list')

    def test_R02_01_stop_during_a_write_is_reconciled_by_its_bytes_then_taken_over(self):
        original = rc.append_journal

        def no_commit(path, entry):
            if entry.get('commits'):
                raise OSError('owner stopped before the commit line')
            return original(path, entry)
        for point, patch, outcome in (
                ('before replace', mock.patch.object(rc.os, 'replace', side_effect=OSError('stopped')), 'not_committed'),
                ('before commit', mock.patch.object(rc, 'append_journal', side_effect=no_commit), 'committed')):
            with self.subTest(point):
                self.write(self.wave_path, wave2())
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                with patch:
                    self.assertEqual(self.ops(self.wave_path, 0, [{'op': 'set', 'path': 'state.next_action',
                                                                   'value': 'next'}])[0], 1)
                code, cold = self.run_cli('resume', self.program_path)
                op = cold['uncertain_operations'][0]['id']
                self.assertTrue(any(f'run reconcile {self.wave_path.resolve()} --actor <you> --op {op}' in a
                                    for a in cold['actions']), cold['actions'])
                result = self.ok('reconcile', self.wave_path, '--actor', self.OTHER, '--op', op, '--evidence', 'bytes')
                self.assertEqual((result['outcome'], result['declared']), (outcome, False))
                self.takeover(self.wave_path)

    def test_R02_04_takeover_of_the_index_inside_the_closure_window(self):
        w = wave2('stopped')
        self.write(self.wave_path, w)
        window = 'A: contradictory state: outcome admitted but wave is stopped'
        code, cold = self.run_cli('resume', self.program_path)
        self.assertEqual(cold['consistency_errors'], [window])
        self.assertTrue(any('outcome A is still admitted' in a and 'claim --takeover' in a for a in cold['actions']))
        self.assertEqual(self.takeover(self.program_path)['consistency_errors'], [window])
        self.ok('write', self.program_path, '--actor', self.OTHER, '--expect-revision', 1, '--ops', json.dumps(
            [{'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'},
              'value': {'status': 'abandoned', 'closure': {'source': 'wave stopped', 'remaining': 'all'}}},
             {'op': 'set', 'path': 'status', 'value': 'stopped'}]))
        self.refused('takeover requires --takeover', 'claim', self.wave_path, '--actor', 'thread:third',
                     '--role', 'pilot', '--expect-revision', 0)  # a takeover still needs its evidence

    def test_R01_05_terminal_wave_of_a_stopped_owner_is_taken_over_then_disposed(self):
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'e1', '--kind', 'review')
        w = self.doc(self.wave_path)
        w['state']['phase'] = 'stopped'
        self.write(self.wave_path, w)
        code, cold = self.run_cli('resume', self.program_path)
        self.assertTrue(any('dispose' in a and 'e1' in a and 'claim --takeover' in a for a in cold['actions']))
        self.takeover(self.wave_path)
        self.assertEqual(self.doc(self.wave_path)['state']['phase'], 'stopped')
        self.ok('dispose', self.wave_path, '--actor', self.OTHER, '--id', 'e1', '--disposition', 'late',
                '--evidence', 'wave closed')
        self.assertEqual(self.ok('event', self.wave_path, '--actor', self.OTHER, '--id', 'e9',
                                 '--kind', 'review')['classification'], 'late')

    def test_P02_launch_proven_without_receipt_is_confirmed_in_one_command(self):
        w = wave2()
        w['intents'] = [{'correlation': 'champ/1', 'op': 'launch', 'target': 'A', 'status': 'pending',
                         'result_ref': None}]
        self.write(self.wave_path, w)
        resolve = ('write', self.wave_path, '--actor', self.OTHER, '--expect-revision', 1, '--resolve-intent',
                   'champ/1', '--status', 'confirmed', '--role', 'champion')
        self.takeover(self.wave_path)
        self.refused('confirmed intent requires result_ref, or an evidence of what was observed', *resolve)
        seen = 'commit 37b2549 on lot/count observed; its author stopped with its parent, no receipt'
        stopped = 'parent stopped on quota, no final message'
        self.ok(*resolve, '--evidence', seen, '--ops', json.dumps(
            [{'op': 'update', 'path': 'actors', 'match': {'correlation': 'champ/1'},
              'value': {'status': 'interrupted', 'evidence': stopped}}]))
        doc = self.doc(self.wave_path)
        self.assertEqual((doc['revision'], doc['intents'][0]['status'], doc['intents'][0]['result_ref'],
                          doc['intents'][0]['evidence']), (2, 'confirmed', None, seen))
        self.assertEqual([(a['ref'], a['status'], a['evidence']) for a in doc['actors']],
                         [(None, 'interrupted', stopped)])
        self.ok('intent', self.wave_path, 'add', '--actor', self.OTHER, '--expect-revision', 2, '--correlation',
                'champ/2', '--op', 'launch', '--target', 'A')

    def test_E01_R2_ops_of_the_short_form_are_judged_from_the_resolved_state(self):
        """v10.2 review, round 2: ops removing the actor a launch created, or undoing the revival of a send."""
        done = {'role': 'champion', 'model': None, 'ref': 'thread-1', 'correlation': 'l1', 'status': 'completed',
                'target': 'A', 'evidence': 'returned'}
        undo = [{'op': 'update', 'path': 'actors', 'match': {'correlation': 'l1'},
                 'value': {'status': 'completed', 'evidence': 'returned'}}]
        for op, actors, ops, fragment in (
                ('launch', [], [{'op': 'set', 'path': 'actors', 'value': []}], 'actor k1 removed'),
                ('send', [done], undo, 'actor l1: running -> completed needs its own new evidence'),
                ('send', [done], [dict(undo[0], value={'status': 'completed',
                                                       'evidence': 'send k1 confirmed: message-1'})],
                 'actor l1: running -> completed needs its own new evidence')):
            with self.subTest(op=op):
                w = wave2()
                w.update(actors=actors, intents=[{'correlation': 'k1', 'op': op, 'target': 'A',
                                                  'status': 'pending', 'result_ref': None}])
                self.write(self.wave_path, w)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                self.refused(fragment, 'write', self.wave_path, '--actor', OWNER, '--expect-revision', 0,
                             '--resolve-intent', 'k1', '--status', 'confirmed', '--result-ref', 'message-1',
                             *(('--role', 'champion') if op == 'launch' else ()), '--ops', json.dumps(ops))
                self.assertEqual(self.doc(self.wave_path)['revision'], 0)

    def test_detached_wave_attaches_although_an_event_id_belongs_to_another_wave(self):
        """Lead left at the v10 hand-back: an id already owned by another wave of the program was an endless refusal."""
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', 'shared-id', '--kind', 'review')  # waves/a
        wave = self.solo()
        p = rc_program()
        p['outcomes'][1]['state_ref'] = 'solo/wave.json'
        self.write(self.program_path, p)
        self.ok('event', wave, '--actor', OWNER, '--id', 'shared-id', '--kind', 'review')  # local journal
        attach = ('write', wave, '--actor', OWNER, '--ops', '[{"op":"set","path":"program_ref","value":"../program.json"}]')
        self.refused('shared-id (its id already belongs to waves/a/wave.json in the program journal: apply it on this '
                     'wave first', *attach[:4], '--expect-revision', 0, *attach[4:])
        self.ok('ack', wave, '--actor', OWNER, '--expect-revision', 0, '--id', 'shared-id', '--reason', 'nothing to do')
        result = self.ok(*attach[:4], '--expect-revision', 1, *attach[4:])
        self.assertEqual(result['events_not_carried'], [{'id': 'shared-id', 'belongs_to': 'waves/a/wave.json'}])
        self.assertEqual(self.doc(wave)['program_ref'], '../program.json')
        carried = [e for e in self.journal(self.program_path) if e['id'] == 'shared-id']
        self.assertEqual([e['wave'] for e in carried], ['waves/a/wave.json'])

    def test_R02_05_moved_or_copied_state_folder_keeps_accepting_writes_and_touches_nothing_outside(self):
        """R02-05 (moved folder) and v10.2 review, point 4 (copy of a state whose prepares list absolute paths)."""
        for how in ('moved', 'copied'):
            with self.subTest(how):
                path, code, result = self.init(f'origin-{how}', 'wave', WAVE_SPEC)
                self.ops(path, 0, [{'op': 'set', 'path': 'state.next_action', 'value': 'a'}])
                journal = path.parent / 'journal.jsonl'
                entries = self.journal(path)
                self.assertEqual([e['journals'] for e in entries if e['kind'] == 'prepare'][-1], ['journal.jsonl'])
                for e in entries:  # as the previous version wrote them: absolute paths of the old folder
                    if e.get('journals'):
                        e['journals'] = [str(journal.resolve())]
                journal.write_text(''.join(json.dumps(e) + '\n' for e in entries), encoding='utf-8')
                target = path.parent.with_name(f'state-{how}')
                if how == 'moved':
                    path.parent.rename(target)
                else:
                    shutil.copytree(path.parent, target)
                    Path(str(journal) + '.lock').write_text('another writer', encoding='utf-8')
                self.assertEqual(self.ops(target / 'wave.json', 1, [{'op': 'set', 'path': 'state.next_action',
                                                                      'value': 'b'}])[0], 0)
                if how == 'copied':
                    self.assertEqual((path.parent / 'journal.jsonl.lock').read_text(encoding='utf-8'), 'another writer')
                    self.assertEqual(self.rev(path), 1)


class Phases(Campaign):
    def test_R07_01_wait_entered_from_planning_resumes_to_preparing(self):
        wave = self.solo()
        self.ok('transition', wave, '--actor', OWNER, '--expect-revision', 0, '--to', 'blocked', '--waiting-kind',
                'dependency', '--detail', 'input missing', '--trigger', 'input delivered', '--resume', 'prepare')
        self.assertIsNone(self.doc(wave)['state']['waiting']['from'])
        self.refused('resumes to preparing', 'transition', wave, '--actor', OWNER, '--expect-revision', 1,
                     '--to', 'planning')
        self.ok('transition', wave, '--actor', OWNER, '--expect-revision', 1, '--to', 'preparing')

    def test_wave_never_launched_reaches_no_product_phase_nor_champion(self):
        """R13-01, R13-02, R07-01 to R07-03, R01-01 to R01-03, R02-02, R02-03, R03-01, R03-02."""
        wait = {'kind': 'quota', 'detail': 'rate limit', 'trigger': 'capacity', 'resume': 'resume'}
        champion = ('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1,
                    '--correlation', 'l1', '--status', 'confirmed', '--result-ref', 'task-1', '--role', 'champion')
        cases = (('transition to integrating', 'resume to preparing, not integrating',
                  ('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--to', 'integrating')),
                 ('transition to launched', 'resume to preparing, not launched',
                  ('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--to', 'launched')),
                 ('origin rewritten', 'waiting origin None cannot be changed', ('write', self.wave_path, '--actor',
                  OWNER, '--expect-revision', 1, '--ops', json.dumps([{'op': 'set', 'path': 'state.waiting',
                                                                      'value': dict(wait, **{'from': 'launched'})}]))),
                 ('champion confirmed', 'in a wave not launched yet (phase blocked)', champion))
        for label, fragment, argv in cases:
            with self.subTest(label):
                w = wave2('blocked')
                w['state']['waiting'] = dict(wait, **{'from': None})
                w['intents'] = [{'correlation': 'l1', 'op': 'launch', 'target': 'A', 'status': 'pending',
                                 'result_ref': None}]
                w['revision'] = 1
                self.write(self.wave_path, w)
                (self.root / 'journal.jsonl').unlink(missing_ok=True)
                self.refused(fragment, *argv)
                self.assertEqual(self.doc(self.wave_path)['revision'], 1)
        self.ok('transition', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--to', 'preparing')


class Help(Campaign):
    def test_command_help_gives_a_complete_example(self):
        expected = {'transition': ('transition FILE --actor A --expect-revision N --to preparing',),
                    'ack': ('ack FILE --actor A --expect-revision N --id task-1:run-1',),
                    'claim': ('claim FILE --actor A --role pilot --expect-revision N',),
                    'event': ('event FILE --actor A --id task-1:run-1 --kind review', 'no --expect-revision'),
                    'intent': ('intent FILE add --actor A --expect-revision N --correlation',),  # R07-06
                    'reconcile': ('reconcile FILE --actor A --op ',),
                    'dispose': ('dispose FILE --actor A --id task-1:run-1 --disposition late --evidence',)}
        for command, fragments in expected.items():
            with self.subTest(command=command):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                    rc.main([command, '--help'])
                for fragment in fragments:
                    self.assertIn(fragment, out.getvalue())


if __name__ == '__main__':
    unittest.main()
