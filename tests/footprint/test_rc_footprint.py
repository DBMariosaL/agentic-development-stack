"""Tests de rc_footprint.py sur des dépôts git temporaires.

Lancer depuis la racine du dépôt : python -B -m unittest discover -s tests/footprint -t tests/footprint
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'package' / 'rc-coordinate-development' / 'scripts' / 'rc_footprint.py'


class Footprint(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name) / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=t', '-c', 'user.email=t@t',
                               '-c', 'core.autocrlf=false', *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, files, remove=()):
        for name in remove:
            self.git('rm', '-q', name)
        for name, content in files.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding='utf-8', newline='\n')
        self.git('add', '-A')
        self.git('commit', '-q', '--allow-empty', '-m', 'c')
        return self.git('rev-parse', 'HEAD')

    def run_tool(self, *args, code=0):
        proc = subprocess.run([sys.executable, '-B', str(SCRIPT), str(self.repo), *args],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def ids(self, result):
        return [s['id'] for s in result['signals']]

    def test_classification_counts_and_new_files(self):
        base = self.commit({'src/old.py': 'a\nb\nc\n'})
        self.commit({'src/old.py': 'a\n', 'src/données.py': 'x = 1\n', 'img.bin': b'\x00\x01\x02',
                     'tests/helpers.py': 'h = 1\n', 'pkg/test_a.py': 't = 1\n', 'lib/b_test.go': 'p\n',
                     'web/c.spec.ts': 's\n', 'web/__tests__/d.js': 'd\n', 'conftest.py': 'c\n',
                     'docs/guide.md': 'g\n', 'tests/notes.md': 'n\n'})
        classes = self.run_tool('--base', base)['classes']
        self.assertEqual(classes['product'], {'added': 1, 'removed': 2, 'files': 3,
                                              'new_files': ['img.bin', 'src/données.py']})
        self.assertEqual(classes['tests']['added'], 6)
        self.assertEqual(classes['tests']['new_files'], ['conftest.py', 'lib/b_test.go', 'pkg/test_a.py',
                                                         'tests/helpers.py', 'web/__tests__/d.js', 'web/c.spec.ts'])
        self.assertEqual(classes['docs']['new_files'], ['docs/guide.md', 'tests/notes.md'])

    def test_rename_is_not_an_addition(self):
        base = self.commit({'src/mod.py': ''.join(f'v{i} = {i}\n' for i in range(20))})
        self.git('mv', 'src/mod.py', 'src/moved.py')
        self.commit({})
        result = self.run_tool('--base', base)
        self.assertEqual(result['classes']['product'], {'added': 0, 'removed': 0, 'files': 1, 'new_files': []})
        self.assertEqual(self.ids(result), [])

    def test_tests_outweigh_product_at_exact_threshold(self):
        base = self.commit({'a.py': 'x = 1\n'})
        at = self.commit({'a.py': 'x = 1\ny = 2\n', 'tests/t.py': 'a\nb\nc\nd\ne\n'})
        over = self.commit({'tests/t.py': 'a\nb\nc\nd\ne\nf\n'})
        options = ('--base', base, '--test-ratio', '2', '--test-slack', '3')
        self.assertEqual(self.ids(self.run_tool(*options, '--candidate', at)), [])
        self.assertEqual(self.ids(self.run_tool(*options, '--candidate', over)), ['tests_outweigh_product'])

    def test_docs_added_names_new_files_first(self):
        base = self.commit({'z.md': 'old\n', 'a.py': 'x = 1\n'})
        self.commit({'z.md': 'old\nmore\n', 'b.md': 'new\n'})
        signal = self.run_tool('--base', base)['signals']
        self.assertEqual(signal, [{'id': 'docs_added', 'detail': 'docs +2 in b.md, z.md'}])

    def test_comments_skip_directives_license_and_docs(self):
        base = self.commit({'keep.txt': 'k\n'})
        self.commit({'tool.py': '#!/usr/bin/env python\n# Copyright 2026 Someone\nimport os  # noqa: F401\n'
                                '# type: ignore\n# pylint: disable=x\n# why this matters\nx = 1  # trailing\n',
                     'web/app.ts': '// eslint-disable-next-line\n/* real block */\nconst a = 1;\n',
                     'README.md': '<!-- hidden -->\n# Title\n'})
        info = self.run_tool('--base', base)['comments_added']
        self.assertEqual(info, {'count': 2, 'lines': [{'path': 'tool.py', 'line': 6, 'text': '# why this matters'},
                                                      {'path': 'web/app.ts', 'line': 2, 'text': '/* real block */'}]})

    def test_grew_since_previous(self):
        base = self.commit({'a.py': 'x = 1\n'})
        first = self.commit({'a.py': 'x = 1\ny = 2\n'})
        previous = self.repo.parent / 'previous.json'
        previous.write_text(json.dumps(self.run_tool('--base', base, '--candidate', first)), encoding='utf-8')
        self.commit({'a.py': 'x = 1\ny = 2\nz = 3\n'})
        self.assertEqual(self.ids(self.run_tool('--base', base, '--candidate', first, '--previous', str(previous))), [])
        signal = self.run_tool('--base', base, '--previous', str(previous))['signals']
        self.assertEqual(signal, [{'id': 'grew_since_previous',
                                   'detail': 'added lines since previous: product +1, tests +0, docs +0'}])
        refused = self.run_tool('--base', first, '--previous', str(previous), code=2)
        self.assertFalse(refused['ok'])
        self.assertIn('--previous', refused['error'])

    def test_unknown_reference_is_refused(self):
        self.commit({'a.py': 'x\n'})
        refused = self.run_tool('--base', 'no-such-ref', code=2)
        self.assertEqual(refused['ok'], False)
        self.assertIn('--base', refused['error'])


if __name__ == '__main__':
    unittest.main()
