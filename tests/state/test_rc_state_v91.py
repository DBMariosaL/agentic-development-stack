"""v9.1 and v9.1.1 engine changes: init and --replace-invalid, per-field messages, explicit wave-only refusals,
resume action deduplication, admitted-admitted resource conflicts, null review candidate_seq."""
import contextlib
import hashlib
import io
import json
import os
import unittest
from unittest import mock

from test_rc_state import OWNER, Base, program, rc, wave2

PROGRAM_SPEC = {'mandate': {'ref': 'synthetic mandate', 'scope': ['synthetic lots'], 'exclusions': [],
                            'end_criteria': 'lot C accepted'},
                'outcomes': [{'id': 'C', 'outcome': 'Lot C', 'next_action': 'prepare wave C'}]}
WAVE_SPEC = {'authorization': {'exclusions': ['real services']}, 'state': {'next_action': 'cut the lots'}}


class InitBase(Base):
    def setUp(self):
        super().setUp()
        self.fresh = self.root / 'fresh'
        self.fresh.mkdir()

    def spec(self, doc, name='spec.json'):
        path = self.root / name
        path.write_text(json.dumps(doc), encoding='utf-8')
        return path

    def init(self, path, kind, spec, *extra, actor=OWNER):
        return self.run_cli('init', path, '--kind', kind, '--actor', actor, '--role', 'pilot',
                            '--spec', self.spec(spec), *extra)

    def doc(self, path):
        return json.loads(path.read_text(encoding='utf-8'))

    def journal(self, directory):
        path = directory / 'journal.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def usage_error(self, *argv):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            rc.main([str(a) for a in argv])


class Init(InitBase):
    def test_init_program_from_minimal_spec(self):
        path = self.fresh / 'program.json'
        code, result = self.init(path, 'program', PROGRAM_SPEC)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['revision'], result['owner']), (0, OWNER))
        doc = self.doc(path)
        self.assertEqual(doc['schema'], 'rc-program/1')
        self.assertEqual(doc['owner'], {'role': 'pilot', 'ref': OWNER})
        self.assertEqual((doc['status'], doc['decisions_pending'], doc['last_milestone'], doc['skills_consumed']),
                         ('active', [], None, []))
        self.assertEqual(doc['outcomes'][0], dict(PROGRAM_SPEC['outcomes'][0], depends_on=[], status='pending',
                                                  state_ref=None, waiting_on=None, resources=[]))
        self.assertTrue(self.ok('check', path)['valid'])
        entry = self.journal(self.fresh)[-1]
        self.assertEqual((entry['kind'], entry['wave'], entry['revision'], entry['replaces']),
                         ('init', 'program.json', 0, None))
        self.assertEqual(entry['new_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        prepare = self.journal(self.fresh)[0]
        self.assertEqual([e['kind'] for e in self.journal(self.fresh)], ['prepare', 'init'])
        self.assertEqual((prepare['op_kind'], prepare['old_sha256'], prepare['new_sha256'], entry['commits']),
                         ('init', None, entry['new_sha256'], prepare['id']))
        ops = json.dumps([{'op': 'set', 'path': 'status_reason', 'value': 'lot C ready'}])
        self.assertEqual(self.ok('write', path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)['revision'], 1)

    def test_init_detached_wave_from_minimal_spec(self):
        path = self.fresh / 'waves/c/wave.json'
        path.parent.mkdir(parents=True)
        code, result = self.init(path, 'wave', WAVE_SPEC)
        self.assertEqual(code, 0, result)
        doc = self.doc(path)
        self.assertEqual((doc['schema_version'], doc['revision'], doc['program_ref'], doc['mode']), (2, 0, None, 'prepare'))
        self.assertEqual((doc['state']['phase'], doc['state']['launch_ready'], doc['state']['owner']['ref']),
                         ('planning', False, OWNER))
        self.assertEqual(doc['authorization'], {'launch': False, 'source': None, 'scope': None,
                                                'exclusions': ['real services']})
        self.assertEqual(doc['project'], {'root': None, 'baseline': None, 'observed_at': None})
        self.assertTrue(self.ok('check', path)['valid'])
        self.assertEqual(self.journal(path.parent)[-1]['wave'], 'wave.json')
        self.ok('transition', path, '--actor', OWNER, '--expect-revision', 0, '--to', 'preparing')

    def test_init_wave_then_program_then_attach(self):
        wave_path = self.fresh / 'waves/c/wave.json'
        wave_path.parent.mkdir(parents=True)
        self.assertEqual(self.init(wave_path, 'wave', WAVE_SPEC)[0], 0)
        spec = json.loads(json.dumps(PROGRAM_SPEC))
        spec['outcomes'][0].update(status='admitted', state_ref='waves/c/wave.json')
        program_path = self.fresh / 'program.json'
        code, result = self.init(program_path, 'program', spec)
        self.assertEqual(code, 0, result)
        ops = json.dumps([{'op': 'set', 'path': 'program_ref', 'value': '../../program.json'}])
        self.ok('write', wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)
        self.assertEqual(self.ok('resume', program_path)['consistency_errors'], [])

    def test_init_refuses_existing_file(self):
        before = self.program_path.read_bytes()
        self.refused('init never overwrites', 'init', self.program_path, '--kind', 'program', '--actor', OWNER,
                     '--role', 'pilot', '--spec', self.spec(PROGRAM_SPEC))
        self.assertEqual(self.program_path.read_bytes(), before)

    def test_init_names_missing_business_fields(self):
        spec = {'mandate': {'ref': 'm', 'scope': ['s'], 'exclusions': []}, 'outcomes': [{'id': 'C', 'outcome': 'Lot C'}]}
        code, result = self.init(self.fresh / 'program.json', 'program', spec)
        self.assertEqual(code, 1)
        self.assertIn('mandate.end_criteria', result['error'])
        self.assertIn('outcomes[0].next_action', result['error'])
        code, result = self.init(self.fresh / 'wave.json', 'wave', {})
        self.assertEqual(code, 1)
        self.assertIn('authorization.exclusions, state.next_action', result['error'])
        self.assertEqual(list(self.fresh.iterdir()), [])

    def test_init_refuses_fields_it_sets(self):
        code, result = self.init(self.fresh / 'program.json', 'program', dict(PROGRAM_SPEC, revision=3))
        self.assertEqual(code, 1)
        self.assertIn('init sets these fields itself', result['error'])
        self.assertIn('revision', result['error'])
        spec = dict(WAVE_SPEC, state={'next_action': 'x', 'phase': 'launched'}, intents=[{'correlation': 'c'}])
        code, result = self.init(self.fresh / 'wave.json', 'wave', spec)
        self.assertIn('intents, state.phase', result['error'])
        code, result = self.init(self.fresh / 'program.json', 'program', dict(PROGRAM_SPEC, schema='rc-program/1'))
        self.assertEqual(code, 0, result)  # a managed field given with the value init sets is accepted

    def test_init_validates_like_check(self):
        spec = json.loads(json.dumps(PROGRAM_SPEC))
        spec['mandate']['scope'] = 'everything'
        code, result = self.init(self.fresh / 'program.json', 'program', spec)
        self.assertEqual(code, 1)
        self.assertIn('initial state invalid', result['error'])
        self.assertIn('mandate.scope: expected list of strings, got str', result['error'])
        self.assertFalse((self.fresh / 'program.json').exists())
        self.assertFalse((self.fresh / 'journal.jsonl').exists())

    def test_init_refuses_missing_file_with_journal_history(self):
        path = self.fresh / 'wave.json'
        self.assertEqual(self.init(path, 'wave', WAVE_SPEC)[0], 0)
        path.unlink()
        code, result = self.init(path, 'wave', WAVE_SPEC)
        self.assertEqual(code, 1)
        self.assertIn('already records operations on wave.json', result['error'])
        self.assertFalse(path.exists())

    def test_init_template_prints_field_formats(self):
        result = self.ok('init', '--template', 'program')
        self.assertEqual(result['spec']['mandate']['scope'], 'required: list of strings')
        self.assertEqual(result['spec']['mandate']['end_criteria'], 'required: nonempty text')
        self.assertIn('candidate_seq: int or null', self.ok('init', '--template', 'wave')['spec']['reviews'])
        self.assertEqual(list(self.fresh.iterdir()), [])
        self.usage_error('init', '--template', 'wave', self.fresh / 'wave.json')
        self.usage_error('init', self.fresh / 'wave.json', '--kind', 'wave', '--actor', OWNER)


class ReplaceInvalid(InitBase):
    def hand_written(self, **changes):
        w = wave2('planning')
        w.update(program_ref=None, mode='prepare')
        w['authorization'].update(launch=False, scope='synthetic lots')  # invalid: scope must be a list
        w['state'].update(owner=None, consumed={})
        w.update(changes)
        path = self.fresh / 'wave.json'
        self.write(path, w)
        return path

    def replace(self, path, *extra, actor=OWNER):
        return self.init(path, 'wave', WAVE_SPEC, '--replace-invalid', '--evidence', 'hand-written v9 initial file',
                         *extra, actor=actor)

    def test_invalid_initial_wave_replaced_and_preserved(self):
        path = self.hand_written()
        before = path.read_bytes()
        code, result = self.replace(path)
        self.assertEqual(code, 0, result)
        preserved = self.fresh / 'wave.invalid-1.json'
        self.assertEqual(preserved.read_bytes(), before)
        self.assertEqual(result['replaced']['preserved_as'], 'wave.invalid-1.json')
        self.assertTrue(self.ok('check', path)['valid'])
        entry = self.journal(self.fresh)[-1]
        self.assertEqual(entry['replaces']['evidence'], 'hand-written v9 initial file')
        self.assertEqual(entry['replaces']['old_sha256'], hashlib.sha256(before).hexdigest())
        self.assertTrue(any('authorization.scope' in e for e in entry['replaces']['old_errors']))
        self.refused('is valid', *self.replace_argv(path))

    def replace_argv(self, path):
        return ('init', path, '--kind', 'wave', '--actor', OWNER, '--role', 'pilot', '--spec', self.spec(WAVE_SPEC),
                '--replace-invalid', '--evidence', 'x')

    def test_owned_by_actor_accepted_and_names_stay_exclusive(self):
        state = dict(wave2('planning')['state'], owner={'role': 'pilot', 'ref': OWNER}, consumed={})
        path = self.hand_written(state=state)
        (self.fresh / 'wave.invalid-1.json').write_text('older evidence', encoding='utf-8')
        code, result = self.replace(path)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['replaced']['preserved_as'], 'wave.invalid-2.json')
        self.assertEqual((self.fresh / 'wave.invalid-1.json').read_text(encoding='utf-8'), 'older evidence')

    def test_replace_refusals_keep_file_untouched(self):
        other = {'role': 'pilot', 'ref': 'thread:other'}
        cases = [('not 0', {'revision': 1}),
                 ('owner other than', {'state': dict(wave2('planning')['state'], owner=other, consumed={})})]
        for fragment, changes in cases:
            path = self.hand_written(**changes)
            before = path.read_bytes()
            self.refused(fragment, *self.replace_argv(path))
            self.assertEqual(path.read_bytes(), before)
        path = self.fresh / 'wave.json'
        path.write_text('{"schema_version": 2, "revision": 0,', encoding='utf-8')
        self.refused('not readable JSON', *self.replace_argv(path))
        self.refused('is a program document', *self.replace_argv(self.write_program()))
        self.refused('no file to replace', *self.replace_argv(self.fresh / 'absent.json'))
        self.assertEqual(sorted(p.name for p in self.fresh.glob('*.invalid-*')), [])
        self.usage_error('init', path, '--kind', 'wave', '--actor', OWNER, '--role', 'pilot', '--replace-invalid')

    def write_program(self):
        bad = program()
        bad['mandate']['scope'] = 'x'
        path = self.fresh / 'other.json'
        self.write(path, bad)
        return path


class FieldMessages(Base):
    def test_mandate_message_per_field(self):
        p = program()
        p['mandate'].update(scope='synthetic', end_criteria=['A'])
        del p['mandate']['ref']
        errors = rc.validate_program(p, self.root)
        self.assertIn('mandate.scope: expected list of strings, got str', errors)
        self.assertIn('mandate.end_criteria: expected nonempty text, got list', errors)
        self.assertIn('mandate.ref: expected nonempty text, got missing', errors)
        self.assertFalse(any('mandate.exclusions' in e for e in errors), errors)
        p['mandate'] = None
        self.assertIn('mandate: expected object {ref, scope, exclusions, end_criteria}, got null',
                      rc.validate_program(p, self.root))

    def test_authorization_message_per_field(self):
        w = wave2()
        w['authorization'].update(launch='yes', scope='lots', exclusions=[3])
        del w['authorization']['source']
        errors = rc.validate_wave2(w, self.wave_path.parent)
        self.assertIn('authorization.launch: expected bool, got str', errors)
        self.assertIn('authorization.scope: expected list of strings or null, got str', errors)
        self.assertIn('authorization.exclusions: expected list of strings, got list with int at [0]', errors)
        self.assertIn('authorization.source: expected text or null, got missing', errors)
        self.write(self.wave_path, w)
        code, result = self.run_cli('check', self.wave_path)
        self.assertEqual(code, 1)
        self.assertIn('authorization.launch: expected bool, got str', result['errors'])
        w['authorization'] = ['launch']
        errors = rc.validate_wave2(w, self.wave_path.parent)
        self.assertEqual([e for e in errors if e.startswith('authorization')],
                         ['authorization: expected object {launch, source, scope, exclusions}, got list'])

    def test_other_cheap_fields(self):
        p = program()
        p['status'] = 'running'
        p['outcomes'][1]['next_action'] = ''
        errors = rc.validate_program(p, self.root)
        self.assertTrue(any(e.startswith("invalid program status: status: expected one of") and e.endswith("got 'running'")
                            for e in errors), errors)
        self.assertTrue(any('B: outcome and next_action required: outcomes.B.next_action: expected nonempty text, '
                            'got empty str' in e for e in errors), errors)
        w = wave2()
        w['mode'] = 'launch'
        w['project'] = {'root': 'r'}
        errors = rc.validate_wave2(w, self.wave_path.parent)
        self.assertIn("mode: expected one of prepare, prepare-and-launch, got 'launch'", errors)
        self.assertIn('project.baseline: expected text or null, got missing', errors)
        w = wave2()
        w['state'].pop('blockers')
        self.assertIn('state: missing blockers', rc.validate_wave2(w, self.wave_path.parent))


class WaveOnlyCommands(Base):
    def test_intent_on_program_refused_explicitly(self):
        argv = ['intent', self.program_path, 'add', '--actor', OWNER, '--expect-revision', 0,
                '--correlation', 'c1', '--op', 'launch', '--target', 'champion-A']
        result = self.refused('intents live in the wave.json', *argv)
        self.assertNotIn('internal', result)
        self.refused('intents live in the wave.json', 'intent', self.program_path, 'resolve', '--actor', OWNER,
                     '--expect-revision', 0, '--correlation', 'c1', '--status', 'absent')
        self.refused('transition refused: a program.json has no phase', 'transition', self.program_path,
                     '--actor', OWNER, '--expect-revision', 0, '--to', 'integrating')
        self.assertEqual(self.rev(self.program_path), 0)


class ResumeAndReady(Base):
    def shared_wave_program(self):
        p = program()
        p['outcomes'][1].update(status='admitted', depends_on=[], state_ref='waves/a/wave.json')
        self.write(self.program_path, p)

    def test_resume_actions_deduplicated_per_wave(self):
        self.shared_wave_program()
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 0, '--correlation', 'a/1',
                '--op', 'launch', '--target', 'champion-A')
        self.ok('intent', self.wave_path, 'resolve', '--actor', OWNER, '--expect-revision', 1, '--correlation', 'a/1',
                '--status', 'confirmed', '--result-ref', 'task-A', '--role', 'champion')
        self.ok('intent', self.wave_path, 'add', '--actor', OWNER, '--expect-revision', 2, '--correlation', 'a/2',
                '--op', 'send', '--target', 'champion-A')
        result = self.ok('resume', self.program_path)
        intents = [a for a in result['actions'] if 'reconcile intent a/2' in a]
        actors = [a for a in result['actions'] if 'actor a/1' in a]
        self.assertEqual(len(intents), 1, result['actions'])
        self.assertEqual(len(actors), 1, result['actions'])
        self.assertIn('waves/a/wave.json (outcomes A, B)', intents[0])
        self.assertEqual([w['outcome'] for w in result['waves']], ['A', 'B'])
        self.assertEqual(len(result['actions']), len(set(result['actions'])))

    def test_admitted_admitted_conflict_between_waves(self):
        p = program()
        p['outcomes'][1].update(status='admitted', depends_on=[], state_ref='waves/b/wave.json', resources=['port-1'])
        view = rc.ready_view(p)
        self.assertEqual(view['resource_conflicts'],
                         [{'kind': 'admitted-admitted', 'outcomes': ['A', 'B'], 'resources': ['port-1']}])
        p['outcomes'][1]['state_ref'] = 'waves/a/./wave.json'  # same wave: shared by design
        self.assertEqual(rc.ready_view(p)['resource_conflicts'], [])


class ReviewCandidateSeq(Base):
    def test_null_candidate_seq_is_out_of_candidate(self):
        w = wave2()
        review = {'artifact': 'prompt_a', 'sha256': 'a' * 64, 'status': 'done', 'disposition': 'ok',
                  'reference': 'r.md', 'candidate_seq': None}
        w['reviews'] = [review]
        self.assertEqual(rc.validate_wave2(w, self.wave_path.parent), [])
        w['reviews'] = [dict(review, candidate_seq='1')]
        errors = rc.validate_wave2(w, self.wave_path.parent)
        self.assertTrue(any('candidate_seq must be an integer or null' in e and 'got str' in e for e in errors), errors)
        ops = json.dumps([{'op': 'append', 'path': 'reviews', 'value': review}])
        self.ok('write', self.wave_path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)



class InitReview(InitBase):
    """Review corrections V91-R1, R2, R4 and write help."""

    def admitted_program(self):
        wave_path = self.fresh / 'waves/c/wave.json'
        wave_path.parent.mkdir(parents=True)
        self.assertEqual(self.init(wave_path, 'wave', WAVE_SPEC)[0], 0)
        spec = json.loads(json.dumps(PROGRAM_SPEC))
        spec['outcomes'][0].update(status='admitted', state_ref='waves/c/wave.json')
        program_path = self.fresh / 'program.json'
        self.assertEqual(self.init(program_path, 'program', spec)[0], 0)
        return program_path, wave_path

    def kinds(self, directory, ident):
        return [e['kind'] for e in self.journal(directory) if e.get('wave') == ident]

    def tmp_files(self, directory):
        return [p.name for p in directory.iterdir() if p.name.endswith('.tmp')]

    def test_R1_tool_initialized_state_is_reconciled_not_reinitialized(self):
        program_path, wave_path = self.admitted_program()
        self.ok('transition', wave_path, '--actor', OWNER, '--expect-revision', 0, '--to', 'stopped')
        self.assertTrue(any('admitted but wave is stopped' in e for e in rc.validate_program(
            self.doc(program_path), self.fresh, self_path=program_path)))
        before = program_path.read_bytes()
        result = self.refused('already records operations on program.json', 'init', program_path, '--kind', 'program',
                              '--actor', OWNER, '--role', 'pilot', '--spec', self.spec(PROGRAM_SPEC),
                              '--replace-invalid', '--evidence', 'admitted wave stopped by another actor')
        self.assertIn('reconcile its inconsistency', result['error'])
        self.assertEqual(program_path.read_bytes(), before)
        self.assertEqual(self.doc(program_path)['outcomes'][0]['state_ref'], 'waves/c/wave.json')
        self.assertEqual(self.kinds(self.fresh, 'program.json'), ['prepare', 'init'])
        self.assertEqual(list(self.fresh.glob('*.invalid-*')), [])

    def test_R2_commit_failure_is_uncertain_until_reconciled(self):
        path = self.fresh / 'program.json'
        real = rc.append_journal

        def fail_commit(jpath, entry):
            if entry.get('kind') == 'init':
                raise OSError('injected after publication')
            return real(jpath, entry)

        with mock.patch.object(rc, 'append_journal', side_effect=fail_commit):
            code, result = self.init(path, 'program', PROGRAM_SPEC)
        self.assertEqual(code, 1, result)
        self.assertIn('stays unresolved', result['error'])
        self.assertTrue(self.ok('check', path)['valid'])
        ops = json.dumps([{'op': 'set', 'path': 'status_reason', 'value': 'x'}])
        self.refused('unresolved state operation', 'write', path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)
        code, cold = self.run_cli('resume', path)
        self.assertEqual(code, 1)
        op = cold['uncertain_operations'][0]
        self.assertEqual(op['op_kind'], 'init')
        self.assertTrue(any(op['id'] in a for a in cold['actions']), cold['actions'])
        self.refused('only the author of init', 'reconcile', path, '--actor', 'thread:other', '--op', op['id'],
                     '--evidence', 'x')
        result = self.ok('reconcile', path, '--actor', OWNER, '--op', op['id'], '--evidence', 'state bytes checked')
        self.assertEqual(result['outcome'], 'committed')
        self.assertEqual(self.ok('write', path, '--actor', OWNER, '--expect-revision', 0, '--ops', ops)['revision'], 1)

    def test_R2_crash_before_publication_resolves_not_committed(self):
        path = self.fresh / 'program.json'
        argv = ['init', str(path), '--kind', 'program', '--actor', OWNER, '--role', 'pilot',
                '--spec', str(self.spec(PROGRAM_SPEC))]
        with mock.patch.object(rc, 'create_exclusive', side_effect=KeyboardInterrupt('process killed')):
            with self.assertRaises(KeyboardInterrupt), contextlib.redirect_stdout(io.StringIO()):
                rc.main(argv)
        self.assertFalse(path.exists())
        self.assertEqual(len(self.tmp_files(self.fresh)), 1)
        self.refused('unresolved state operation', *argv)
        op = next(e for e in self.journal(self.fresh) if e['kind'] == 'prepare')
        result = self.ok('reconcile', path, '--actor', OWNER, '--op', op['id'], '--evidence', 'no state file')
        self.assertEqual((result['outcome'], result['removed_own_temporary']), ('not_committed', op['tmp']))
        self.assertEqual(self.tmp_files(self.fresh), [])
        code, result = self.init(path, 'program', PROGRAM_SPEC)
        self.assertEqual(code, 0, result)  # a voided init is no history
        self.assertEqual(self.kinds(self.fresh, 'program.json'), ['prepare', 'resolve', 'prepare', 'init'])

    def test_R2_bad_journal_refused_before_any_publication(self):
        journal = self.fresh / 'journal.jsonl'
        journal.write_bytes(b'')
        try:
            os.link(journal, self.fresh / 'alias.jsonl')
        except OSError as exc:
            self.skipTest(f'hard links unavailable: {exc}')
        path = self.fresh / 'program.json'
        self.refused('single link', 'init', path, '--kind', 'program', '--actor', OWNER, '--role', 'pilot',
                     '--spec', self.spec(PROGRAM_SPEC))
        self.assertFalse(path.exists())
        self.assertEqual((journal.read_bytes(), self.tmp_files(self.fresh)), (b'', []))

    def test_R4_failed_replacement_removes_only_its_temporary(self):
        path = ReplaceInvalid.hand_written(self)
        before = path.read_bytes()
        with mock.patch.object(rc.os, 'replace', side_effect=PermissionError('handle open without delete sharing')):
            code, result = ReplaceInvalid.replace(self, path)
        self.assertEqual(code, 1, result)
        self.assertIn('not published', result['error'])
        self.assertEqual((path.read_bytes(), self.tmp_files(self.fresh)), (before, []))
        self.assertEqual((self.fresh / 'wave.invalid-1.json').read_bytes(), before)
        op = next(e for e in self.journal(self.fresh) if e['kind'] == 'prepare')
        result = self.ok('reconcile', path, '--actor', OWNER, '--op', op['id'], '--evidence', 'old bytes in place')
        self.assertEqual(result['outcome'], 'not_committed')
        code, result = ReplaceInvalid.replace(self, path)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['replaced']['preserved_as'], 'wave.invalid-2.json')

    def test_write_list_index_points_to_match(self):
        for path in ('outcomes.0.status', 'outcomes.1'):
            ops = json.dumps([{'op': 'set', 'path': path, 'value': 'admitted'}])
            result = self.refused('outcomes is a list', 'write', self.program_path, '--actor', OWNER,
                                  '--expect-revision', 0, '--ops', ops)
            self.assertIn('"op":"update","path":"outcomes","match"', result['error'])
        out = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(out):
            rc.main(['write', '--help'])
        self.assertIn('[{"op":"update","path":"outcomes","match":{"id":"B1"}', out.getvalue())
        self.assertIn('[{"op":"set","path":"status_reason"', out.getvalue())


class V911Messages(Base):
    """v9.1.1: a v2 wave report carries no `v1-fields:` prefix; the template states when prompt_artifact is due."""

    def test_v2_wave_errors_carry_no_version_prefix(self):
        w = wave2('launched')
        w['state']['consumed'] = {}
        w['batches'] = [['ZZ']]
        errors = rc.validate_wave2(w)
        self.assertIn('operational state requires nonempty consumed mandates', errors)
        self.assertIn('unknown batch ID', errors)
        self.assertFalse([e for e in errors if e.startswith('v1-fields')], errors)

    def test_template_states_prompt_artifact_is_due_before_launch(self):
        socle = self.ok('init', '--template', 'wave')['spec']['socles'][0]
        self.assertIn('required before launch_ready=true', socle['prompt_artifact'])


if __name__ == '__main__':
    unittest.main()
