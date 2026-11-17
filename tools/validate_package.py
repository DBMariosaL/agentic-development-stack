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

For every skill: Markdown links and in-page anchors, resource paths
(``references/``, ``scripts/``, ``assets/``, ``agents/``) cited in code spans, also inside a
command line, compilation and standard-library imports of Python files, UTF-8 text, no
cache or temporary file, regular files only, no machine path (drive letter, UNC, /home/,
/Users/) or 40-hex snapshot in Markdown. A link or resource is sound only if it names a
package file at exact case, with '/' separators: the verdict does not depend on the host
file system. With --provenance, the bytes of every package file are compared with the
recorded provenance.

Markdown is not parsed as CommonMark. The validator reads a declared subset, the one the
package uses (see ``blocks``), and refuses a construct outside it by naming it and saying
how to rewrite it, rather than guessing; HTML blocks and HTML links are refused. A bracketed label with no
definition (``[P][R]``) is plain text, as in CommonMark.

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
RESOURCE = re.compile(r'(?:references|scripts|assets|agents)/[\w.\-/]+')
MACHINE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|\\\\[^\s\\]+\\|/(?:home|Users)/|[0-9A-Fa-f]{40}')
FENCE = re.compile(r'( *)(`{3,}(?=[^`]*$)|~{3,})')
MARKER = re.compile(r' {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)')
ATX = re.compile(r' {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*')
INLINE = re.compile(r'\\[!-/:-@\[-`{-~]|`+')
DEST = r'[ \t]*\n?[ \t]*(?:<([^<>\n]*)>|((?:[^\s()]|\([^\s()]*\))+))'
INLINE_DEST = re.compile(DEST + r'(?:\s+(?:"[^"]*"|\'[^\']*\'|\([^()]*\)))?\s*\)')
REFERENCE = re.compile(r'^ {0,3}(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)*\[[^\]]+\]:' + DEST, re.M)
UNREADABLE_LINK = ('link not read: write [text](path), [text](<path with spaces>) '
                   'or [text](path "title"); HTML links are not read')


def blocks(text):
    """Read the supported Markdown subset; returns (prose chunks, headings, refusals).

    Supported: ATX headings indented 0-3 spaces, Setext headings, paragraphs, tables, nested
    lists, fenced code blocks (also inside list items), indented code blocks outside lists,
    code spans (also across the lines of one paragraph), backslash escapes, inline links and
    images, reference definitions. Refused with their line, because they change what is code
    and what is prose: block quotes, HTML blocks, tab indentation, and a block indented four
    spaces or more after a blank line inside a list.
    """
    chunks, headings, refused = [], [], []
    chunk, fence, in_list, prev = [], None, False, 'blank'

    def flush():
        if chunk:
            chunks.append('\n'.join(chunk))
            chunk.clear()

    def refuse(number, construct):
        if prev != 'skip':
            refused.append((number, construct))
        return 'skip'

    for number, line in enumerate(text.split('\n'), 1):
        indent = len(line) - len(line.lstrip(' '))
        if fence:
            if line.strip() and indent < fence[1]:
                fence = None  # the line leaves the list item that held the fence
            else:
                closing = re.fullmatch(r' *(`+|~+)[ \t]*', line)
                if closing and closing[1][0] == fence[0][0] and len(closing[1]) >= len(fence[0]) \
                        and indent <= fence[1] + 3:
                    fence = None
                continue
        if not line.strip():
            flush()
            prev = 'blank'
            continue
        marker, heading = MARKER.match(line), ATX.fullmatch(line)
        if indent == 0 and not marker and (prev != 'para' or heading):
            in_list = False
        opening = FENCE.match(line)
        if opening and (indent < 4 or prev != 'para'):
            flush()
            fence, prev = (opening[2], indent), 'code'
        elif indent >= 4 and prev != 'para':
            flush()
            prev = refuse(number, 'block indented 4+ spaces after a blank line in a list: indent it by the '
                                  "item's content width (2 for '- ', 3 for '1. ') or use a fenced block") \
                if in_list else 'code'
        elif re.match(r' {0,3}>', line):
            flush()
            prev = refuse(number, 'block quote: rewrite without ">"')
        elif re.match(r' {0,3}<(?![A-Za-z][\w+.-]*:)[A-Za-z/!?]', line):
            flush()
            prev = refuse(number, 'HTML block: put it in a fenced code block or write Markdown')
        elif heading:
            flush()
            headings.append(heading[1] or '')
            chunks.append(heading[1] or '')
            prev = 'heading'
        elif prev == 'para' and re.fullmatch(r' {0,3}(=+|-+)[ \t]*', line) \
                and not MARKER.match(chunk[0]) and not chunk[0].lstrip().startswith('|'):
            headings.append(' '.join(part.strip() for part in chunk))
            flush()
            prev = 'heading'
        else:
            if '\t' in line[:indent + 1]:
                refused.append((number, 'tab indentation: indent with spaces'))
            in_list = in_list or bool(marker)
            if prev != 'para' or marker or line.lstrip().startswith('|'):
                flush()
            chunk.append(line)
            prev = 'para'
    flush()
    return chunks, headings, refused


def inline(chunk):
    """Chunk with backslash escapes as \\x1a and code spans as \\x1b; returns (text, span contents)."""
    out, spans, pos = [], [], 0
    while match := INLINE.search(chunk, pos):
        out.append(chunk[pos:match.start()])
        pos = match.end()
        if match[0][0] == '\\':
            out.append('\x1a')
            continue
        close = re.compile(f'(?<!`){match[0]}(?!`)').search(chunk, pos)
        if close:
            spans.append(chunk[pos:close.start()])
            out.append('\x1b')
            pos = close.end()
        else:
            out.append(match[0])
    out.append(chunk[pos:])
    return ''.join(out), spans


def link_targets(chunks):
    """Destinations after every '](' and of reference definitions, outside code; None if unreadable."""
    targets = []
    for chunk in chunks:
        text, _ = inline(chunk)
        for match in re.finditer(r'\]\(', text):
            dest = INLINE_DEST.match(text, match.end())
            targets.append(None if dest is None else dest[1] if dest[1] is not None else dest[2])
        targets += [m[1] if m[1] is not None else m[2] for m in REFERENCE.finditer(text)]
        if re.search(r'<(?:a|img)\s', text, re.I):
            targets.append(None)
    return targets


def slug(heading):
    """GitHub anchor of a heading's rendered text: links and images reduced to their text,
    emphasis and inline HTML removed, code spans kept."""
    text, spans = inline(heading)
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\*+|(?<!\w)_+|_+(?!\w)|<[^>]*>', '', text)
    for span in spans:
        text = text.replace('\x1b', span.strip(), 1)
    return re.sub(r'[^\w\- ]', '', text.strip().lower()).replace(' ', '-')


def anchors(headings):
    """Heading anchors with GitHub's numbering of repeats: Zed, Zed, Zed 1 give zed, zed-1, zed-1-1."""
    seen = {}
    for heading in headings:
        base = anchor = slug(heading)
        while anchor in seen:
            seen[base] += 1
            anchor = f'{base}-{seen[base]}'
        seen[anchor] = 0
    return set(seen)


def resolve(names, folder, target):
    """Package path that target names from folder, only if a file has exactly that path."""
    path = posixpath.normpath(posixpath.join(folder, target)) if isinstance(target, str) else None
    return path if path in names else None


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
    checks, files, texts, parsed = [], [], {}, {}

    def check(name, condition, detail=''):
        checks.append({'check': name, 'passed': bool(condition), 'detail': detail})

    def parse(key):
        if key not in parsed:
            text = texts[key]
            if key.endswith('SKILL.md'):  # frontmatter lines blanked, numbering kept
                text = re.sub(r'\A---\n.*?\n---\n', lambda m: '\n' * m[0].count('\n'), text, flags=re.S)
            parsed[key] = blocks(text)
        return parsed[key]

    paths = sorted(p for p in root.rglob('*') if p.is_file())
    names = {p.relative_to(root).as_posix() for p in paths}
    for path in paths:
        rel = path.relative_to(root)
        data = path.read_bytes()
        entry = {'path': rel.as_posix(), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        if path.suffix in TEXT_SUFFIXES:
            try:
                texts[rel.as_posix()] = data.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
                entry['words'] = len(texts[rel.as_posix()].split())
            except UnicodeDecodeError as exc:
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
                check(f'{name}:no_machine_snapshot', not MACHINE.search(body))
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
                            icon = resolve(names, name, interface[key])
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
        if '__pycache__' in path.parts or path.suffix in {'.pyc', '.lock', '.tmp'}:
            check(f'{rel}:no_cache_or_temp', False)
        if path.suffix == '.py' and text is not None:
            try:
                compile(text, str(path), 'exec')
                check(f'{rel}:compiles', True)
                outside = stdlib_imports(text, str(path))
                check(f'{rel}:stdlib_imports', not outside, outside)
            except (SyntaxError, ValueError) as exc:
                check(f'{rel}:compiles', False, str(exc))
        if path.suffix != '.md' or text is None:
            continue
        check(f'{rel}:no_machine_snapshot', not MACHINE.search(text))
        chunks, headings, refused = parse(key)
        for number, construct in refused:
            check(f'{rel}:unsupported:{number}', False, construct)
        skill, folder = rel.parts[0], posixpath.dirname(key)
        for index, target in enumerate(link_targets(chunks)):
            if target is None:
                check(f'{rel}:link:{index}', False, UNREADABLE_LINK)
                continue
            if re.match(r'^[a-z][a-z0-9+.-]*://', target) or target.startswith('mailto:'):
                continue
            file_part, _, anchor = target.partition('#')
            anchor = unquote(anchor)
            if not file_part:
                check(f'{rel}:link:{index}', anchor in anchors(headings), target)
                continue
            dest = resolve(names, folder, unquote(file_part))
            ok = dest is not None
            if ok and anchor and dest.endswith('.md'):
                ok = dest in texts and anchor in anchors(parse(dest)[1])
            check(f'{rel}:link:{index}', ok, target)
        index = 0
        for chunk in chunks:
            for span in inline(chunk)[1]:
                for token in span.split():
                    token = token.strip('"\'(),;:')
                    token = token[2:] if token.startswith('./') else token
                    if RESOURCE.fullmatch(token):
                        found = [p for p in (resolve(names, skill, token), resolve(names, folder, token)) if p]
                        check(f'{rel}:resource:{index}', any(p.startswith(skill + '/') for p in found), token)
                        index += 1
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
                       'Markdown is read as a declared subset, not as CommonMark; constructs outside it are refused.',
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
