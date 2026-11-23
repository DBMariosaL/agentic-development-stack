"""Run the offline repository checks on a verified copy of the candidate's declared inputs.

Steps:
  inventory   every path listed in provenance.json is relative and normalized, without
              '..', root, drive, backslash, or trailing dot or space, its destination stays
              in the copy, and no two entries name the same destination ignoring case; then
              every file is read once and those bytes are checked against provenance.json
              and manifest.json and written to a fresh copy under the fixture root, with
              manifest.json and provenance.json; manifest.json against package/, every
              package file listed in provenance.json, pilot mandatory reading against
              READING_BUDGET; a file that cannot be read is a named problem
  state       tests/state, unchanged v7 state regressions
  updater-v7  tests/updater/test_rc_update.py, unchanged, against the frozen v7 fixture
              (31 October -> v7, three RC skills)
  updater-v8  tests/updater/test_rc_update_v8.py: three -> seven skills and dependencies
  updater-from-<version>
              tests/updater/test_update_from_previous.py, one step per origin version
              (v8, v9, v9.1, v9.1.1, v9.1.2) selected by RC_UPDATE_FROM: an installed
              version (compact frozen reference tests/fixtures/<version>) updated to
              package/: RC files replaced, dependencies untouched, claude-fable-prompt-optimizer
              installed
  package     tests/package: moved package, missing resources, dependency metadata,
              vendored scripts, frozen qualification scenarios
  footprint   tests/footprint: rc_footprint.py on temporary git repositories
  structure   tools/validate_package.py on the copy's package/ with provenance

A zero exit code is never enough. A test step passes only if its exit code is 0, its
results file is readable, its collection matches the declared count, nothing failed or
errored, every skip is declared for this platform and, for updater-v7, its results name
the module and fixture manifest of the copy. After the steps, the copy is checked again
against the input digests: a file that a step changed is an inventory problem
(copy_changed) and the run fails. summary.json records candidate identity, the copy that
ran, input digests, commands, working directories, relevant environment, log hashes,
collections and skips; it is written, and the copy removed, however the run ends. Results
go to a new .local/ folder of the clone.

What the copy confines: the steps start in the copy, where a file outside provenance.json
does not exist, so a test that reads a path relative to the copy reads listed bytes only.
What it does not: the test code is itself listed, hence reviewed, but nothing stops it from
reading elsewhere through an absolute path, an inherited variable or a path computed toward
the clone; check.py does not confine what the tests do.

Fixture roots and the copy are short folders under RC_CHECK_FIXTURES_ROOT (default: the
system temp folder; give an absolute folder outside the clone). On Windows a preflight
measures the resolved base, refuses one too long for the declared depth margin under the
legacy 260-character limit, records the refusal in summary.json and runs no step. The copy
is removed; fixture roots are removed only when empty. git state is recorded when
available; no git repository is needed.

Every step runs under python -I -S -B: it ignores PYTHON* variables, puts neither the script
folder nor site-packages (.pth files, sitecustomize) on sys.path and writes no bytecode; the
collector refuses to run outside isolated mode. Steps get no inherited PYTHON* variable, so
a process that a test starts does not see an inherited PYTHONPATH, but it does not inherit
-S. The interpreter installation, standard library and site-packages, is trusted:
summary.json records which executable ran. check.py installs nothing and opens no network
connection itself.
"""
import datetime
import hashlib
import json
import os
import platform
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'state': 236,'updater-v7': 30, 'updater-v8': 39, 'updater-from-v8': 9, 'updater-from-v9': 9, 'updater-from-v9.1': 9, 'updater-from-v9.1.1': 9, 'updater-from-v9.1.2': 9, 'package': 36, 'footprint': 19}
READING = ('SKILL.md', 'references/program-contract.md', 'references/operating-loop.md')
READING_BUDGET = 3733
# Every step in run order; all_passed requires exactly these results, in this order.
STEPS = list(EXPECTED) + ['structure']
# Skips accepted only off Windows (NTFS junction tests), as Class.method; none is accepted on Windows.
NON_NT_SKIPS = {
    'updater-v7': {'GuardTests.test_reparse_point_refused', 'GuardTests.test_reparse_target_root_refused'},
    'updater-v8': {'PlanV8Tests.test_dependency_junction_refused'},
    'updater-from-v8': set(),
    'updater-from-v9': set(),
    'updater-from-v9.1': set(),
    'updater-from-v9.1.1': set(),
    'updater-from-v9.1.2': set(),
    'package': {'CheckPreflightTests.test_preflight_refusal_writes_summary'},
    'footprint': set(),
    'state': set(),
}
# Deepest synthetic profile path observed below a fixture root, plus margin (characters).
FIXTURE_DEPTH_MARGIN = 175
ENV_KEYS = ('RC_STATE_PACKAGE', 'RC_UPDATE_LOT', 'RC_UPDATE_PREVIOUS', 'RC_UPDATE_CANDIDATE',
            'RC_UPDATE_MODULE', 'RC_UPDATE_FIXTURES', 'RC_UPDATE_FROM', 'RC_PACKAGE_FIXTURES', 'PYTHONPATH')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha(Path(path).read_bytes())


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def collect(start, top, out, pattern='test*.py'):
    """Subprocess mode: discover and run a unittest suite, write ids, counts and skips."""
    if not sys.flags.isolated:
        Path(out).write_text(json.dumps({'error': 'collect runs only under python -I', 'tests_run': 0,
                                         'collected': []}) + '\n', encoding='utf-8')
        return 2
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
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


def inventory(copy=None):
    """Candidate identity, input digests and byte integrity; returns (identity, problems).

    Every file is read once. With copy, the bytes read for each file listed in
    provenance.json, and for the two manifests, are written below it."""
    problems, cache = [], {}

    def read(rel):
        if rel not in cache:
            try:
                cache[rel] = (ROOT / rel).read_bytes()
            except OSError as exc:
                cache[rel] = None
                problems.append({'check': 'unreadable', 'path': rel, 'reason': str(exc)})
        return cache[rel]

    docs = {}
    for name in ('manifest.json', 'provenance.json'):
        raw = read(name)
        try:
            docs[name] = None if raw is None else json.loads(raw.decode('utf-8'))
        except ValueError as exc:
            problems.append({'check': 'unreadable', 'path': name, 'reason': str(exc)})
    if problems:
        return {}, problems
    manifest, provenance = docs['manifest.json'], docs['provenance.json']
    seen = {'provenance.json'}
    for item in provenance['files']:
        rel = item.get('path')
        if not isinstance(rel, str) or posixpath.normpath(rel) != rel or rel.startswith(('/', '../')) \
                or re.search(r'[\\:]|[. ]$|[. ]/', rel) \
                or (copy is not None and not (copy / rel).resolve().is_relative_to(copy.resolve())):
            problems.append({'check': 'provenance_path', 'path': rel})
        elif rel.lower() in seen:
            problems.append({'check': 'provenance_duplicate', 'path': rel})
        else:
            seen.add(rel.lower())
    if problems:
        return {}, problems
    listed, inputs = set(), []
    for item in provenance['files']:
        listed.add(item['path'])
        if not (ROOT / item['path']).is_file():
            problems.append({'check': 'provenance_missing', 'path': item['path']})
            continue
        raw = read(item['path'])
        if raw is None:
            continue
        got = sha(raw)
        if got != item['sha256']:
            problems.append({'check': 'provenance_sha256', 'path': item['path']})
        if item.get('adaptation') == 'byte-identical' and got != item.get('source_sha256'):
            problems.append({'check': 'provenance_source', 'path': item['path']})
        inputs.append({'path': item['path'], 'sha256': got})
        if copy is not None:
            (copy / item['path']).parent.mkdir(parents=True, exist_ok=True)
            (copy / item['path']).write_bytes(raw)
    for name in ('manifest.json', 'provenance.json'):
        if name not in listed:
            inputs.append({'path': name, 'sha256': sha(cache[name])})
        if copy is not None:
            (copy / name).write_bytes(cache[name])
    expected = {entry['path'] for entry in manifest['files']}
    actual = {p.relative_to(ROOT / 'package').as_posix()
              for p in (ROOT / 'package').rglob('*') if p.is_file()}
    if expected != actual:
        problems.append({'check': 'package_inventory', 'difference': sorted(expected ^ actual)})
    for entry in manifest['files']:
        if (ROOT / 'package' / entry['path']).is_file():
            raw = read('package/' + entry['path'])
            if raw is not None and (sha(raw) != entry['sha256'] or len(raw) != entry['bytes']):
                problems.append({'check': 'package_bytes', 'path': entry['path']})
    unlisted = sorted(f'package/{name}' for name in actual if f'package/{name}' not in listed)
    if unlisted:
        problems.append({'check': 'provenance_inventory', 'unlisted': unlisted})
    reading = 0
    for name in READING:
        rel = 'package/rc-coordinate-development/' + name
        if (ROOT / rel).is_file():
            reading += len((read(rel) or b'').decode('utf-8', errors='replace').split())
        else:
            problems.append({'check': 'pilot_reading_missing', 'path': name})
    if reading > READING_BUDGET:
        problems.append({'check': 'pilot_reading', 'words': reading, 'budget': READING_BUDGET})
    identity = {'pilot_reading_words': reading, 'manifest_sha256': sha(cache['manifest.json']),
                'manifest_format': manifest.get('format'),
                'distribution': manifest.get('distribution', 'rc-core'), 'manifest_digest': manifest.get('digest'),
                'package_files': len(actual), 'provenance_sha256': sha(cache['provenance.json']),
                'inputs': inputs}
    return identity, problems


def changed(root, inputs):
    """Paths of the inputs whose bytes below root no longer match their digest."""
    paths = []
    for entry in inputs:
        try:
            same = sha_file(root / entry['path']) == entry['sha256']
        except OSError:
            same = False
        if not same:
            paths.append(entry['path'])
    return paths


def read_results(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


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


def judge(name, exit_code, results, root=ROOT):
    """Pass only with exit 0, readable results, exact collection, no failure, declared skips
    and, for updater-v7, results produced for the module and fixture manifest below root."""
    reasons = []
    if exit_code != 0:
        reasons.append(f'exit code {exit_code}')
    if results is None:
        return False, reasons + ['no readable results file']
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
    undeclared = [s for s in skipped if '.'.join(s.split('.')[-2:]) not in allowed]
    if undeclared:
        reasons.append(f'undeclared skips {undeclared}')
    if name == 'updater-v7':
        inputs = results.get('inputs', {})
        if inputs.get('module_sha256') != sha_file(root / 'tools/rc_update.py') \
                or inputs.get('new_manifest_sha256') != sha_file(root / 'tests/fixtures/v7/manifest.json'):
            reasons.append('results produced for other inputs')
    return not reasons, reasons


def run_steps(copy, out, base, summary):
    """Run every step in the copy, judge it, record it; returns the fixture roots used."""
    from_steps = [n for n in EXPECTED if n.startswith('updater-from-')]
    roots = {k: base / k for k in ('f', 'g', 'p')}
    roots.update({n: base / f'h{i}' for i, n in enumerate(from_steps)})
    for r in roots.values():
        r.mkdir()
    py = [sys.executable, '-I', '-S', '-B']
    env = {**{k: v for k, v in os.environ.items() if not k.upper().startswith('PYTHON')},
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8',
           'TMP': str(out / 'tmp'), 'TEMP': str(out / 'tmp'),
           'RC_STATE_PACKAGE': str(copy / 'package'),
           'RC_UPDATE_LOT': str(copy),
           'RC_UPDATE_PREVIOUS': str(copy / 'tests/fixtures/previous'),
           'RC_UPDATE_CANDIDATE': str(copy / 'tests/fixtures/v7'),
           'RC_UPDATE_MODULE': str(copy / 'tools/rc_update.py'),
           'RC_UPDATE_FIXTURES': str(roots['f'])}
    me = str(copy / 'tools/check.py')
    steps = [
        ('state', [*py, me, '--collect', '.', '.', str(out / 'state.json')],
         copy / 'tests/state', {}, out / 'state.json'),
        ('updater-v7', [*py, str(copy / 'tests/updater/test_rc_update.py'),
                        '--results-out', str(out / 'updater-v7.json')], copy, {}, out / 'updater-v7.json'),
        ('updater-v8', [*py, me, '--collect', str(copy / 'tests/updater'), str(copy / 'tests/updater'),
                        str(out / 'updater-v8.json'), 'test_rc_update_v8.py'],
         copy, {'RC_UPDATE_FIXTURES': str(roots['g'])}, out / 'updater-v8.json'),
    ] + [
        (n, [*py, me, '--collect', str(copy / 'tests/updater'), str(copy / 'tests/updater'),
             str(out / (n + '.json')), 'test_update_from_previous.py'],
         copy, {'RC_UPDATE_FIXTURES': str(roots[n]), 'RC_UPDATE_FROM': n[len('updater-from-'):]},
         out / (n + '.json'))
        for n in from_steps
    ] + [
        ('package', [*py, me, '--collect', str(copy / 'tests/package'), str(copy / 'tests/package'),
                     str(out / 'package.json')],
         copy, {'RC_PACKAGE_FIXTURES': str(roots['p'])}, out / 'package.json'),
        ('footprint', [*py, me, '--collect', str(copy / 'tests/footprint'),
                       str(copy / 'tests/footprint'), str(out / 'footprint.json')],
         copy, {}, out / 'footprint.json'),
    ]
    for name, command, cwd, extra, results_path in steps:
        step_env = {**env, **extra}
        cwd.mkdir(parents=True, exist_ok=True)
        with (out / (name + '.txt')).open('w', encoding='utf-8') as log:
            proc = subprocess.run(command, cwd=cwd, env=step_env, stdout=log, stderr=subprocess.STDOUT, check=False)
        results = read_results(results_path)
        passed, reasons = judge(name, proc.returncode, results, copy)
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
    command = [*py, str(copy / 'tools/validate_package.py'), str(copy / 'package'),
               '--output', str(out / 'structure.json'), '--provenance', str(copy / 'provenance.json')]
    with (out / 'structure.txt').open('w', encoding='utf-8') as log:
        proc = subprocess.run(command, cwd=copy, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    structure = read_results(out / 'structure.json')
    reasons = []
    if proc.returncode:
        reasons.append(f'exit code {proc.returncode}')
    if structure is None or structure['failed'] or not structure['passed']:
        reasons.append('structural checks failed or absent')
    elif {f['path'] for f in structure['files']} != {e['path'] for e in json.loads(
            (copy / 'manifest.json').read_text(encoding='utf-8'))['files']}:
        reasons.append('validated files differ from manifest')
    elif structure['distribution'] != summary['candidate']['distribution']:
        reasons.append('validated distribution differs from manifest')
    summary['results'].append({
        'step': 'structure', 'command': command, 'cwd': str(copy), 'exit_code': proc.returncode,
        'log': str(out / 'structure.txt'), 'log_sha256': sha_file(out / 'structure.txt'),
        'checks_passed': structure['passed'] if structure else None,
        'checks_failed': structure['failed'] if structure else None,
        'passed': not reasons, 'reasons': reasons})
    print('structure: ' + ('passed' if not reasons else 'FAILED ' + '; '.join(reasons)), flush=True)
    return roots


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / '.local' / (stamp + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    (out / 'tmp').mkdir()
    summary = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'git': git_state(),
               'environment': {'python': platform.python_version(), 'executable': sys.executable,
                               'os': f'{platform.system()} {platform.release()} ({platform.version()})'},
               'expected_collections': EXPECTED, 'copy': None, 'results': []}
    # Short fixture roots outside the clone keep NTFS paths below the legacy 260-character limit.
    base = Path(os.environ.get('RC_CHECK_FIXTURES_ROOT') or tempfile.gettempdir()).resolve()
    base = base / ('rcchk-' + uuid.uuid4().hex[:6])
    preflight = os.name == 'nt' and len(str(base)) + FIXTURE_DEPTH_MARGIN > 259
    copy = None if preflight else base / 's'
    try:
        if copy is not None:
            copy.mkdir(parents=True)
        identity, problems = inventory(copy)
        inputs = identity.pop('inputs', [])
        summary.update(candidate=identity, inventory_problems=problems, copy=copy and str(copy), inputs=inputs,
                       inputs_digest=sha(canonical(inputs)))
        print('inventory: ' + ('passed' if not problems else 'FAILED'), flush=True)
        if preflight:
            summary['preflight_problem'] = {'check': 'fixture_root_length', 'root': str(base), 'not_run': STEPS}
            print(f'preflight: FAILED fixture root {base} is too long for 260-character paths; '
                  'set RC_CHECK_FIXTURES_ROOT to a shorter absolute folder', flush=True)
        elif not problems:
            roots = run_steps(copy, out, base, summary)
            drift = changed(copy, inputs)
            if drift:
                problems.append({'check': 'copy_changed', 'paths': drift})
                print('copy: FAILED changed by a step: ' + ', '.join(drift), flush=True)
            summary['fixtures_left'] = {}
            for r in roots.values():
                left = sorted(p.name for p in r.iterdir())
                summary['fixtures_left'][str(r)] = left
                if not left:
                    r.rmdir()
    except BaseException as exc:
        summary['error'] = repr(exc)
        raise
    finally:
        if copy is not None:
            shutil.rmtree(copy, ignore_errors=True)
            if base.is_dir() and not any(base.iterdir()):
                base.rmdir()
        summary['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        summary['all_passed'] = summary.get('inventory_problems') == [] and not preflight \
            and 'error' not in summary and [r['step'] for r in summary['results']] == STEPS \
            and all(r['passed'] for r in summary['results']) and not any(summary.get('fixtures_left', {}).values())
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
