"""v10 short actor return: write --resolve-intent with --record-event."""
import contextlib
import io
import json
import unittest

from test_rc_state import OWNER, Base, rc

EVENT = 'task-9:run1'
DONE = json.dumps([{'op': 'update', 'path': 'actors', 'match': {'correlation': 'r1'}, 'value': {'status': 'completed'}}])


class ShortReturn(Base):
    def setUp(self):
        super().setUp()
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 0,
                '--correlation', 'r1', '--op', 'launch', '--target', 'reviewer-A')

    def short_argv(self, rev, *extra):
        return ('write', self.wave_path, '--actor', OWNER, '--expect-revision', rev, '--resolve-intent', 'r1',
                '--status', 'confirmed', '--result-ref', 'task-9', '--role', 'reviewer',
                '--record-event', EVENT, '--kind', 'review', *extra)

    def short(self, rev, *extra):
        return self.run_cli(*self.short_argv(rev, *extra))

    def doc(self):
        return json.loads(self.wave_path.read_text(encoding='utf-8'))

    def journal(self):
        return [json.loads(line) for line in (self.root / 'journal.jsonl').read_text(encoding='utf-8').splitlines()]

    def unapplied(self):
        code, result = self.run_cli('resume', self.program_path)
        return [e['id'] for e in result['unapplied_events']], result['uncertain_operations']

    def test_one_command_records_resolves_and_applies_in_one_revision(self):
        before = len(self.journal())
        code, result = self.short(1, '--ops', DONE)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['revision'], result['event']['classification']), (2, 'new'))
        doc = self.doc()
        self.assertEqual((doc['intents'][0]['status'], doc['intents'][0]['result_ref']), ('confirmed', 'task-9'))
        self.assertEqual([(a['correlation'], a['ref'], a['role'], a['target'], a['status']) for a in doc['actors']],
                         [('r1', 'task-9', 'reviewer', 'reviewer-A', 'completed')])
        added = self.journal()[before:]
        self.assertEqual([e['kind'] for e in added], ['event:review', 'prepare', 'write'])
        self.assertEqual((added[0]['id'], added[0]['wave'], added[0]['classification']),
                         (EVENT, 'waves/a/wave.json', 'new'))
        self.assertEqual((added[1]['pending_applies_event'], added[2]['applies_event'], added[2]['commits']),
                         (EVENT, EVENT, added[1]['id']))
        self.assertEqual(self.unapplied(), ([], []))

    def test_event_already_applied_is_reported_and_nothing_written(self):
        self.ok('event', self.wave_path, '--actor', OWNER, '--id', EVENT, '--kind', 'review')
        self.ok('ack', self.wave_path, '--actor', OWNER, '--expect-revision', 1, '--id', EVENT)
        before = len(self.journal())
        code, result = self.short(2)
        self.assertEqual(code, 1, result)
        self.assertEqual((result['event']['classification'], result['written']), ('duplicate', None))
        self.assertEqual(self.rev(self.wave_path), 2)
        self.assertEqual((self.doc()['intents'][0]['status'], self.doc()['actors']), ('pending', []))
        self.assertEqual(len(self.journal()), before)

    def test_intent_not_pending_refused_and_event_stays_unapplied(self):
        self.ok('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1,
                '--correlation', 'r1', '--status', 'absent')
        result = self.refused('resolved and immutable', *self.short_argv(2))
        self.assertIn(f'event {EVENT} is recorded and stays unapplied', result['error'])
        self.assertEqual(self.rev(self.wave_path), 2)
        self.assertEqual((self.doc()['intents'][0]['status'], self.doc()['actors']), ('absent', []))
        self.assertEqual(self.unapplied(), ([EVENT], []))

    def test_refused_write_after_receipt_leaves_event_unapplied_then_rerun_applies_it(self):
        bad = json.dumps([{'op': 'set', 'path': 'state.phase', 'value': 'planning'}])
        result = self.refused('transition launched -> planning not allowed', *self.short_argv(1, '--ops', bad))
        self.assertIn('stays unapplied', result['error'])
        self.assertEqual(self.rev(self.wave_path), 1)
        self.assertEqual((self.doc()['intents'][0]['status'], self.doc()['actors']), ('pending', []))
        self.assertEqual(self.unapplied(), ([EVENT], []))
        code, result = self.short(1, '--ops', DONE)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['revision'], result['event']['classification']), (2, 'unapplied'))
        self.assertEqual(self.unapplied(), ([], []))

    def test_short_form_options_refused_out_of_their_pairing(self):
        base = ('write', self.wave_path, '--actor', OWNER, '--expect-revision', 1)
        for extra in ((), ('--resolve-intent', 'r1'), ('--ops', DONE, '--status', 'confirmed'),
                      ('--ops', DONE, '--result-ref', 'task-9'), ('--ops', DONE, '--record-event', EVENT),
                      ('--ops', DONE, '--kind', 'review'), ('--ops', DONE, '--candidate-seq', 1),
                      ('--ops', DONE, '--record-event', EVENT, '--kind', 'review', '--applies-event', EVENT)):
            with self.subTest(extra=extra), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                rc.main([str(a) for a in base + extra])
        self.assertEqual((self.rev(self.wave_path), len(self.journal())), (1, 2))


if __name__ == '__main__':
    unittest.main()
