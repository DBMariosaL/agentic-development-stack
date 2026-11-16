"""Deterministic footprint of a candidate: what base..candidate adds and removes (stdlib only).

Classifies each touched file as tests, docs or product, counts added and removed lines,
lists new files and added comment lines, and emits signals that point where to look.
Signals are neither acceptance nor refusal and never change the exit code: 0 when the
measure succeeded, 2 on usage error, unknown repository or reference, or unusable --previous.
Read-only: no network, no write.
"""
import argparse
import codecs
import fnmatch
import json
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True

CLASSES = ('product', 'tests', 'docs')
TEST_DIRS = {'test', 'tests', '__tests__', 'spec', 'specs'}
TEST_NAMES = ('test_*.py', '*_test.*', '*.test.*', '*.spec.*', 'conftest.py')
DOC_SUFFIXES = {'.md', '.mdx', '.rst', '.adoc'}
COMMENT_PREFIXES = {}
for _exts, _prefixes in (
        (('py', 'pyi', 'sh', 'bash', 'zsh', 'ps1', 'rb', 'pl', 'r', 'yaml', 'yml', 'toml', 'cfg', 'conf'), ('#',)),
        (('js', 'jsx', 'mjs', 'cjs', 'ts', 'tsx', 'c', 'h', 'cc', 'cpp', 'hpp', 'java', 'go', 'rs', 'cs',
          'swift', 'kt', 'kts'), ('//', '/*')),
        (('sql', 'lua'), ('--',)),
        (('html', 'htm', 'vue', 'svelte'), ('<!--',))):
    for _ext in _exts:
        COMMENT_PREFIXES['.' + _ext] = _prefixes
DIRECTIVE = re.compile(r'(?i)^(?:!|type:|noqa|pragma|pylint:|mypy:|flake8|ruff:|isort:|fmt:|yapf:|-\*-|'
                       r'eslint|prettier-ignore|@ts-|tslint:|jshint|global |istanbul |c8 |nolint|go:|\+build|'
                       r'rubocop:|shellcheck |spdx-license-identifier|copyright\b|\(c\)|licensed under)')
MAX_COMMENT_LINES = 50
HUNK = re.compile(r'^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
LIMITS = ['Comment detection is a per-extension line-prefix heuristic: docstrings, trailing comments, '
          'block comment bodies and unlisted extensions are not counted.',
          'Classification uses path and file name patterns only, never file content.',
          'Renames use git default similarity: a heavily edited move counts as removal plus addition.',
          'Binary files are counted in files, without lines.',
          'Measures size only; signals say where to look, not whether the candidate is acceptable.']


class UsageError(Exception):
    pass


Repo = namedtuple('Repo', 'path config')


def git(repo, *args):
    cmd = ['git', '--no-optional-locks', '-C', repo.path, *repo.config, '-c', 'core.quotepath=off', *args]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode:
        raise UsageError(proc.stderr.decode('utf-8', 'replace').strip() or f'git {args[0]} failed')
    return proc.stdout.decode('utf-8', 'replace')


def diff(repo, base, candidate, *options):
    # Pinned options: user config (algorithm, prefixes, external tools) must not change the measure.
    return git(repo, 'diff', '--no-color', '--no-ext-diff', '--no-textconv', '--diff-algorithm=myers',
               '-M', *options, base, candidate, '--')


def resolve(repo, ref, flag):
    if ref.startswith('-'):
        raise UsageError(f'{flag}: invalid reference {ref!r}')
    try:
        return git(repo, 'rev-parse', '--verify', '--quiet', ref + '^{commit}').strip()
    except UsageError:
        raise UsageError(f'{flag}: unknown revision {ref!r} in {repo.path}') from None


def classify(path):
    pure = PurePosixPath(path)
    if pure.suffix.lower() in DOC_SUFFIXES:
        return 'docs'
    if TEST_DIRS & set(pure.parts[:-1]) or any(fnmatch.fnmatchcase(pure.name, p) for p in TEST_NAMES):
        return 'tests'
    return 'product'


def numstat(repo, base, candidate):
    tokens = diff(repo, base, candidate, '--numstat', '-z').split('\0')
    rows, index = [], 0
    while index < len(tokens) and tokens[index]:
        added, removed, path = tokens[index].split('\t', 2)
        index += 1
        if not path:
            path = tokens[index + 1]
            index += 2
        rows.append((path, None if added == '-' else int(added), None if removed == '-' else int(removed)))
    return rows


def measure_classes(rows, new_files):
    classes = {name: {'added': 0, 'removed': 0, 'files': 0, 'new_files': []} for name in CLASSES}
    for path, added, removed in rows:
        entry = classes[classify(path)]
        entry['files'] += 1
        entry['added'] += added or 0
        entry['removed'] += removed or 0
        if path in new_files:
            entry['new_files'].append(path)
    for entry in classes.values():
        entry['new_files'].sort()
    return classes


def unquote(path):
    if path.startswith('"'):
        return codecs.escape_decode(path[1:-1].encode('utf-8'))[0].decode('utf-8', 'replace')
    return path


def added_lines(patch):
    path, line, old_left, new_left = None, 0, 0, 0
    for raw in patch.split('\n'):
        if old_left or new_left:
            if raw.startswith('+'):
                yield path, line, raw[1:]
                line, new_left = line + 1, new_left - 1
            elif raw.startswith('-'):
                old_left -= 1
            elif raw.startswith(' '):
                line, old_left, new_left = line + 1, old_left - 1, new_left - 1
            continue
        if raw.startswith('+++ '):
            # git ends the header with a tab when the path contains a space
            target = unquote(raw[4:].removesuffix('\t'))
            path = target[2:] if target.startswith('b/') else None
        elif match := HUNK.match(raw):
            old_left = int(match.group(1) or 1)
            line, new_left = int(match.group(2)), int(match.group(3) or 1)


def is_comment(path, text):
    stripped = text.strip()
    for prefix in COMMENT_PREFIXES.get(PurePosixPath(path).suffix.lower(), ()):
        if stripped.startswith(prefix):
            body = stripped[len(prefix):].strip()
            return not (stripped.startswith('#!') or DIRECTIVE.match(body))
    return False


def comments(repo, base, candidate):
    patch = diff(repo, base, candidate, '-U0', '--inter-hunk-context=0', '--src-prefix=a/', '--dst-prefix=b/')
    found = [{'path': path, 'line': line, 'text': text.strip()[:200]}
             for path, line, text in added_lines(patch)
             if path and classify(path) != 'docs' and is_comment(path, text)]
    return {'count': len(found), 'lines': found[:MAX_COMMENT_LINES]}


def load_previous(path, base):
    try:
        with open(path, encoding='utf-8') as stream:
            previous = json.load(stream)
        added = {name: previous['classes'][name]['added'] for name in CLASSES}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UsageError(f'--previous: unreadable footprint {path}: {exc}') from None
    if not all(type(count) is int and count >= 0 for count in added.values()):
        raise UsageError(f'--previous: added counts must be non-negative integers in {path}')
    if previous.get('base') != base:
        raise UsageError(f'--previous: measured on base {previous.get("base")}, not {base}')
    return added


def signals(rows, classes, comment_info, args, previous):
    found = []
    tests, product, docs = (classes[name]['added'] for name in ('tests', 'product', 'docs'))
    if tests > args.test_ratio * product + args.test_slack:
        found.append({'id': 'tests_outweigh_product',
                      'detail': f'tests +{tests} > {args.test_ratio:g} x product +{product} + {args.test_slack}: '
                                'have the added tests classified with references/test-review-brief.md'})
    if docs:
        grown = {path for path, added, _ in rows if added and classify(path) == 'docs'}
        new = [path for path in classes['docs']['new_files'] if path in grown]
        names = new + sorted(grown - set(new))
        found.append({'id': 'docs_added', 'detail': f'docs +{docs} in ' + ', '.join(names)})
    if comment_info['count']:
        found.append({'id': 'comments_added', 'detail': f'{comment_info["count"]} added comment lines'})
    if previous is not None:
        current = {name: classes[name]['added'] for name in CLASSES}
        if sum(current.values()) > sum(previous.values()):
            delta = ', '.join(f'{name} {current[name] - previous[name]:+d}' for name in CLASSES)
            found.append({'id': 'grew_since_previous', 'detail': f'added lines since previous: {delta}'})
    return found


def footprint(args):
    config = ['-c', 'safe.directory=' + Path(args.repo).resolve().as_posix()] if args.safe_directory else []
    repo = Repo(args.repo, config)
    try:
        git(repo, 'rev-parse', '--git-dir')
    except UsageError as exc:
        raise UsageError(f'REPO: {repo.path}: {exc}') from None
    base = resolve(repo, args.base, '--base')
    candidate = resolve(repo, args.candidate, '--candidate')
    previous = load_previous(args.previous, base) if args.previous else None
    rows = numstat(repo, base, candidate)
    new_files = set(diff(repo, base, candidate, '--diff-filter=A', '--name-only', '-z').split('\0')) - {''}
    classes = measure_classes(rows, new_files)
    comment_info = comments(repo, base, candidate)
    return {'ok': True, 'base': base, 'candidate': candidate, 'classes': classes,
            'comments_added': comment_info, 'signals': signals(rows, classes, comment_info, args, previous),
            'limits': LIMITS}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('repo', metavar='REPO', help='path of the git repository')
    parser.add_argument('--base', required=True, help='reference the candidate is measured against')
    parser.add_argument('--candidate', default='HEAD', help='measured reference (default: HEAD)')
    parser.add_argument('--previous', metavar='FILE.json', help='earlier output of this tool on the same base')
    parser.add_argument('--test-ratio', type=float, default=3.0, help='tests_outweigh_product ratio (default: 3)')
    parser.add_argument('--test-slack', type=int, default=100, help='tests_outweigh_product slack (default: 100)')
    parser.add_argument('--safe-directory', action='store_true',
                        help='pass -c safe.directory=REPO to every git call, for a repository owned by another '
                             'account; REPO must be its top-level folder; git configuration files are not changed')

    def error(message):
        raise UsageError(message)
    parser.error = error
    return parser


def main(argv=None):
    try:
        result = footprint(build_parser().parse_args(argv))
    except (UsageError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
