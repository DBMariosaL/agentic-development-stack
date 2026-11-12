"""Regression tests for pre-review 3 findings (revues/pre-revue-3-gpt/rapport.md, R3-01 and R3-02)."""
import json
import unittest

from test_rc_state import OWNER, Base, program, wave2


class Review3(Base):
    def two_waves(self, seq_a=1, seq_b=2):
        a = wave2()
        a['candidate'] = {'seq': seq_a, 'ref': 'mA', 'artifact': 'manifest', 'sha256': 'a' * 64, 'frozen_at': 't'}
        self.write(self.wave_path, a)
        other = self.root / 'waves/b/wave.json'
        other.parent.mkdir(parents=True)
        b = wave2()
        b['candidate'] = {'seq': seq_b, 'ref': 'mB', 'artifact': 'manifest', 'sha256': 'b' * 64, 'frozen_at': 't'}
        self.write(other, b)
        p = program()
        p['outcomes'][1].update(status='admitted', depends_on=[], state_ref='waves/b/wave.json')
        self.write(self.program_path, p)
        return other

    def test_R3_02_other_wave_cannot_reclassify_or_ack(self):
        other = self.two_waves()
        argv = ['--actor', OWNER, '--id', 'task-A:run1', '--kind', 'review', '--candidate-seq', 1]
        self.assertEqual(self.ok('event', self.wave_path, *argv)['classification'], 'new')
        self.refused('belongs to waves/a/wave.json', 'event', other, *argv)
        code, result = self.run_cli('resume', self.program_path)
        self.assertEqual([e['id'] for e in result['unapplied_events']], ['task-A:run1'])
        self.assertEqual(self.ok('event', self.wave_path, *argv)['classification'], 'unapplied')

    def test_R3_01_legacy_event_without_wave_needs_sourced_attachment(self):
        other = self.two_waves()
        legacy = {'id': 'legacy-review', 'at': 't', 'kind': 'event:review', 'file': 'wave.json', 'actor': OWNER,
                  'classification': 'new', 'candidate_seq': 1, 'wave_revision': 0, 'detail': None}
        (self.root / 'journal.jsonl').write_text(json.dumps(legacy) + '\n', encoding='utf-8')
        base = ['--actor', OWNER, '--id', 'legacy-review', '--kind', 'review']
        self.assertEqual(self.ok('event', self.wave_path, *base)['classification'], 'legacy-unattached')
        self.refused('no wave identity', 'ack', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--id', 'legacy-review')
        code, result = self.run_cli('resume', self.program_path)
        self.assertTrue(any('older tool without wave identity' in a for a in result['actions']), result['actions'])
        self.refused('needs --evidence', 'event', self.wave_path, *base, '--attach-legacy')
        self.assertEqual(self.ok('event', self.wave_path, *base, '--attach-legacy', '--evidence',
                                 'receipt of review task for wave a, candidate 1')['classification'], 'attached')
        self.refused('not a received legacy event', 'event', other, *base, '--attach-legacy', '--evidence', 'x')
        self.refused('was received for waves/a/wave.json', 'ack', other, '--actor', OWNER, '--expect-revision', 0,
                     '--id', 'legacy-review')
        self.ok('ack', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--id', 'legacy-review')
        code, result = self.run_cli('resume', self.program_path)
        self.assertEqual(result['unapplied_events'], [])


if __name__ == '__main__':
    unittest.main()
