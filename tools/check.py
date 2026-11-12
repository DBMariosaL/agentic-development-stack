"""Run the offline repository checks using synthetic files and isolated profiles.

Steps:
  inventory   manifest.json against package/, provenance.json against every listed file
  state       tests/state, unchanged v7 state regressions
  updater-v7  tests/updater/test_rc_update.py, unchanged, against the frozen v7 fixture
              (31 October -> v7, three RC skills)
  updater-v8  tests/updater/test_rc_update_v8.py: three -> six skills and dependencies
  updater-from-v8
              tests/updater/test_update_from_v8.py: an installed v8 (compact frozen reference
              tests/fixtures/v8) updated to package/: RC files replaced, dependencies untouched
  updater-from-v9
              tests/updater/test_update_from_v9.py: the same for an installed v9 (compact frozen
              reference tests/fixtures/v9)
  updater-from-v9.1
              tests/updater/test_update_from_v9_1.py: the same for an installed v9.1 (compact
              frozen reference tests/fixtures/v9.1)
  updater-from-v9.1.1
              tests/updater/test_update_from_v9_1_1.py: the same for installed v9.1.1
  package     tests/package: moved package, missing resources, dependency metadata,
              vendored scripts, frozen qualification scenarios
  structure   tools/validate_package.py on package/ with provenance

A zero exit code is never enough. A test step passes only if its exit code is 0, its
collection matches the declared count, nothing failed or errored, every skip is declared
for this platform and its results were produced for the expected inputs. summary.json
records candidate identity, input digests, commands, working directories, relevant
environment, log hashes, collections and skips. Results go to a new .local/ folder.
Fixture roots are short folders under RC_CHECK_FIXTURES_ROOT (default: the system temp
folder), outside the clone, so a deep clone path cannot exceed the legacy Windows
260-character limit; a preflight refuses a base that is still too long. Only empty fixture
roots are removed.
Nothing is installed in an active profile and no network access is used.
"""
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'state': 169, 'updater-v7': 30, 'updater-v8': 28, 'updater-from-v8': 7, 'updater-from-v9': 7, 'updater-from-v9.1': 7, 'updater-from-v9.1.1': 7, 'package': 25}
# Every step in run order; all_passed requires exactly these results, in this order.
STEPS = list(EXPECTED) + ['structure']
# Skips accepted only off Windows (NTFS junction tests); none is accepted on Windows.
NON_NT_SKIPS = {
    'updater-v7': {'test_reparse_point_refused', 'test_reparse_target_root_refused'},
    'updater-v8': {'test_dependency_junction_refused'},
    'updater-from-v8': set(),
    'updater-from-v9': set(),
    'updater-from-v9.1': set(),
    'updater-from-v9.1.1': set(),
    'package': set(),
    'state': set(),
}
# Deepest synthetic profile path observed below a fixture root, plus margin (characters).
FIXTURE_DEPTH_MARGIN = 175
ENV_KEYS = ('RC_STATE_PACKAGE', 'RC_UPDATE_LOT', 'RC_UPDATE_PREVIOUS', 'RC_UPDATE_CANDIDATE',
            'RC_UPDATE_MODULE', 'RC_UPDATE_FIXTURES', 'RC_PACKAGE_FIXTURES')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha(Path(path).read_bytes())


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def collect(start, top, out, pattern='test*.py'):
    """Subprocess mode: discover and run a unittest suite, write ids, counts and skips."""
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=start, pattern=pattern, top_level_dir=top)
    ids = []

    def walk(item):
        if isinstance(item, unittest.TestSuite):
            for sub in item:
                walk(sub)
        else:
            ids.append(item.id())
    walk(suite)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    doc = {'collected': ids, 'tests_run': result.testsRun,
           'failures': [t.id() for t, _ in result.failures], 'errors': [t.id() for t, _ in result.errors],
           'skipped': [{'id': t.id(), 'reason': r} for t, r in result.skipped],
           'expected_failures': [t.id() for t, _ in result.expectedFailures],
           'unexpected_successes': [t.id() for t in result.unexpectedSuccesses],
           'python': platform.python_version()}
    Path(out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() and not result.expectedFailures else 1


def inventory():
    """Candidate identity and byte integrity; returns (identity, problems)."""
    problems = []
    manifest_path = ROOT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    expected = {entry['path'] for entry in manifest['files']}
    actual = {p.relative_to(ROOT / 'package').as_posix()
              for p in (ROOT / 'package').rglob('*') if p.is_file()}
    if expected != actual:
        problems.append({'check': 'package_inventory', 'difference': sorted(expected ^ actual)})
    for entry in manifest['files']:
        path = ROOT / 'package' / entry['path']
        if path.is_file():
            raw = path.read_bytes()
            if sha(raw) != entry['sha256'] or len(raw) != entry['bytes']:
                problems.append({'check': 'package_bytes', 'path': entry['path']})
    provenance = json.loads((ROOT / 'provenance.json').read_text(encoding='utf-8'))
    listed = set()
    for item in provenance['files']:
        listed.add(item['path'])
        path = ROOT / item['path']
        if not path.is_file():
            problems.append({'check': 'provenance_missing', 'path': item['path']})
            continue
        got = sha_file(path)
        if got != item['sha256']:
            problems.append({'check': 'provenance_sha256', 'path': item['path']})
        if item.get('adaptation') == 'byte-identical' and got != item.get('source_sha256'):
            problems.append({'check': 'provenance_source', 'path': item['path']})
    unlisted = sorted('package/' + p for p in actual if 'package/' + p not in listed)
    if unlisted:
        problems.append({'check': 'provenance_inventory', 'unlisted': unlisted})
    identity = {'manifest_sha256': sha_file(manifest_path), 'manifest_format': manifest.get('format'),
                'distribution': manifest.get('distribution', 'rc-core'), 'manifest_digest': manifest.get('digest'),
                'package_files': len(actual), 'provenance_sha256': sha_file(ROOT / 'provenance.json')}
    return identity, problems


def input_files():
    """Files whose bytes define what is checked: tools, tests, package, manifests."""
    names = []
    for base in ('tools', 'tests', 'package'):
        for p in sorted((ROOT / base).rglob('*')):
            parts = p.relative_to(ROOT).parts
            if p.is_file() and '__pycache__' not in parts and '_fixtures' not in parts and p.suffix != '.pyc':
                names.append(p.relative_to(ROOT).as_posix())
    names += ['manifest.json', 'provenance.json']
    return [{'path': n, 'sha256': sha_file(ROOT / n)} for n in names]


def git_state():
    """Read-only, best effort; repository identity also rests on the input digests."""
    out = {}
    for key, command in (('head', ['git', 'rev-parse', 'HEAD']),
                         ('status', ['git', 'status', '--porcelain=v1', '--untracked-files=all'])):
        try:
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=False)
            out[key] = proc.stdout.strip() if proc.returncode == 0 else None
            if proc.returncode:
                out[key + '_error'] = (proc.stderr.strip().splitlines() or [''])[0]
        except OSError as exc:
            out[key] = None
            out[key + '_error'] = str(exc)
    return out


def judge(name, exit_code, results):
    """Pass only with exit 0, exact collection, no failure, declared skips, results present."""
    reasons = []
    if exit_code != 0:
        reasons.append(f'exit code {exit_code}')
    if results is None:
        return False, reasons + ['no results file']
    count = results.get('tests_run')
    if count != EXPECTED[name]:
        reasons.append(f'collection {count} != expected {EXPECTED[name]}')
    if 'collected' in results and len(results['collected']) != count:
        reasons.append('collected ids differ from tests run')
    if results.get('failures') or results.get('errors') or results.get('unexpected_successes'):
        reasons.append('failures or errors')
    if results.get('expected_failures'):
        reasons.append('expected failures remain unqualified')
    allowed = NON_NT_SKIPS[name] if os.name != 'nt' else set()
    skipped = [s['id'] if isinstance(s, dict) else s for s in results.get('skipped', [])]
    undeclared = [s for s in skipped if s.split('.')[-1] not in allowed]
    if undeclared:
        reasons.append(f'undeclared skips {undeclared}')
    return not reasons, reasons


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / '.local' / (stamp + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    (out / 'tmp').mkdir()
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    identity, problems = inventory()
    summary = {'started_at': started, 'candidate': identity, 'inventory_problems': problems,
               'git': git_state(), 'inputs': input_files(),
               'environment': {'python': platform.python_version(), 'executable': sys.executable,
                               'os': f'{platform.system()} {platform.release()} ({platform.version()})'},
               'expected_collections': EXPECTED, 'results': []}
    summary['inputs_digest'] = sha(canonical(summary['inputs']))
    print('inventory: ' + ('passed' if not problems else 'FAILED'), flush=True)
    if not problems:
        # Short fixture roots outside the clone keep NTFS paths below the legacy 260-character limit.
        base = Path(os.environ.get('RC_CHECK_FIXTURES_ROOT') or tempfile.gettempdir()) / ('rcchk-' + uuid.uuid4().hex[:6])
        if os.name == 'nt' and len(str(base)) + FIXTURE_DEPTH_MARGIN > 259:
            print(f'preflight: FAILED fixture root {base} is too long for 260-character paths; '
                  'set RC_CHECK_FIXTURES_ROOT to a short folder (for example C:\\rc)', flush=True)
            return 1
        base.mkdir(parents=True)
        roots = {k: base / k for k in ('f', 'g', 'h', 'i', 'j', 'k', 'p')}
        for r in roots.values():
            r.mkdir()
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8',
               'TMP': str(out / 'tmp'), 'TEMP': str(out / 'tmp'),
               'RC_STATE_PACKAGE': str(ROOT / 'package'),
               'RC_UPDATE_LOT': str(ROOT),
               'RC_UPDATE_PREVIOUS': str(ROOT / 'tests/fixtures/previous'),
               'RC_UPDATE_CANDIDATE': str(ROOT / 'tests/fixtures/v7'),
               'RC_UPDATE_MODULE': str(ROOT / 'tools/rc_update.py'),
               'RC_UPDATE_FIXTURES': str(roots['f'])}
        me = str(Path(__file__).resolve())
        steps = [
            ('state', [sys.executable, '-B', me, '--collect', '.', '.', str(out / 'state.json')],
             ROOT / 'tests/state', {}, out / 'state.json'),
            ('updater-v7', [sys.executable, '-B', str(ROOT / 'tests/updater/test_rc_update.py'),
                            '--results-out', str(out / 'updater-v7.json')], ROOT, {}, out / 'updater-v7.json'),
            ('updater-v8', [sys.executable, '-B', me, '--collect', str(ROOT / 'tests/updater'), str(ROOT / 'tests/updater'),
                            str(out / 'updater-v8.json'), 'test_rc_update_v8.py'],
             ROOT, {'RC_UPDATE_FIXTURES': str(roots['g'])}, out / 'updater-v8.json'),
            ('updater-from-v8', [sys.executable, '-B', me, '--collect', str(ROOT / 'tests/updater'),
                                 str(ROOT / 'tests/updater'), str(out / 'updater-from-v8.json'),
                                 'test_update_from_v8.py'],
             ROOT, {'RC_UPDATE_FIXTURES': str(roots['h'])}, out / 'updater-from-v8.json'),
            ('updater-from-v9', [sys.executable, '-B', me, '--collect', str(ROOT / 'tests/updater'),
                                 str(ROOT / 'tests/updater'), str(out / 'updater-from-v9.json'),
                                 'test_update_from_v9.py'],
             ROOT, {'RC_UPDATE_FIXTURES': str(roots['i'])}, out / 'updater-from-v9.json'),
            ('updater-from-v9.1', [sys.executable, '-B', me, '--collect', str(ROOT / 'tests/updater'),
                                   str(ROOT / 'tests/updater'), str(out / 'updater-from-v9.1.json'),
                                   'test_update_from_v9_1.py'],
             ROOT, {'RC_UPDATE_FIXTURES': str(roots['j'])}, out / 'updater-from-v9.1.json'),
            ('updater-from-v9.1.1', [sys.executable, '-B', me, '--collect', str(ROOT / 'tests/updater'),
                                     str(ROOT / 'tests/updater'), str(out / 'updater-from-v9.1.1.json'),
                                     'test_update_from_v9_1_1.py'],
             ROOT, {'RC_UPDATE_FIXTURES': str(roots['k'])}, out / 'updater-from-v9.1.1.json'),
            ('package', [sys.executable, '-B', me, '--collect', str(ROOT / 'tests/package'), str(ROOT / 'tests/package'),
                         str(out / 'package.json')],
             ROOT, {'RC_PACKAGE_FIXTURES': str(roots['p'])}, out / 'package.json'),
        ]
        for name, command, cwd, extra, results_path in steps:
            step_env = {**env, **extra}
            with (out / (name + '.txt')).open('w', encoding='utf-8') as log:
                proc = subprocess.run(command, cwd=cwd, env=step_env, stdout=log, stderr=subprocess.STDOUT, check=False)
            results = json.loads(results_path.read_text(encoding='utf-8')) if results_path.is_file() else None
            passed, reasons = judge(name, proc.returncode, results)
            if name == 'updater-v7' and results is not None:
                inputs = results.get('inputs', {})
                if inputs.get('module_sha256') != sha_file(ROOT / 'tools/rc_update.py') \
                        or inputs.get('new_manifest_sha256') != sha_file(ROOT / 'tests/fixtures/v7/manifest.json'):
                    passed, reasons = False, reasons + ['results produced for other inputs']
            summary['results'].append({
                'step': name, 'command': command, 'cwd': str(cwd), 'exit_code': proc.returncode,
                'environment': {k: step_env[k] for k in ENV_KEYS if k in step_env},
                'log': str(out / (name + '.txt')), 'log_sha256': sha_file(out / (name + '.txt')),
                'results_file': str(results_path) if results_path.is_file() else None,
                'tests_run': results.get('tests_run') if results else None,
                'expected': EXPECTED[name],
                'skipped': results.get('skipped') if results else None,
                'passed': passed, 'reasons': reasons})
            print(name + ': ' + ('passed' if passed else 'FAILED ' + '; '.join(reasons)), flush=True)
        command = [sys.executable, '-B', str(ROOT / 'tools/validate_package.py'), str(ROOT / 'package'),
                   '--output', str(out / 'structure.json'), '--provenance', str(ROOT / 'provenance.json')]
        with (out / 'structure.txt').open('w', encoding='utf-8') as log:
            proc = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        structure = json.loads((out / 'structure.json').read_text(encoding='utf-8')) \
            if (out / 'structure.json').is_file() else None
        reasons = []
        if proc.returncode:
            reasons.append(f'exit code {proc.returncode}')
        if structure is None or structure['failed'] or not structure['passed']:
            reasons.append('structural checks failed or absent')
        elif {f['path'] for f in structure['files']} != {e['path'] for e in json.loads(
                (ROOT / 'manifest.json').read_text(encoding='utf-8'))['files']}:
            reasons.append('validated files differ from manifest')
        elif structure['distribution'] != identity['distribution']:
            reasons.append('validated distribution differs from manifest')
        summary['results'].append({
            'step': 'structure', 'command': command, 'cwd': str(ROOT), 'exit_code': proc.returncode,
            'log': str(out / 'structure.txt'), 'log_sha256': sha_file(out / 'structure.txt'),
            'checks_passed': structure['passed'] if structure else None,
            'checks_failed': structure['failed'] if structure else None,
            'passed': not reasons, 'reasons': reasons})
        print('structure: ' + ('passed' if not reasons else 'FAILED ' + '; '.join(reasons)), flush=True)
        summary['fixtures_left'] = {}
        for key, r in roots.items():
            left = sorted(p.name for p in r.iterdir())
            summary['fixtures_left'][str(r)] = left
            if not left:
                r.rmdir()
        if not any(base.iterdir()):
            base.rmdir()
    summary['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    summary['all_passed'] = not problems and [r['step'] for r in summary['results']] == STEPS \
        and all(r['passed'] for r in summary['results']) \
        and not any(summary.get('fixtures_left', {}).values())
    summary['limits'] = ['Offline synthetic checks on this candidate only; no installation, runtime, '
                         'agent behaviour or model quality is qualified.']
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Results: ' + str(out), flush=True)
    return 0 if summary['all_passed'] else 1


if __name__ == '__main__':
    if len(sys.argv) >= 5 and sys.argv[1] == '--collect':
        # Optional sixth argument: one module pattern when several suites share a folder.
        sys.exit(collect(*sys.argv[2:6]))
    sys.exit(main())
