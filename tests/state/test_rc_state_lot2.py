"""Rules the engine now refuses on the write that creates their situation; states that already hold it stay valid."""
import hashlib
import json

from test_rc_state import OWNER, Base, program, wave2

REVIEW = {'artifact': 'prompt_a', 'sha256': 'a' * 64, 'status': 'done', 'disposition': 'no finding',
          'reference': 'review r.md', 'candidate_seq': None}
HOLD = {'kind': 'human', 'detail': 'licence unknown', 'trigger': 'owner answers'}
DECISION = {'id': 'D1', 'question': 'Licence?', 'option': 'use it under MIT', 'effects': 'A waits', 'suspends': ['A']}


class Lot2(Base):
    def edit(self, path, *ops):
        return self.run_cli('write', path, '--actor', OWNER, '--expect-revision', self.rev(path), '--ops', json.dumps(ops))

    def still_usable(self, *paths):
        """C1: check, resume, ready, claim and an unrelated write all pass on a state that holds the situation."""
        for path in paths:
            self.assertEqual(self.ok('check', path)['errors'], [])
        self.ok('resume', self.program_path)
        self.ok('ready', self.program_path)
        for path in paths:
            self.ok('claim', path, '--actor', OWNER, '--role', 'pilot', '--expect-revision', self.rev(path))
            field = 'status_reason' if path == self.program_path else 'state.next_action'
            self.assertEqual(self.edit(path, {'op': 'set', 'path': field, 'value': 'unrelated note'})[0], 0)

    def test_G1_a_batched_lot_without_consumed_mandate_blocks_the_launch(self):
        w = wave2('ready')
        w['socles'].append({'id': 'B', 'outcome': 'Lot B', 'depends_on': [], 'readiness': 'blocked', 'resources': [],
                            'source_refs': []})
        w.update(batches=[['A', 'B']], reviews=[REVIEW])
        self.write(self.wave_path, w)
        self.refused('B: lot listed in batches (readiness blocked) without a consumed mandate', 'write', self.wave_path,
                     '--actor', OWNER, '--expect-revision', 0,
                     '--ops', json.dumps([{'op': 'set', 'path': 'state.launch_ready', 'value': True}]))
        w['state']['launch_ready'] = True  # accepted by the previous engine: stays valid and writable
        self.write(self.wave_path, w)
        self.still_usable(self.wave_path)
        self.refused('remove B from batches', 'transition', self.wave_path, '--actor', OWNER,
                     '--expect-revision', self.rev(self.wave_path), '--to', 'launched')

    def test_G2_a_motive_without_three_letters_or_digits_is_refused_where_it_is_written(self):
        dot = dict(REVIEW, disposition='.', reference='-- !')
        for ops, field in (([{'op': 'set', 'path': 'reviews', 'value': [dot]}], 'reviews[0].disposition'),
                           ([{'op': 'set', 'path': 'reviews', 'value': [dot]}], 'reviews[0].reference'),
                           ([{'op': 'set', 'path': 'envelope', 'value': {'reason': ' . '}}], 'envelope.reason')):
            with self.subTest(field=field):
                self.assertIn(f"{field}: expected a motive with at least 3 letters or digits",
                              self.edit(self.wave_path, *ops)[1]['error'])
        self.refused("state.waiting.resume: expected a motive", 'transition', self.wave_path, '--actor', OWNER,
                     '--expect-revision', 0, '--to', 'waiting_quota', '--waiting-kind', 'quota', '--detail', 'rate',
                     '--trigger', 'quota back', '--resume', '...')
        self.assertIn("outcomes.B.closure.source: expected a motive", self.edit(self.program_path, {
            'op': 'update', 'path': 'outcomes', 'match': {'id': 'B'},
            'value': {'status': 'abandoned', 'closure': {'source': '#1', 'remaining': 'all'}}})[1]['error'])
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

    def test_G3_consumed_artifact_changed_on_disk_is_signalled_and_stops_the_gates(self):
        mandate = self.wave_path.parent / 'socles/a.txt'
        mandate.parent.mkdir()
        mandate.write_bytes(b'mandate v1\n')
        w = wave2('ready')
        w['state']['consumed']['prompt_a']['sha256'] = sha = hashlib.sha256(b'mandate v1\n').hexdigest()
        w['reviews'] = [dict(REVIEW, sha256=sha)]
        self.write(self.wave_path, w)
        launch_ready = [{'op': 'set', 'path': 'state.launch_ready', 'value': True}]
        mandate.unlink()  # absent: today's treatment, nothing signalled or refused without --check-paths
        self.assertNotIn('drifted_artifacts', self.ok('check', self.wave_path))
        self.assertEqual(self.edit(self.wave_path, *launch_ready)[0], 0)
        mandate.write_bytes(b'mandate v2\n')
        result = self.ok('check', self.wave_path)
        self.assertEqual([(d['artifact'], d['consumed_sha256']) for d in result['drifted_artifacts']], [('prompt_a', sha)])
        self.assertTrue(any('consumed artifact prompt_a (socles/a.txt) no longer matches its sha256' in a
                            for a in self.ok('resume', self.program_path)['actions']))
        self.still_usable(self.wave_path)
        self.refused('prompt_a: file socles/a.txt no longer matches its consumed sha256', 'transition',
                     self.wave_path, '--actor', OWNER, '--expect-revision', self.rev(self.wave_path), '--to', 'launched')
        w = json.loads(self.wave_path.read_text(encoding='utf-8'))
        w['state'].update(phase='launched', launch_ready=False)
        w['candidate'] = {'seq': 1, 'ref': 'manifest-1', 'artifact': 'manifest', 'sha256': 'c' * 64}
        w['reviews'].append(dict(REVIEW, artifact='manifest', sha256='c' * 64, candidate_seq=1))
        self.write(self.wave_path, w)
        self.refused('no longer matches its consumed sha256', 'transition', self.wave_path, '--actor', OWNER,
                     '--expect-revision', self.rev(self.wave_path), '--to', 'completed')

    def test_G4_admitting_a_suspended_outcome_is_refused(self):
        p = program(outcome_status='pending')
        p['outcomes'][0]['waiting_on'] = HOLD
        p['outcomes'][1]['depends_on'] = []
        p['decisions_pending'] = [DECISION]
        self.write(self.program_path, p)
        admit = {'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {'status': 'admitted'}}
        self.assertIn('A: admitted while suspended by pending decision D1', self.edit(self.program_path, admit)[1]['error'])
        p['decisions_pending'] = []
        p['outcomes'][0]['waiting_on'] = dict(HOLD, kind='quota')
        self.write(self.program_path, p)
        self.assertIn('A: admitted while waiting_on is {"kind": "quota"', self.edit(self.program_path, admit)[1]['error'])
        p['outcomes'][0].update(status='admitted', waiting_on=HOLD)  # admitted then suspended: stays valid
        p['decisions_pending'] = [DECISION]
        self.write(self.program_path, p)
        self.still_usable(self.program_path)

    def test_G5_closing_an_outcome_by_clearing_the_ref_of_a_live_wave_is_refused(self):
        accept = {'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {
            'status': 'accepted', 'state_ref': None, 'closure': {'source': 'review of A', 'remaining': 'none'}}}
        self.refused('A: accepted clears state_ref waves/a/wave.json while that wave is launched', 'write',
                     self.program_path, '--actor', OWNER, '--expect-revision', 0, '--ops', json.dumps([accept]))
        w = wave2('stopped')
        self.write(self.wave_path, w)
        self.assertEqual(self.edit(self.program_path, accept)[0], 0)

    def test_G6_a_new_decision_carries_a_recommendation_that_resume_and_ready_render(self):
        p = program(outcome_status='pending')
        p['outcomes'][1]['depends_on'] = []
        self.write(self.program_path, p)
        suspend = [{'op': 'update', 'path': 'outcomes', 'match': {'id': 'A'}, 'value': {'waiting_on': HOLD}}]
        self.refused('decisions_pending[0].recommendation: a new decision D1 needs a recommendation', 'write',
                     self.program_path, '--actor', OWNER, '--expect-revision', 0,
                     '--ops', json.dumps(suspend + [{'op': 'set', 'path': 'decisions_pending', 'value': [DECISION]}]))
        advised = dict(DECISION, recommendation='accept: MIT allows our use')
        self.assertEqual(self.edit(self.program_path, *suspend, {'op': 'set', 'path': 'decisions_pending',
                                                                 'value': [advised]})[0], 0)
        self.assertTrue(any('recommendation: accept: MIT allows our use' in a
                            for a in self.ok('resume', self.program_path)['actions']))
        self.assertEqual(self.ok('ready', self.program_path)['decisions_pending'][0]['recommendation'],
                         'accept: MIT allows our use')
        p['outcomes'][0]['waiting_on'] = HOLD  # an entry written before this rule stays valid without it
        p['decisions_pending'] = [DECISION]
        self.write(self.program_path, p)
        self.still_usable(self.program_path)
