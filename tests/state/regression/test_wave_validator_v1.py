"""Synthetic document tests; temporary fixtures stay beside this file."""
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
PACKAGE = Path(__import__('os').environ.get('RC_STATE_PACKAGE', str(ROOT.parents[1] / 'package')))
FIXTURES = ROOT.parent / '_fixtures'
CHECKER = PACKAGE / 'rc-coordinate-development/scripts/check_wave.py'
spec = importlib.util.spec_from_file_location('wave_check', CHECKER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def wave():
    return {
        'schema_version': 1, 'mode': 'prepare',
        'project': {'root': None, 'baseline': None, 'observed_at': None},
        'authorization': {'launch': False, 'source': 'synthetic preparation',
                          'scope': [], 'exclusions': []},
        'socles': [
            {'id': 'SENSOR', 'outcome': 'Synthetic events', 'depends_on': [],
             'readiness': 'ready', 'resources': [], 'source_refs': []},
            {'id': 'ROUTE', 'outcome': 'Synthetic routes', 'depends_on': [],
             'readiness': 'partial', 'resources': [], 'source_refs': [],
             'ready_scope': 'Local routing fixtures',
             'blocked_scope': 'Consume the event schema later',
             'consumption_dependencies': [
                 {'producer': 'SENSOR', 'artifact': 'event-schema',
                  'consumer_scope': 'Schema-bound routes',
                  'continue_scope': 'Local routing fixtures'}]}],
        'batches': [['SENSOR', 'ROUTE']], 'artifacts': {}, 'reviews': [],
        'decisions': [],
        'state': {'phase': 'ready', 'owner': None,
                  'next_action': 'Return the synthetic documents',
                  'blockers': [], 'runtime_refs': None,
                  'consumed': {}, 'launch_ready': False}}


def launch(directory):
    """Declare a launch on synthetic artifacts, without launching anything."""
    data = wave()
    data['mode'] = 'prepare-and-launch'
    data['project'] = {'root': str(directory / 'declared-project'),
                       'baseline': 'synthetic-base-1', 'observed_at': 'synthetic-observation'}
    data['authorization'] = {'launch': True, 'source': 'synthetic applicable request',
                             'scope': ['Synthetic routing fixtures'], 'exclusions': ['Real services']}
    data['state']['owner'] = {'role': 'supervisor', 'ref': 'synthetic-actor-reference'}
    data['state']['launch_ready'] = True
    data['socles'][0]['prompt_artifact'] = 'supervisor'
    data['socles'][1]['prompt_artifact'] = 'route_prompt'
    for name, relative, content in (
            ('supervisor', 'supervisor.txt', b'Synthetic supervisor mandate.\n'),
            ('route_prompt', 'socles/route.txt', b'Synthetic routing prompt.\n')):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        sha256 = hashlib.sha256(content).hexdigest()
        data['artifacts'][name] = relative
        data['state']['consumed'][name] = {'version': 'fixture-v1', 'sha256': sha256}
        data['reviews'].append({'artifact': name, 'sha256': sha256, 'status': 'done',
                                'disposition': 'Synthetic findings disposed',
                                'reference': 'synthetic-review-reference'})
    return data


def rename_artifact(data, old, new):
    """Rename one synthetic artifact key without inventing another mandate."""
    data['artifacts'][new] = data['artifacts'].pop(old)
    data['state']['consumed'][new] = data['state']['consumed'].pop(old)
    for review in data['reviews']:
        if review['artifact'] == old:
            review['artifact'] = new
    for socle in data['socles']:
        if socle.get('prompt_artifact') == old:
            socle['prompt_artifact'] = new


class WaveChecks(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(exist_ok=True)  # R1 observed a first run failing when this parent was absent
        self.temp = tempfile.TemporaryDirectory(prefix='checker-fixtures-', dir=FIXTURES)
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.directory = self.area / 'wave'
        self.directory.mkdir()

    def errors(self, data, check_paths=False):
        return module.validate(data, self.directory, check_paths=check_paths)

    def assert_error(self, data, fragment, check_paths=False):
        errors = self.errors(data, check_paths)
        self.assertTrue(any(fragment in error for error in errors), errors)

    def cli(self, data=None, *, encoding='utf-8', raw=None, check_paths=False):
        path = self.directory / 'wave.json'
        path.write_text(raw if raw is not None else json.dumps(data), encoding=encoding)
        args = [sys.executable, '-B', str(CHECKER), str(path)]
        if check_paths:
            args.append('--check-paths')
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual('', result.stderr)
        return result, json.loads(result.stdout)

    def test_preparation_partial_and_null_owner_are_valid_without_mutation(self):
        data = wave()
        before = copy.deepcopy(data)
        self.assertEqual([], self.errors(data))
        self.assertEqual(before, data)

    def test_owner_field_is_required_even_during_preparation(self):
        data = wave()
        del data['state']['owner']
        self.assert_error(data, 'invalid state fields')

    def test_preparation_waits_can_describe_documentary_quota_or_children(self):
        for phase in ('waiting_quota', 'waiting_children'):
            with self.subTest(phase=phase):
                data = wave()
                data['state']['phase'] = phase
                data['state']['runtime_refs'] = [{'ref': 'synthetic-documentary-reviewer'}]
                data['state']['next_action'] = 'Resume the documentary review when its author signals'
                data['decisions'] = ['Documentary review only; return state to the parent while waiting']
                self.assertEqual([], self.errors(data))

    def test_operational_wait_with_referenced_actors_requires_known_owner(self):
        for phase in ('waiting_quota', 'waiting_children'):
            with self.subTest(phase=phase):
                data = wave()
                data['mode'] = 'prepare-and-launch'
                data['state'].update(phase=phase, runtime_refs=[{'ref': 'synthetic-existing-actor'}])
                self.assert_error(data, 'operational waiting with runtime_refs requires state.owner.ref')
                data['state']['owner'] = {'role': 'supervisor', 'ref': 'synthetic-holder'}
                self.assertEqual([], self.errors(data))

    def test_wait_without_referenced_actors_can_remain_unowned_preparation(self):
        for refs in (None, []):
            with self.subTest(refs=refs):
                data = wave()
                data['mode'] = 'prepare-and-launch'
                data['state'].update(phase='waiting_quota', runtime_refs=refs)
                self.assertEqual([], self.errors(data))

    def test_preparation_rejects_launch_authorization_and_readiness_flags(self):
        for field in ('launch', 'launch_ready'):
            with self.subTest(field=field):
                data = wave()
                target = data['authorization'] if field == 'launch' else data['state']
                target[field] = True
                self.assert_error(data, 'prepare requires')

    def test_each_product_phase_requires_mode_and_authority_even_when_not_launch_ready(self):
        for phase in sorted(module.PRODUCT_PHASES):
            for missing in ('mode', 'launch', 'source'):
                with self.subTest(phase=phase, missing=missing):
                    data = launch(self.directory)
                    data['state'].update(phase=phase, launch_ready=False)
                    if missing == 'mode':
                        data['mode'] = 'prepare'
                    else:
                        data['authorization'][missing] = False if missing == 'launch' else None
                    self.assert_error(data, 'operational state lacks')

    def test_product_phase_declarations_do_not_require_the_readiness_flag_to_stay_true(self):
        for phase in sorted(module.PRODUCT_PHASES):
            with self.subTest(phase=phase):
                data = launch(self.directory)
                data['state'].update(phase=phase, launch_ready=False)
                self.assertEqual([], self.errors(data))

    def test_each_product_phase_retains_consumed_mandates_when_readiness_is_reset(self):
        for phase in sorted(module.PRODUCT_PHASES):
            with self.subTest(phase=phase):
                data = launch(self.directory)
                data['state'].update(phase=phase, launch_ready=False, consumed={})
                self.assert_error(data, 'requires nonempty consumed mandates')

    def test_handoff_requires_a_known_owner_reference(self):
        for owner in (None, {'role': 'supervisor', 'ref': None},
                      {'role': 'supervisor', 'ref': ''}):
            with self.subTest(owner=owner):
                data = launch(self.directory)
                data['state'].update(phase='handed_off', launch_ready=False, owner=owner)
                self.assert_error(data, 'requires state.owner.ref')

    def test_fully_declared_launch_and_exact_local_hashes_are_valid(self):
        data = launch(self.directory)
        self.assertEqual([], self.errors(data, check_paths=True))
        self.assertFalse(Path(data['project']['root']).exists())  # Context is a declaration only.

    def test_launch_ready_requires_declared_context_owner_authorization_scope_and_no_blockers(self):
        cases = [
            (('state', 'owner'), None, 'owner.ref'),
            (('authorization', 'source'), None, 'mode/authorization/source'),
            (('authorization', 'scope'), [], 'authorization.scope'),
            (('state', 'blockers'), ['Selected launch has an unresolved review'], 'no blockers')]
        cases.extend((('project', field), None, 'declared project context')
                     for field in ('root', 'baseline', 'observed_at'))
        for (section, field), value, fragment in cases:
            with self.subTest(section=section, field=field):
                data = launch(self.directory)
                data[section][field] = value
                self.assert_error(data, fragment)

    def test_launch_ready_requires_at_least_one_admitted_executable_path(self):
        data = launch(self.directory)
        data['batches'] = []
        self.assert_error(data, 'executable admitted scope')
        data['batches'] = [['SENSOR', 'ROUTE']]
        for socle in data['socles']:
            socle['readiness'] = 'blocked'
        self.assert_error(data, 'executable admitted scope')

    def test_deferred_blocked_socle_and_unconsumed_pending_review_do_not_block_selected_launch(self):
        data = launch(self.directory)
        data['socles'].append({'id': 'ARCHIVE', 'outcome': 'Future archive',
                               'depends_on': [], 'readiness': 'blocked',
                               'resources': [], 'source_refs': []})
        data['artifacts']['future_prompt'] = 'future.txt'
        (self.directory / 'future.txt').write_bytes(b'Synthetic deferred draft')
        data['reviews'].append({'artifact': 'future_prompt', 'sha256': '0' * 64,
                                'status': 'pending', 'disposition': None, 'reference': None})
        data['decisions'] = ['ARCHIVE and its draft are deferred; consume neither']
        self.assertEqual([], self.errors(data, check_paths=True))

    def test_launch_ready_consumes_supervisor_when_that_key_is_declared(self):
        data = launch(self.directory)
        del data['state']['consumed']['supervisor']
        self.assert_error(data, 'consumed declared supervisor')

    def test_launch_ready_accepts_a_mandate_under_another_key(self):
        data = launch(self.directory)
        rename_artifact(data, 'supervisor', 'coordination_mandate')
        self.assertNotIn('supervisor', data['artifacts'])
        self.assertEqual([], self.errors(data, check_paths=True))

    def test_launch_ready_requires_some_consumed_mandate_without_a_reserved_key(self):
        data = launch(self.directory)
        rename_artifact(data, 'supervisor', 'direct_mandate')
        data['state']['consumed'] = {}
        self.assert_error(data, 'requires nonempty consumed mandates')

    def test_direct_work_in_the_same_thread_can_share_one_reviewed_mandate(self):
        data = launch(self.directory)
        rename_artifact(data, 'supervisor', 'direct_mandate')
        data['state']['owner']['role'] = 'coordinator acting as supervisor'
        data['socles'][1]['prompt_artifact'] = 'direct_mandate'
        del data['state']['consumed']['route_prompt']
        data['reviews'][1]['status'] = 'not_executed'
        data['decisions'] = ['Both admitted paths are covered by the direct mandate in this thread']
        self.assertEqual([], self.errors(data, check_paths=True))

    def test_all_admitted_unblocked_lots_must_identify_their_mandate(self):
        for name in (None, [], 'unknown-key'):
            with self.subTest(name=name):
                data = launch(self.directory)
                data['socles'][1]['prompt_artifact'] = name
                self.assert_error(data, 'ROUTE: admitted socle requires prompt_artifact key in artifacts')

    def test_an_admitted_lot_cannot_hide_its_unreviewed_prompt_outside_consumed(self):
        data = launch(self.directory)
        entry = data['state']['consumed'].pop('route_prompt')
        data['reviews'][1]['status'] = 'pending'
        self.assert_error(data, 'ROUTE: admitted prompt_artifact must be consumed')
        data['state']['consumed']['route_prompt'] = entry
        self.assert_error(data, 'route_prompt: launch_ready requires disposed reviews')

    def test_a_deferred_lot_leaves_batches_until_its_prompt_can_be_consumed(self):
        data = launch(self.directory)
        data['state']['consumed'].pop('route_prompt')
        data['reviews'][1]['status'] = 'pending'
        data['batches'] = [['SENSOR']]
        data['decisions'] = ['ROUTE stays outside admission until its prompt is reviewed']
        self.assertEqual([], self.errors(data, check_paths=True))

    def test_prepare_without_launch_readiness_does_not_require_consumed_lot_prompts(self):
        data = wave()
        data['socles'][1]['prompt_artifact'] = 'not-yet-authored'
        self.assertEqual([], self.errors(data))

    def test_consumed_records_require_known_artifact_version_and_sha256(self):
        for entry in (None, [], {}, {'version': None, 'sha256': '0' * 64},
                      {'version': 'v1', 'sha256': 'incorrect'},
                      {'version': 1, 'sha256': '0' * 64}):
            with self.subTest(entry=entry):
                data = wave()
                data['artifacts']['draft'] = 'draft.txt'
                data['state']['consumed']['draft'] = entry
                self.assert_error(data, 'consumed version and sha256 required')
        data = wave()
        data['state']['consumed']['absent'] = {'version': 'v1', 'sha256': '0' * 64}
        self.assert_error(data, 'consumed artifact is unknown')

    def test_all_consumed_artifacts_need_reviews_not_just_supervisor(self):
        data = launch(self.directory)
        data['reviews'] = data['reviews'][:1]
        self.assert_error(data, 'route_prompt: launch_ready requires disposed reviews')

    def test_missing_pending_and_unexecuted_reviews_cannot_cover_launch(self):
        for status in (None, 'pending', 'not_executed'):
            with self.subTest(status=status):
                data = launch(self.directory)
                if status is None:
                    data['reviews'] = []
                else:
                    data['reviews'][0]['status'] = status
                self.assert_error(data, 'supervisor: launch_ready requires disposed reviews')

    def test_review_for_an_older_hash_cannot_cover_the_consumed_version(self):
        data = launch(self.directory)
        data['reviews'][0]['sha256'] = '0' * 64
        self.assert_error(data, 'supervisor: launch_ready requires disposed reviews')

    def test_an_old_review_record_does_not_replace_or_block_current_coverage(self):
        data = launch(self.directory)
        historical = copy.deepcopy(data['reviews'][0])
        historical.update(sha256='0' * 64, status='not_executed',
                          disposition='Superseded synthetic draft', reference=None)
        data['reviews'].append(historical)
        self.assertEqual([], self.errors(data, check_paths=True))

    def test_not_required_is_accepted_only_with_disposition_and_reference(self):
        data = launch(self.directory)
        review = data['reviews'][0]
        review.update(status='not_required', disposition='Synthetic mission excludes this review',
                      reference='synthetic applicable decision')
        self.assertEqual([], self.errors(data, check_paths=True))
        for field in ('disposition', 'reference'):
            with self.subTest(field=field):
                invalid = copy.deepcopy(data)
                invalid['reviews'][0][field] = None
                self.assert_error(invalid, 'disposed review requires disposition and reference')

    def test_done_review_requires_findings_disposition_and_reference(self):
        for field in ('disposition', 'reference'):
            with self.subTest(field=field):
                data = launch(self.directory)
                data['reviews'][0][field] = None
                self.assert_error(data, 'disposed review requires disposition and reference')

    def test_pending_review_on_the_same_hash_is_not_erased_by_a_done_record(self):
        data = launch(self.directory)
        pending = copy.deepcopy(data['reviews'][0])
        pending['status'] = 'pending'
        data['reviews'].append(pending)
        self.assert_error(data, 'requires disposed reviews')

    def test_hashes_are_compared_with_bytes_only_when_check_paths_is_requested(self):
        data = launch(self.directory)
        (self.directory / 'supervisor.txt').write_bytes(b'Mutated synthetic mandate.\n')
        self.assertEqual([], self.errors(data))
        self.assert_error(data, 'supervisor: consumed sha256 mismatch with local artifact', check_paths=True)

    def test_agreeing_but_fabricated_hashes_do_not_pass_local_hash_check(self):
        data = launch(self.directory)
        data['state']['consumed']['supervisor']['sha256'] = 'f' * 64
        data['reviews'][0]['sha256'] = 'f' * 64
        self.assertEqual([], self.errors(data))
        self.assert_error(data, 'sha256 mismatch with local artifact', check_paths=True)

    def test_hash_comparison_is_case_insensitive(self):
        data = launch(self.directory)
        data['state']['consumed']['supervisor']['sha256'] = data['reviews'][0]['sha256'].upper()
        self.assertEqual([], self.errors(data, check_paths=True))

    def test_structural_validation_reads_no_artifact_contents(self):
        data = launch(self.directory)
        with mock.patch.object(Path, 'open', side_effect=AssertionError('unexpected artifact read')):
            self.assertEqual([], self.errors(data))

    def test_missing_file_is_checked_only_under_check_paths(self):
        data = wave()
        data['artifacts']['draft'] = 'missing.txt'
        self.assertEqual([], self.errors(data))
        self.assert_error(data, 'artifact not found', check_paths=True)

    def test_artifact_paths_remain_strings_separate_from_metadata(self):
        data = wave()
        data['artifacts']['draft'] = {'path': 'draft.txt', 'version': 'v1'}
        self.assert_error(data, 'local relative artifact path required')

    def test_path_escape_is_rejected_even_if_synthetic_target_exists(self):
        outside = self.area / 'outside.txt'
        outside.write_text('Synthetic sibling fixture', encoding='utf-8')
        for relative in ('../outside.txt', r'..\outside.txt', 'nested/../../outside.txt'):
            with self.subTest(relative=relative):
                data = wave()
                data['artifacts']['draft'] = relative
                self.assert_error(data, 'no escape')

    def test_absolute_drive_unc_and_url_paths_are_rejected_portably(self):
        for relative in ('/outside.txt', r'C:\synthetic\outside.txt', 'C:outside.txt',
                         r'\\synthetic\share\outside.txt', r'\outside.txt',
                         'https://invalid.example/fixture', 'draft.txt:stream', '\x00'):
            with self.subTest(relative=relative):
                data = wave()
                data['artifacts']['draft'] = relative
                self.assert_error(data, 'local relative artifact path required')

    def test_normalized_internal_relative_path_is_valid(self):
        data = wave()
        (self.directory / 'draft.txt').write_bytes(b'Synthetic draft')
        data['artifacts']['draft'] = 'nested/../draft.txt'
        self.assertEqual([], self.errors(data, check_paths=True))

    def test_resolved_path_escape_is_rejected_without_reading_sibling(self):
        data = wave()
        data['artifacts']['draft'] = 'alias.txt'
        original_resolve = Path.resolve

        def resolving(path, *args, **kwargs):
            if path.name == 'alias.txt':
                return self.area / 'outside.txt'
            return original_resolve(path, *args, **kwargs)

        with mock.patch.object(Path, 'resolve', new=resolving):
            self.assert_error(data, 'artifact path escapes wave directory', check_paths=True)

    def test_partial_requires_both_scopes_even_before_launch(self):
        for field in ('ready_scope', 'blocked_scope'):
            with self.subTest(field=field):
                data = wave()
                del data['socles'][1][field]
                self.assert_error(data, 'partial requires ready_scope and blocked_scope')

    def test_self_consumption_is_rejected(self):
        data = wave()
        data['socles'][1]['consumption_dependencies'][0]['producer'] = 'ROUTE'
        self.assert_error(data, 'self-consumption is invalid')

    def cycle(self):
        data = wave()
        data['socles'][0]['consumption_dependencies'] = [
            {'producer': 'ROUTE', 'artifact': 'route-schema',
             'consumer_scope': 'Dispatch against route schema',
             'continue_scope': 'Draft the event schema independently'}]
        return data

    def test_consumption_cycle_without_bootstrap_scope_is_reported(self):
        data = self.cycle()
        data['decisions'] = ['Unresolved circular consumption']
        self.assert_error(data, 'consumption cycle requires explicit ready_scope')

    def test_consumption_cycle_with_scopes_but_without_decision_is_reported(self):
        data = self.cycle()
        data['socles'][0]['ready_scope'] = 'Draft the event schema independently'
        self.assert_error(data, 'bootstrap decision')

    def test_consumption_cycle_can_declare_independent_bootstrap(self):
        data = self.cycle()
        self.assertEqual('ready', data['socles'][0]['readiness'])
        data['socles'][0]['ready_scope'] = 'Draft the event schema independently'
        data['decisions'] = ['Both schema authors publish independently; only downstream binding waits']
        self.assertEqual([], self.errors(data))

    def test_scoped_bootstrap_cycle_does_not_prohibit_a_fully_declared_launch(self):
        data = launch(self.directory)
        self.assertEqual('ready', data['socles'][0]['readiness'])
        data['socles'][0]['consumption_dependencies'] = self.cycle()['socles'][0]['consumption_dependencies']
        data['socles'][0]['ready_scope'] = 'Publish the event schema independently'
        data['decisions'] = ['Publish both schemas before binding their downstream consumers']
        self.assertEqual([], self.errors(data, check_paths=True))

    def test_hard_dependency_cycles_are_distinct_from_scoped_consumption_cycles(self):
        data = self.cycle()
        data['socles'][0]['ready_scope'] = 'Draft event schema'
        data['decisions'] = ['Independent schema bootstrap']
        data['socles'][0]['depends_on'] = ['ROUTE']
        data['socles'][1]['depends_on'] = ['SENSOR']
        self.assert_error(data, 'hard dependency cycle')

    def test_hard_dependency_requires_earlier_admission(self):
        data = wave()
        data['socles'][1]['depends_on'] = ['SENSOR']
        self.assert_error(data, 'hard dependency not admitted earlier')
        data['batches'] = [['SENSOR'], ['ROUTE']]
        self.assertEqual([], self.errors(data))

    def test_unknown_producer_or_batch_and_duplicate_admission_are_rejected(self):
        data = wave()
        data['socles'][1]['consumption_dependencies'][0]['producer'] = 'MISSING'
        self.assert_error(data, 'incomplete consumption dependency')
        data = wave()
        data['batches'].append(['MISSING'])
        self.assert_error(data, 'unknown batch ID')
        data = wave()
        data['batches'].append(['SENSOR'])
        self.assert_error(data, 'duplicate batch ID')

    def test_no_universal_actor_limit_or_inferred_resource_rule(self):
        data = wave()
        prototype = copy.deepcopy(data['socles'][0])
        data['socles'] = [dict(prototype, id='PART-' + str(index)) for index in range(7)]
        for socle in data['socles']:
            socle['resources'] = ['declared-shared-fixture-resource']
        data['batches'] = [[socle['id'] for socle in data['socles']]]
        self.assertEqual([], self.errors(data))

    def test_malformed_json_field_types_return_errors_without_exceptions(self):
        cases = [
            ('mode', []), ('project', []), ('authorization', []),
            ('socles', {}), ('socles', [None]), ('batches', {}),
            ('batches', [[{}]]), ('artifacts', []), ('reviews', {}),
            ('reviews', [None]), ('decisions', {}), ('state', [])]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                data = wave()
                data[field] = value
                self.assertTrue(self.errors(data))
        for field, value in (('phase', []), ('owner', []), ('consumed', []),
                             ('blockers', {}), ('launch_ready', []), ('next_action', {})):
            with self.subTest(state_field=field):
                data = wave()
                data['state'][field] = value
                self.assertTrue(self.errors(data))
        for field, value in (('id', {}), ('readiness', {}), ('depends_on', [{}]),
                             ('consumption_dependencies', [{'producer': []}])):
            with self.subTest(socle_field=field):
                data = wave()
                data['socles'][0][field] = value
                self.assertTrue(self.errors(data))
        data = launch(self.directory)
        data['reviews'][0].update(artifact=[], sha256={}, status=[])
        self.assertTrue(self.errors(data))
        self.assertEqual(['wave must be an object'], module.validate([]))

    def test_cli_accepts_utf8_bom_and_emits_read_only_limits(self):
        result, payload = self.cli(wave(), encoding='utf-8-sig')
        self.assertEqual(0, result.returncode)
        self.assertTrue(payload['valid'])
        self.assertIn('Cannot certify', payload['limits'])

    def test_cli_invalid_json_and_types_produce_clean_json_errors(self):
        for raw in ('{bad json', '[]', '{"mode": []}'):
            with self.subTest(raw=raw):
                result, payload = self.cli(raw=raw)
                self.assertEqual(1, result.returncode)
                self.assertFalse(payload['valid'])
                self.assertTrue(payload['errors'])

    def test_cli_errors_remain_json_on_a_limited_console_encoding(self):
        data = wave()
        data['artifacts']['\u4eba\u5de5'] = '../outside.txt'
        path = self.directory / 'wave.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        output = io.BytesIO()
        console = io.TextIOWrapper(output, encoding='ascii')
        with mock.patch.object(sys, 'argv', [str(CHECKER), str(path)]), \
                mock.patch.object(sys, 'stdout', console):
            self.assertEqual(1, module.main())
        console.flush()
        payload = json.loads(output.getvalue().decode('ascii'))
        self.assertFalse(payload['valid'])
        self.assertIn('\u4eba\u5de5', payload['errors'][0])

    def test_cli_check_paths_detects_a_real_byte_change(self):
        data = launch(self.directory)
        result, payload = self.cli(data, check_paths=True)
        self.assertEqual(0, result.returncode)
        self.assertTrue(payload['valid'])
        (self.directory / 'socles/route.txt').write_bytes(b'Synthetic changed route prompt')
        result, payload = self.cli(data, check_paths=True)
        self.assertEqual(1, result.returncode)
        self.assertFalse(payload['valid'])
        self.assertTrue(any('route_prompt: consumed sha256 mismatch' in error for error in payload['errors']))

    def test_validator_and_cli_do_not_write_artifacts_or_mutate_documents(self):
        data = launch(self.directory)
        path = self.directory / 'wave.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        before_doc = copy.deepcopy(data)

        def tree():
            return {str(p.relative_to(self.area)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.area.rglob('*') if p.is_file()}

        before_files = tree()
        self.assertEqual([], self.errors(data, check_paths=True))
        result = subprocess.run([sys.executable, '-B', str(CHECKER), str(path), '--check-paths'],
                                capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before_doc, data)
        self.assertEqual(before_files, tree())


if __name__ == '__main__':
    unittest.main()
