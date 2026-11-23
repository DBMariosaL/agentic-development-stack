"""Rules the engine now refuses on what a write adds or changes; states that already hold them stay valid."""
import hashlib
import json

from test_rc_state import OWNER, Base, program, wave2

REVIEW = {'artifact': 'prompt_a', 'sha256': 'a' * 64, 'status': 'done', 'disposition': 'no finding',
          'reference': 'review r.md', 'candidate_seq': None}
HOLD = {'kind': 'human', 'detail': 'licence unknown', 'trigger': 'owner answers'}
DECISION = {'id': 'D1', 'question': 'Licence?', 'option': 'use it under MIT', 'effects': 'A waits', 'suspends': ['A']}
MOTIVE = 'expected a motive with at least 3 letters or decimal digits'


class Lot2(Base):
    def edit(self, path, *ops):
        return self.run_cli('write', path, '--actor', OWNER, '--expect-revision', self.rev(path), '--ops', json.dumps(ops))

    def refused_edit(self, fragment, path, *ops):
        code, result = self.edit(path, *ops)
        self.assertEqual(code, 1, result)
        self.assertIn(fragment, result['error'])

    def accepted_edit(self, path, *ops):
        code, result = self.edit(path, *ops)
        self.assertEqual(code, 0, result)

    def still_usable(self, *paths):
        """C1: check, resume, ready, claim and an unrelated write all pass on a state that holds the situation."""
        for path in paths:
            self.assertEqual(self.ok('check', path)['errors'], [])
        self.ok('resume', self.program_path)
        self.ok('ready', self.program_path)
        for path in paths:
            self.ok('claim', path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', self.rev(path))
            field = 'status_reason' if path == self.program_path else 'state.next_action'
            self.accepted_edit(path, {'op': 'set', 'path': field, 'value': 'unrelated note'})

    def test_G1_a_batched_lot_without_consumed_mandate_blocks_the_launch(self):
        w = wave2('ready')
        w['socles'].append({'id': 'B', 'outcome': 'Lot B', 'depends_on': [], 'readiness': 'blocked', 'resources': [],
                            'source_refs': []})
        w.update(batches=[['A', 'B']], reviews=[REVIEW])
        self.write(self.wave_path, w)
        flag = {'op': 'set', 'path': 'state.launch_ready', 'value': True}
        self.refused_edit('B: lot listed in batches (readiness blocked) without a consumed mandate', self.wave_path, flag)
        w['socles'][1]['prompt_artifact'] = []  # an unexpected type is named, never an internal error
        self.write(self.wave_path, w)
        self.refused_edit('B: lot listed in batches', self.wave_path, flag)
        w['socles'][1].pop('prompt_artifact')
        w['state']['launch_ready'] = True  # accepted by the previous engine: stays valid and writable
        self.write(self.wave_path, w)
        self.still_usable(self.wave_path)
        self.refused('remove B from batches', 'transition', self.wave_path, '--actor', OWNER,
                     '--expect-revision', self.rev(self.wave_path), '--to', 'launched')

    def test_G2_a_motive_without_three_letters_or_digits_is_refused_where_it_is_written(self):
        dot = dict(REVIEW, disposition='.', reference='-- !')
        for value, field in (([dot], 'reviews[0].disposition'), ([dot], 'reviews[0].reference'),
                             ([dict(REVIEW, reference='½½½')], 'reviews[0].reference')):
            with self.subTest(field=field, value=value):
                self.refused_edit(f'{field}: {MOTIVE}', self.wave_path, {'op': 'set', 'path': 'reviews', 'value': value})
        self.refused_edit(f'envelope.reason: {MOTIVE}', self.wave_path, {'op': 'set', 'path': 'envelope',
                                                                        'value': {'reason': ' . '}})
        self.accepted_edit(self.wave_path, {'op': 'set', 'path': 'reviews', 'value': [dict(REVIEW, reference='2026 11')]})
        self.refused(f'state.waiting.resume: {MOTIVE}', 'transition', self.wave_path, '--actor', OWNER,
                     '--expect-revision', self.rev(self.wave_path), '--to', 'waiting_quota', '--waiting-kind', 'quota',
                     '--detail', 'rate', '--trigger', 'quota back', '--resume', '...')
        self.refused_edit(f'outcomes.B.closure.source: {MOTIVE}', self.program_path, {
            'op': 'update', 'path': 'outcomes', 'match': {'id': 'B'},
            'value': {'status': 'abandoned', 'closure': {'source': '#1', 'remaining': 'all'}}})
        legacy = wave2('waiting_quota')
        legacy.update(reviews=[dot], envelope={'reason': '.'})
        legacy['state']['waiting'] = {'kind': 'quota', 'detail': 'rate', 'trigger': 'quota back', 'resume': '.',
                                      'from': 'launched'}
        self.write(self.wave_path, legacy)
        p = program()
        p['outcomes'].append({'id': 'C', 'outcome': 'Lot C', 'depends_on': [], 'status': 'abandoned', 'state_ref': None,
                              'waiting_on': None, 'resources': [], 'next_action': 'none',
                              'closure': {'source': '.', 'remaining': 'all'}})
        self.write(self.program_path, p)
        self.still_usable(self.wave_path, self.program_path)
        self.accepted_edit(self.wave_path, {'op': 'set', 'path': 'reviews', 'value': [dict(dot, reference='report r.md')]})
        self.accepted_edit(self.wave_path, {'op': 'set', 'path': 'state.waiting.detail', 'value': 'rate limit'})
        self.accepted_edit(self.program_path, {'op': 'update', 'path': 'outcomes', 'match': {'id': 'C'},
                                               'value': {'closure': {'source': '.', 'remaining': 'nothing left'}}})
        self.refused_edit(f'reviews[1].disposition: {MOTIVE}', self.wave_path,
                          {'op': 'append', 'path': 'reviews', 'value': dict(dot, reference='report r.md')})

    def test_G3_consumed_artifact_changed_on_disk_is_signalled_and_stops_the_gates(self):
        mandate = self.wave_path.parent / 'socles/a.txt'
        mandate.parent.mkdir()
        mandate.write_bytes(b'mandate v1\n')
        w = wave2('ready')
        w['state']['consumed']['prompt_a']['sha256'] = sha = hashlib.sha256(b'mandate v1\n').hexdigest()
        w['reviews'] = [dict(REVIEW, sha256=sha)]
        self.write(self.wave_path, w)
        flag = {'op': 'set', 'path': 'state.launch_ready', 'value': True}
        mandate.write_bytes(b'mandate v2\n')
        self.refused_edit('prompt_a: file socles/a.txt no longer matches its consumed sha256', self.wave_path, flag)
        mandate.unlink()  # absent: today's treatment, nothing signalled or refused without --check-paths
        self.assertNotIn('drifted_artifacts', self.ok('check', self.wave_path))
        self.accepted_edit(self.wave_path, flag)
        mandate.write_bytes(b'mandate v2\n')
        result = self.ok('check', self.wave_path)
        self.assertEqual([(d['artifact'], d['consumed_sha256']) for d in result['drifted_artifacts']], [('prompt_a', sha)])
        self.assertEqual(list(self.ok('check', self.program_path)['drifted_artifacts']), ['A'])
        self.assertTrue(any('consumed artifact prompt_a (socles/a.txt) no longer matches its sha256' in a
                            for a in self.ok('resume', self.program_path)['actions']))
        self.still_usable(self.wave_path)
        self.refused('prompt_a: file socles/a.txt no longer matches its consumed sha256', 'transition',
                     self.wave_path, '--actor', OWNER, '--expect-revision', self.rev(self.wave_path), '--to', 'launched')
        w = json.loads(self.wave_path.read_text(encoding='utf-8'))
        w['state'].update(phase='waiting_quota', launch_ready=False,
                          waiting={'kind': 'quota', 'detail': 'rate', 'trigger': 'back', 'resume': 'relaunch', 'from': 'launched'})
        w['candidate'] = {'seq': 1, 'ref': 'manifest-1', 'artifact': 'manifest', 'sha256': 'c' * 64}
        w['reviews'].append(dict(REVIEW, artifact='manifest', sha256='c' * 64, candidate_seq=1))
        self.write(self.wave_path, w)
        self.refused('no longer matches its consumed sha256', 'transition', self.wave_path, '--actor', OWNER,
                     '--expect-revision', self.rev(self.wave_path), '--to', 'launched')
        w['state'].update(phase='launched', waiting=None)
        self.write(self.wave_path, w)
        for phase in ('completed', 'completed_partial'):
            self.refused('no longer matches its consumed sha256', 'transition', self.wave_path, '--actor', OWNER,
                         '--expect-revision', self.rev(self.wave_path), '--to', phase)
        self.refused_edit('prompt_a: file socles/a.txt no longer matches', self.wave_path,
                          {'op': 'set', 'path': 'state.consumed',
                           'value': {'manifest': {'version': 'v1', 'sha256': 'c' * 64}}},
                          {'op': 'set', 'path': 'state.phase', 'value': 'completed'})

    def test_G4_admitting_a_suspended_outcome_is_refused(self):
        p = program(outcome_status='pending')
        p['outcomes'][0]['waiting_on'] = HOLD
        p['outcomes'][1]['depends_on'] = []
        p['decisions_pending'] = [DECISION]
        self.write(self.program_path, p)
        admit = {'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {'status': 'admitted'}}
        self.refused_edit('A: admitted while suspended by pending decision D1', self.program_path, admit)
        p['decisions_pending'] = []
        p['outcomes'][0]['waiting_on'] = dict(HOLD, kind='quota')
        self.write(self.program_path, p)
        self.refused_edit('A: admitted while waiting_on is {"kind": "quota"', self.program_path, admit)
        p['outcomes'][0].update(status='admitted', waiting_on=HOLD)  # admitted then suspended: stays valid
        p['decisions_pending'] = [DECISION]
        self.write(self.program_path, p)
        self.still_usable(self.program_path)

    def test_G5_clearing_the_ref_of_an_outcome_whose_wave_is_live_is_refused(self):
        closed = {'status': 'accepted', 'state_ref': None, 'closure': {'source': 'review of A', 'remaining': 'none'}}
        for value in (closed, {'status': 'pending', 'state_ref': None}):
            with self.subTest(value=value):
                self.refused_edit('A: state_ref waves/a/wave.json cleared while that wave is launched',
                                  self.program_path, {'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'},
                                                      'value': value})
        self.write(self.wave_path, wave2('stopped'))
        self.accepted_edit(self.program_path, {'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': closed})

    def test_G6_a_new_decision_carries_a_recommendation_that_resume_and_ready_render(self):
        p = program(outcome_status='pending')
        p['outcomes'][1]['depends_on'] = []
        self.write(self.program_path, p)
        suspend = {'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {'waiting_on': HOLD}}
        for value in (DECISION, dict(DECISION, recommendation='.')):
            with self.subTest(value=value):
                self.refused_edit(f'decisions_pending[0].recommendation: {MOTIVE}', self.program_path, suspend,
                                  {'op': 'set', 'path': 'decisions_pending', 'value': [value]})
        advised = dict(DECISION, recommendation='accept: MIT allows our use')
        self.accepted_edit(self.program_path, suspend, {'op': 'set', 'path': 'decisions_pending', 'value': [advised]})
        self.assertTrue(any('recommendation: accept: MIT allows our use' in a
                            for a in self.ok('resume', self.program_path)['actions']))
        self.assertEqual(self.ok('ready', self.program_path)['decisions_pending'][0]['recommendation'],
                         'accept: MIT allows our use')
        self.refused_edit(f'decisions_pending[0].recommendation: {MOTIVE}', self.program_path,
                          {'op': 'set', 'path': 'decisions_pending', 'value': [DECISION]})
        self.refused_edit(f'decisions_pending[1].recommendation: {MOTIVE}', self.program_path,
                          {'op': 'append', 'path': 'decisions_pending', 'value': dict(DECISION, question='Again?')})
        p['outcomes'][0]['waiting_on'] = HOLD  # entries written before this rule, same id included, stay valid
        p['decisions_pending'] = [dict(DECISION, recommendation='.'), dict(DECISION, question='Again?')]
        self.write(self.program_path, p)
        self.still_usable(self.program_path)
        spec = self.root / 'spec.json'
        spec.write_text(json.dumps({'mandate': p['mandate'], 'outcomes': [{'id': 'A', 'outcome': 'A', 'next_action': 'n'}],
                                    'decisions_pending': [dict(DECISION, id=[], suspends=[])]}), encoding='utf-8')
        self.refused('decisions_pending[0].id: expected nonempty text, got list', 'init', self.root / 'other.json',
                     '--kind', 'program', '--actor', OWNER, '--role', 'pilot', '--spec', spec)
