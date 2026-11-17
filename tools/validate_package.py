"""Offline structural validation of a skill distribution package, with explicit proof limits.

Adapted from skills-workflow-alpha-20261031/validate_package.py, then from the v7 version:
writes only to --output.

The package must contain exactly the skills of one distribution recognised by
tools/rc_update.py (single registry). Rules depend on the role of each skill:

- RC skills keep the historical rules unchanged: frontmatter subset, name, description,
  metadata keys, UI strings quoted as JSON, short description length, explicit
  ``$skill`` invocation and normal discovery. Their ``agents/openai.yaml`` is read in its
  canonical form only (``section:`` lines, then ``  key: <JSON value>`` with one space
  after the colon); any other line is refused.
- Dependency copies are accepted as delivered and never rewritten to fit RC conventions.
  Checked: name and description, the limited ``agents/openai.yaml`` subset they use,
  icons resolved from the skill root, the invocation policy recorded at snapshot time
  (Unslop stays explicit-only), and closure of their local resources.

For every skill: compilation and standard-library imports of Python files, UTF-8 text without BOM, no
cache or temporary file, regular files only, no blank in a file name, no machine path
(drive letter, UNC, /home/, /Users/) or 40-hex snapshot in Markdown. With --provenance,
the bytes of every package file are compared with the recorded provenance.

Markdown (extension .md in any case) is scanned as raw text: the validator does not tell code from prose, does not
render Markdown and does not read HTML. What it guarantees, one sentence per rule:

1. Destinations. Every text after '](' (up to ')' or the end of the line), the first word
   after every '[label]:' that starts a line (after indentation and list or quote markers,
   or on the next line), and every href= or src= value is accepted only if it has a
   scheme (not checked further), or is '#anchor' with an anchor of rule 3, or is a
   relative path of letters, digits and ._-/%# that, %xx decoded and without chevrons,
   names a package file at exact case and carries an anchor only into a Markdown file
   whose rule-3 ids hold it; anything else is refused with the rule that failed.
2. Resources. Every word starting with references/, scripts/ or assets/ in a Markdown
   file, taken whole up to a blank, a code delimiter, a sentence mark or '#', is accepted only
   if it is made of letters, digits and ._-/ and names a file of its skill at exact case
   from the skill root; a file name with a blank is refused for itself.
3. Anchors. The only ids are those of ATX headings indented 0-3 spaces, outside a ``` or
   ~~~ fence, whose text holds no link, defined [label], entity, HTML, backslash or
   underscore at a word edge, numbered on repeats as on GitHub; Setext headings give
   none, and a fence mark after a list or quote marker, indented 4+ spaces or by a tab,
   or a backtick fence whose info string holds a backtick puts the rest of the file in a
   fence, so that doubt refuses rather than accepts.
4. HTML that could hide a heading is refused by name: '<!--' anywhere, and outside a
   fence a line that starts (indented 0-3 spaces) with '<' then a letter, '/' or '!',
   unless it is an autolink with a scheme.

The frontmatter and UI readers accept only the subsets present in these files; they are
not YAML parsers. Structural success certifies neither the quality of a prompt, nor the
behaviour of an agent, nor the output of a vendored script beyond what is checked here.
No dependency is installed and no tool or development mandate is executed.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import unquote

_spec = importlib.util.spec_from_file_location('rc_update_registry', Path(__file__).with_name('rc_update.py'))
_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_registry)
DISTRIBUTIONS = _registry.DISTRIBUTIONS
ALL_SKILLS = _registry.ALL_SKILLS

NAMES = _registry.SKILLS  # RC skills, historical rules
# Invocation policy of the dependency copies as delivered (upstream snapshot of 2026-11-09).
DEPENDENCY_POLICY = {
    'gpt-prompt-optimizer': {'allow_implicit_invocation': True, 'default_prompt': True},
    'claude-opus-prompt-optimizer': {'allow_implicit_invocation': True, 'default_prompt': True},
    'claude-fable-prompt-optimizer': {'allow_implicit_invocation': True, 'default_prompt': True},
    'unslop': {'allow_implicit_invocation': False, 'default_prompt': False},
}
TEXT_SUFFIXES = {'.md', '.py', '.yaml', '.yml', '.svg', '.txt', '.json'}
MACHINE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|\\\\[^\s\\]+\\|/(?:home|Users)/|[0-9A-Fa-f]{40}')
DEFINITION = r'^[ \t>]*(?:(?:[-*+]|\d{1,9}[.)])[ \t>]+)*\['
LABELS = re.compile(DEFINITION + r'([^\]\n]+)\]:', re.M)
DESTINATIONS = re.compile(
    r'\]\(([^)\n]*)'
    r'|' + DEFINITION + r'[^\]\n]+\]:[ \t]*\n?[ \t>]*(\S*)'
    r'|(?:href|src)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.M)
RESOURCE = re.compile(r'(?:(?<=\./)|(?<![\w./\-]))(?:references|scripts|assets)/[^\s`"\'()<>\[\]{},;:!?|*#]+')
SAFE_RESOURCE = re.compile(r'(?:references|scripts|assets)/[\w.\-/]*[\w\-]')
HEADING = re.compile(r' {0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*')
NOT_SIMPLE = re.compile(r'\]\(|\]\[|&#?\w+;|<|\\|(?<!\w)_|_(?!\w)')
HTML_LINE = re.compile(r' {0,3}<(?![A-Za-z][A-Za-z0-9+.-]*:)[A-Za-z/!]')
DEAD = 'not a package file at exact case; an example in code carries a scheme'
ANCHORLESS = 'no simple ATX heading has this id'
UNSAFE = "unsupported destination: use letters, digits and ._-/%# or a URL with a scheme"


def outline(text):
    """Ids of the simple ATX headings outside fences, GitHub numbering of repeats, and the
    numbers of the lines outside fences that open an HTML block."""
    seen, fence, html = {}, None, []
    defined = {' '.join(label.split()).lower() for label in LABELS.findall(text)}
    for number, line in enumerate(text.split('\n'), 1):
        stripped = line.lstrip(' \t')
        inner = re.sub(r'^(?:(?:[-*+]|\d{1,9}[.)]|>)[ \t]*)+', '', stripped)
        opening = re.match(r'(`{3,}|~{3,})(.*)', inner)
        if opening:
            margin = line[:len(line) - len(stripped)]
            if len(margin) >= 4 or '\t' in margin or inner != stripped or (opening[1][0] == '`' and '`' in opening[2]):
                break  # in doubt, the rest of the file is in a fence
            if fence is None:
                fence = opening[1]
            elif opening[1][0] == fence[0] and len(opening[1]) >= len(fence) and not opening[2].strip():
                fence = None
            continue
        if fence is None and HTML_LINE.match(line):
            html.append(number)
        heading = HEADING.fullmatch(line) if fence is None else None
        labels = {' '.join(label.split()).lower() for label in re.findall(r'\[([^\]\n]+)\]', heading[1])} \
            if heading else set()
        if heading and not NOT_SIMPLE.search(heading[1]) and not labels & defined:
            base = anchor = re.sub(r'[^\w\- ]', '', heading[1].lower()).replace(' ', '-')
            while anchor in seen:
                seen[base] += 1
                anchor = f'{base}-{seen[base]}'
            seen[anchor] = 0
    return set(seen), html


def scalar(value):
    if value.startswith('"'):
        parsed = json.loads(value)
        if not isinstance(parsed, str):
            raise ValueError('String required')
        return parsed
    if not value or value[0] in "'[{>|&*!":
        raise ValueError('Unsupported YAML scalar: use plain text or JSON quoted string')
    if ': ' in value or ' #' in value:
        raise ValueError('Quote ambiguous plain YAML scalar')
    return value


def frontmatter(text):
    match = re.match(r'\A---\n(.*?)\n---(?:\n|$)', text, re.S)
    if not match:
        raise ValueError('Invalid frontmatter')
    data = {}
    for line in match[1].splitlines():
        key, sep, value = line.partition(':')
        if not sep or not re.fullmatch('[a-z][a-z_-]*', key) or key in data:
            raise ValueError('Invalid or duplicate frontmatter key')
        data[key] = scalar(value.strip())
    return data, text[match.end():]


def ui_scalar(value):
    if value in ('true', 'false'):
        return value == 'true'
    if value.startswith('"'):
        return scalar(value)
    if value[0] in "'[{>|&*!%@`" or ': ' in value or ' #' in value:
        raise ValueError(f'Unsupported UI scalar: {value!r}')
    return value


def read_ui(text):
    """Limited reader for agents/openai.yaml as used by these skills, not a YAML parser.

    Accepts top-level mappings, second-level keys with JSON-quoted, boolean or plain
    scalars, plain-scalar continuation lines and block sequences of scalars. Anything
    else is refused.
    """
    root, section, last, seq = {}, None, None, None
    for number, raw in enumerate(text.splitlines(), 1):
        if '\t' in raw:
            raise ValueError(f'line {number}: tab')
        if not raw.strip():
            last = None
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        content = raw.strip()
        top = re.fullmatch(r'([a-z_]+):', content)
        item = re.fullmatch(r'([a-z_]+):(?: (.*))?', content)
        if indent == 0 and top:
            if top[1] in root:
                raise ValueError(f'line {number}: duplicate key')
            section = root[top[1]] = {}
            last = seq = None
        elif section is not None and content.startswith('- ') and seq is not None and indent >= seq[1]:
            seq[0].append(ui_scalar(content[2:].strip()))
        elif section is not None and indent == 2 and item:
            key, value = item[1], item[2]
            if key in section:
                raise ValueError(f'line {number}: duplicate key')
            if value is None:
                section[key] = []
                seq, last = (section[key], indent), None
            else:
                section[key] = ui_scalar(value.strip())
                seq = None
                last = (section, key, indent) if isinstance(section[key], str) and not value.startswith('"') else None
        elif last is not None and indent > last[2]:
            section_, key, _ = last
            section_[key] = section_[key] + ' ' + content
        else:
            raise ValueError(f'line {number}: outside the supported subset')
    return root


def stdlib_imports(source, filename):
    names = set()
    for node in ast.walk(ast.parse(source, filename)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split('.')[0])
    allowed = set(getattr(sys, 'stdlib_module_names', ())) | {'__future__'}
    return sorted(names - allowed)


def validate(root, provenance=None):
    root = root.resolve()
    checks, files, texts = [], [], {}

    def check(name, condition, detail=''):
        checks.append({'check': name, 'passed': bool(condition), 'detail': detail})

    def resolve(folder, target):
        path = posixpath.normpath(posixpath.join(folder, target)) if isinstance(target, str) else None
        return path if path in names else None

    paths = sorted(p for p in root.rglob('*') if p.is_file())
    names = {p.relative_to(root).as_posix() for p in paths}
    for path in paths:
        rel = path.relative_to(root)
        data = path.read_bytes()
        entry = {'path': rel.as_posix(), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = data.decode('utf-8')
                if text.startswith('\ufeff'):
                    raise UnicodeError('UTF-8 BOM: save the file without BOM')
                texts[rel.as_posix()] = text.replace('\r\n', '\n').replace('\r', '\n')
                entry['words'] = len(texts[rel.as_posix()].split())
            except UnicodeError as exc:
                check(f'{rel}:utf8', False, str(exc))
        files.append(entry)

    present = {p.name for p in root.iterdir() if p.is_dir()}
    distribution = next((d for d, skills in DISTRIBUTIONS.items() if present == set(skills)), None)
    check('distribution_directories', distribution is not None, distribution or sorted(present))
    check('no_file_at_package_root', not [p for p in root.iterdir() if p.is_file()])
    roles = DISTRIBUTIONS.get(distribution, {s: ('rc' if s in NAMES else 'dependency') for s in present})

    for name in [s for s in ALL_SKILLS if s in roles]:
        check(f'{name}:skill_exists', f'{name}/SKILL.md' in names)
        text, ui = texts.get(f'{name}/SKILL.md'), texts.get(f'{name}/agents/openai.yaml')
        check(f'{name}:ui_exists', f'{name}/agents/openai.yaml' in names)
        if text is None:
            continue
        if roles[name] == 'rc':
            try:
                meta, body = frontmatter(text)
                check(f'{name}:frontmatter_subset', True)
                check(f'{name}:name', meta.get('name') == name and len(name) < 64)
                desc = meta.get('description', '')
                check(f'{name}:description', bool(desc) and len(desc) <= 1024 and '<' not in desc and '>' not in desc)
                check(f'{name}:metadata_keys', set(meta) == {'name', 'description'})
                check(f'{name}:no_unfinished_scaffold', not re.search(r'^\s*\[TODO:', body, re.M))
                check(f'{name}:no_automatic_reference_import', not re.search(r'^@\S+', body, re.M))
            except (ValueError, json.JSONDecodeError) as exc:
                check(f'{name}:frontmatter_subset', False, str(exc))
            if ui is not None:
                values = {}
                for number, line in enumerate(ui.splitlines(), 1):
                    if not line.strip() or re.fullmatch(r'[a-z_]+:', line):
                        continue
                    item = re.fullmatch(r'  ([a-z_]+): (\S.*)', line)
                    if not item or item[1] in values:
                        check(f'{name}:ui_line:{number}', False,
                              'canonical form only: "  key: <JSON value>", one space after the colon, no repeat')
                        continue
                    try:
                        values[item[1]] = json.loads(item[2])
                    except json.JSONDecodeError as exc:
                        check(f'{name}:ui_string:{item[1]}', False, str(exc))
                short, prompt = values.get('short_description'), values.get('default_prompt')
                check(f'{name}:ui_short_description', isinstance(short, str) and 25 <= len(short) <= 64)
                check(f'{name}:ui_invocation', isinstance(prompt, str) and f'${name}' in prompt)
                check(f'{name}:ui_normal_discovery', values.get('allow_implicit_invocation', True) is True)
        else:
            try:
                meta, body = frontmatter(text)
                check(f'{name}:frontmatter_subset', True)
                check(f'{name}:name', meta.get('name') == name)
                desc = meta.get('description', '')
                check(f'{name}:description', bool(desc) and len(desc) <= 1024 and '<' not in desc and '>' not in desc,
                      f'{len(desc)} characters')
            except (ValueError, json.JSONDecodeError) as exc:
                check(f'{name}:frontmatter_subset', False, str(exc))
            if ui is not None:
                try:
                    doc = read_ui(ui)
                    check(f'{name}:ui_subset', True)
                except (ValueError, json.JSONDecodeError) as exc:
                    check(f'{name}:ui_subset', False, str(exc))
                    doc = None
                if doc is not None:
                    interface = doc.get('interface') if isinstance(doc.get('interface'), dict) else {}
                    policy = doc.get('policy') if isinstance(doc.get('policy'), dict) else {}
                    check(f'{name}:ui_display_name', isinstance(interface.get('display_name'), str)
                          and interface.get('display_name'))
                    short = interface.get('short_description')
                    check(f'{name}:ui_short_description', isinstance(short, str) and short,
                          f'{len(short) if isinstance(short, str) else 0} characters')
                    for key in ('icon_small', 'icon_large'):
                        if key in interface:
                            icon = resolve(name, interface[key])
                            check(f'{name}:ui_{key}', icon and icon.startswith(name + '/'), interface[key])
                    expected = DEPENDENCY_POLICY.get(name)
                    check(f'{name}:ui_policy_known', expected is not None)
                    if expected:
                        implicit = policy.get('allow_implicit_invocation')
                        check(f'{name}:ui_invocation_policy', implicit is expected['allow_implicit_invocation'],
                              f'allow_implicit_invocation={implicit!r}')
                        prompt = interface.get('default_prompt')
                        if expected['default_prompt']:
                            check(f'{name}:ui_invocation', isinstance(prompt, str) and f'${name}' in prompt)
                        else:
                            check(f'{name}:ui_no_default_prompt', prompt is None)
                    products = policy.get('products')
                    check(f'{name}:ui_products', isinstance(products, list) and products
                          and all(isinstance(p, str) for p in products))

    for path in paths:
        rel = path.relative_to(root)
        key = rel.as_posix()
        text = texts.get(key)
        check(f'file:{rel}:regular', not path.is_symlink())
        if re.search(r'\s', key):
            check(f'file:{rel}:name', False, 'file name contains a blank: rename it without spaces')
        suffix = path.suffix.lower()
        if '__pycache__' in path.parts or suffix in {'.pyc', '.lock', '.tmp'}:
            check(f'{rel}:no_cache_or_temp', False)
        if suffix == '.py' and text is not None:
            try:
                compile(text, str(path), 'exec')
                check(f'{rel}:compiles', True)
                outside = stdlib_imports(text, str(path))
                check(f'{rel}:stdlib_imports', not outside, outside)
            except (SyntaxError, ValueError) as exc:
                check(f'{rel}:compiles', False, str(exc))
        if suffix != '.md' or text is None:
            continue
        check(f'{rel}:no_machine_snapshot', not MACHINE.search(text))
        if '<!--' in text:
            check(f'{rel}:html_comment', False, 'HTML comment: remove it, a heading inside would count')
        for number in outline(text)[1]:
            check(f'{rel}:html_block:{number}', False, 'HTML block outside a fence: put it in a fenced block')
        skill, folder = rel.parts[0], posixpath.dirname(key)
        for index, match in enumerate(DESTINATIONS.finditer(text)):
            target = next(g for g in match.groups() if g is not None).strip()
            if target.startswith('<') and target.endswith('>'):
                target = target[1:-1]
            if re.match(r'[A-Za-z][A-Za-z0-9+.-]*:', target):
                continue
            file_part, _, anchor = target.partition('#')
            if not re.fullmatch(r'[\w.\-/%]*(?:#[\w.\-%]*)?', target) or not target:
                ok, reason = False, UNSAFE
            elif not file_part:
                ok, reason = unquote(anchor) in outline(text)[0], ANCHORLESS
            else:
                dest = resolve(folder, unquote(file_part))
                ok = dest is not None and (not anchor or (dest.lower().endswith('.md') and dest in texts
                                                          and unquote(anchor) in outline(texts[dest])[0]))
                reason = ANCHORLESS if dest else DEAD
            check(f'{rel}:link:{index}', ok, target if ok else f'{target} ({reason})')
        for index, word in enumerate(RESOURCE.findall(text)):
            word = word.rstrip('.')
            found = (resolve(skill, word) or '').startswith(skill + '/')
            blank = any(n.startswith(posixpath.normpath(posixpath.join(skill, word)) + ' ') for n in names)
            if not SAFE_RESOURCE.fullmatch(word):
                check(f'{rel}:resource:{index}', False, f'{word} (unsupported resource word: use letters, digits and ._-/)')
            elif not blank:  # a word cut at a blank of an existing file name: its name check reports it
                check(f'{rel}:resource:{index}', found, word if found else f'{word} (not a file of the skill at exact case)')
    if provenance is not None:
        records = {}
        for item in json.loads(Path(provenance).read_text(encoding='utf-8'))['files']:
            if item['path'].startswith('package/'):
                records[item['path'][len('package/'):]] = item
        actual = {f['path']: f for f in files}
        check('provenance:inventory', set(records) == set(actual),
              sorted(set(records) ^ set(actual)))
        for rel, item in sorted(records.items()):
            got = actual.get(rel, {}).get('sha256')
            ok = got == item.get('sha256')
            if item.get('adaptation') == 'byte-identical':
                ok = ok and got == item.get('source_sha256')
            check(f'provenance:{rel}', ok, item.get('adaptation', ''))
    return {'distribution': distribution, 'roles': roles, 'checks': checks,
            'passed': sum(c['passed'] for c in checks),
            'failed': sum(not c['passed'] for c in checks), 'files': files,
            'limits': ['Structural subset validator; frontmatter and UI readers are not YAML parsers.',
                       'Markdown is scanned as raw text: every destination and resource word is checked, '
                       'code examples included; anchors resolve only to simple ATX headings.',
                       'Dependency copies are checked as delivered, not rewritten; their prompt quality is not assessed.',
                       'Python files are compiled and their imports listed; vendored scripts are not executed here.',
                       'No runtime, launch, model quality or product behavior is certified.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--provenance', type=Path, help='provenance.json whose package/ entries must match the bytes')
    args = parser.parse_args()
    result = validate(args.package, args.provenance)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ['distribution', 'passed', 'failed']}))
    raise SystemExit(bool(result['failed']))
