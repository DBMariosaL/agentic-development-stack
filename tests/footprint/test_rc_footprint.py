"""Tests de rc_footprint.py sur des dépôts git temporaires.

Lancer depuis la racine du dépôt : python -B -m unittest discover -s tests/footprint -t tests/footprint
"""
import json
import os
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

    def run_tool(self, *args, code=0, env=None, repo=None):
        where = [] if repo is False else [str(repo or self.repo)]
        proc = subprocess.run([sys.executable, '-B', str(SCRIPT), *where, *args],
                              capture_output=True, text=True, encoding='utf-8', env=env)
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
        self.assertEqual(classes['product'], {'added': 2, 'removed': 2, 'files': 3,
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

    def test_docs_added_only_on_net_addition(self):
        base = self.commit({'a.md': 'a\nb\nc\n', 'old.md': ''.join(f'{i}\n' for i in range(6)), 'k.py': 'k\n'})
        edited = self.commit({'a.md': 'a\nB\nc\n'})
        shrunk = self.commit({'a.md': 'a\nB\nc\nd\n'}, remove=['old.md'])
        for candidate in (edited, shrunk):
            with self.subTest(candidate=candidate):
                self.assertEqual(self.ids(self.run_tool('--base', base, '--candidate', candidate)), [])

    def test_empty_candidate_signal(self):
        base = self.commit({'a.py': 'x = 1\n'})
        result = self.run_tool('--base', base, '--candidate', base)
        self.assertEqual(self.ids(result), ['empty_candidate'])

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

    def test_comment_in_path_with_space(self):
        base = self.commit({'keep.txt': 'k\n'})
        self.commit({'normal.py': '# why one\n', 'avec espace.py': '# why two\n'})
        info = self.run_tool('--base', base)['comments_added']
        self.assertEqual(info, {'count': 2, 'lines': [{'path': 'avec espace.py', 'line': 1, 'text': '# why two'},
                                                      {'path': 'normal.py', 'line': 1, 'text': '# why one'}]})

    def test_comment_lines_ignore_git_hunk_config(self):
        base = self.commit({'code.py': 'a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n', 'next.py': 'x = 1\n'})
        self.commit({'code.py': '# first\na = 1\nb = 2\nc = 3\nd = 4\ne = 5\n# last\n', 'next.py': 'x = 1\n# after\n'})
        self.git('config', 'diff.interHunkContext', '10')
        lines = self.run_tool('--base', base)['comments_added']['lines']
        self.assertEqual([(c['path'], c['line']) for c in lines], [('code.py', 1), ('code.py', 7), ('next.py', 2)])

    def test_previous_with_invalid_counts_refused(self):
        base = self.commit({'a.py': 'x = 1\n'})
        previous = self.repo.parent / 'previous.json'
        for value in ('1e400', '-500', 'true', '"5"', '2.0'):
            with self.subTest(value):
                classes = ','.join(f'"{name}":{{"added":{value}}}' for name in ('product', 'tests', 'docs'))
                previous.write_text(f'{{"base":"{base}","classes":{{{classes}}}}}', encoding='utf-8')
                refused = self.run_tool('--base', base, '--previous', str(previous), code=2)
                self.assertFalse(refused['ok'])
                self.assertIn('--previous', refused['error'])

    def test_safe_directory_option_writes_no_config(self):
        base = self.commit({'a.py': 'x = 1\n'})
        global_config = self.repo.parent / 'global.gitconfig'
        env = {**os.environ, 'GIT_CONFIG_GLOBAL': str(global_config)}
        result = self.run_tool('--base', base, '--safe-directory', env=env)
        self.assertEqual(result['base'], base)
        self.assertFalse(global_config.exists())

    def test_measure_depends_only_on_the_commits(self):
        body = ''.join(f'line {i} of the file\n' for i in range(40))
        first = self.commit({'src/a.py': 'A\n' + body, 'src/b.py': 'B\n' + body[::-1] + '\n', 'sub/s.py': 's\n'})
        self.git('update-index', '--add', '--cacheinfo', f'160000,{first},vendor')
        self.git('commit', '-q', '-m', 'vendor')
        base = self.git('rev-parse', 'HEAD')
        for name in ('src/a.py', 'src/b.py'):
            (self.repo / name).unlink()
        self.commit({'lib/a2.py': 'A\n' + body + 'extra a\n', 'lib/b2.py': 'B\n' + body[::-1] + '\nextra b\n',
                     'top.py': 'y\n' * 30, 'tests/test_t.py': 'assert 1\n' * 500,
                     'a.py': ''.join(f'# a{i}\n' for i in range(40)), 'z.py': ''.join(f'# z{i}\n' for i in range(40))})
        self.git('update-index', '--add', '--cacheinfo', f'160000,{base},vendor')
        self.git('commit', '-q', '--amend', '--no-edit')
        candidate = self.git('rev-parse', 'HEAD')
        other = self.repo.parent / 'other'
        subprocess.run(['git', 'init', '-q', str(other)], check=True)
        (self.repo / 'order.txt').write_bytes(b'z.py\n')
        info = self.repo / '.git' / 'info'
        info.mkdir(exist_ok=True)
        config = self.repo / '.git' / 'config'
        options = ('--base', base, '--candidate', candidate)
        expected = self.run_tool(*options, repo=self.repo / 'sub')
        self.assertEqual(expected['classes']['product']['files'], 6)  # renames paired, gitlink counted
        cases = {'.gitattributes': lambda: (self.repo / '.gitattributes').write_text('tests/** -diff\n'),
                 'info/attributes': lambda: (info / 'attributes').write_text('* -diff\n'),
                 'bigFileThreshold': lambda: self.git('config', 'core.bigFileThreshold', '1'),
                 'renameLimit': lambda: self.git('config', 'diff.renameLimit', '1'),
                 'orderFile': lambda: self.git('config', 'diff.orderFile', 'order.txt'),
                 'relative': lambda: self.git('config', 'diff.relative', 'true'),
                 '.gitmodules': lambda: (self.repo / '.gitmodules').write_text(
                     '[submodule "vendor"]\n\tpath = vendor\n\turl = x\n\tignore = all\n'),
                 'replace': lambda: self.git('replace', candidate, base),
                 'GIT_DIR': lambda: {**os.environ, 'GIT_DIR': str(other / '.git')}}
        saved = config.read_bytes()
        for name, change in cases.items():
            config.write_bytes(saved)
            for path in (self.repo / '.gitattributes', info / 'attributes', self.repo / '.gitmodules'):
                path.unlink(missing_ok=True)
            subprocess.run(['git', '-C', str(self.repo), 'replace', '-d', candidate], capture_output=True)
            with self.subTest(name):
                env = change()
                self.assertEqual(self.run_tool(*options, repo=self.repo / 'sub',
                                               env=env if isinstance(env, dict) else None), expected)

    def test_partial_clone_is_not_fetched(self):
        base = self.commit({'a.py': 'x = 1\n'})
        self.commit({'a.py': 'x = 1\ny = 2\n'})
        self.git('config', 'uploadpack.allowFilter', 'true')
        clone = self.repo.parent / 'clone'
        subprocess.run(['git', 'clone', '-q', '--no-checkout', '--filter=blob:none', self.repo.as_uri(), str(clone)],
                       check=True, capture_output=True)
        subprocess.run(['git', '-C', str(clone), 'config', 'protocol.file.allow', 'always'], check=True)
        before = sorted(clone.rglob('*'))
        refused = self.run_tool('--base', base, code=2, repo=clone)
        self.assertFalse(refused['ok'])
        self.assertEqual(sorted(clone.rglob('*')), before)

    def test_unusable_arguments_refused(self):
        base = self.commit({'a.py': 'x = 1\n'})
        deep = self.repo.parent / 'deep.json'
        deep.write_text('[' * 200000, encoding='utf-8')
        for args in (('--previous', str(deep)), ('--previous', ''), ('--test-ratio', 'nan'), ('--test-ratio', 'inf'),
                     ('--test-ratio', '-5'), ('--test-slack', '-1'), ('--test-slack', '1.5')):
            with self.subTest(args):
                refused = self.run_tool('--base', base, *args, code=2)
                self.assertFalse(refused['ok'])

    def write_wave(self, files):
        wave = self.repo.parent / 'wave'
        for name, content in files.items():
            path = wave / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return wave

    def test_wave_dir_alone_measures_each_class(self):
        wave = self.write_wave({'brief.md': 'one two\nthree\n', 'notes/log.txt': 'four five',
                                'bad.md': b'six \xff seven', 'nul.txt': 'a\0b', 'ops.json': '{"a": 1}',
                                'ev.jsonl': '{}\n{}\n', 't.tsv': 'a\tb\n', 'run.py': 'x = 1\n\n  \ny = 2\n',
                                'go.ps1': 'Write-Host 1\r\n', 'sub/do.sh': 'echo\n', 'img.png': b'\x89PNG\0\0',
                                'ctl.txt': b'\x08\x01', 'page.txt': 'p\fq r\t', 'bom.md': '﻿\nhello',
                                'bom.ps1': '﻿\nGet-Date'})
        result = self.run_tool('--wave-dir', str(wave), repo=False)
        self.assertEqual(result['wave_dir'], {
            'path': str(wave.resolve()), 'files': 15, 'prose': {'files': 4, 'words': 9},
            'data': {'files': 3, 'bytes': 18}, 'scripts': {'files': 4, 'lines': 5},
            'other': {'files': 4, 'bytes': 22}})

    def test_wave_dir_follows_no_link_or_junction(self):
        wave = self.write_wave({'brief.md': 'one two\n'})
        expected = self.run_tool('--wave-dir', str(wave), repo=False)['wave_dir']
        outside = self.repo.parent / 'outside'
        outside.mkdir()
        (outside / 'big.md').write_text('word ' * 5000, encoding='utf-8')
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(outside), str(wave / 'joined'))
        else:
            os.symlink(outside, wave / 'joined', target_is_directory=True)
        self.assertEqual(self.run_tool('--wave-dir', str(wave), repo=False)['wave_dir'], expected)
        refused = self.run_tool('--wave-dir', str(wave / 'joined'), repo=False, code=2)
        self.assertIn('symbolic link or junction', refused['error'])

    def test_failures_without_wave_dir_keep_parser_messages(self):
        refused = self.run_tool('extra', code=2)
        self.assertEqual(refused, {'ok': False, 'error': 'the following arguments are required: --base'})

    def test_writing_outweighs_diff_at_exact_threshold(self):
        base = self.commit({'a.py': 'x = 1\n'})
        self.commit({'a.py': 'x = 1\ny = 2\n', 'tests/t.py': 't\n', 'd.md': 'd\n'})
        wave = self.write_wave({'w.md': 'w ' * 2090})
        at = self.run_tool('--base', base, '--wave-dir', str(wave))
        self.assertEqual((at['wave_dir']['added_lines'], at['wave_dir']['prose_words_per_added_line']), (3, 696.7))
        self.assertNotIn('writing_outweighs_diff', self.ids(at))
        (wave / 'more.txt').write_text('w', encoding='utf-8')
        over = self.run_tool('--base', base, '--wave-dir', str(wave))
        self.assertEqual(over['signals'][-1], {'id': 'writing_outweighs_diff',
                                               'detail': 'wave prose 2091 words > 2000 + 30 x added lines 3'})

    def test_unknown_reference_is_refused(self):
        self.commit({'a.py': 'x\n'})
        refused = self.run_tool('--base', 'no-such-ref', code=2)
        self.assertEqual(refused['ok'], False)
        self.assertIn('--base', refused['error'])


if __name__ == '__main__':
    unittest.main()
