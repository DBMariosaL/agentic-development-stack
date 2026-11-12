"""Offline structural validation of a skill distribution package, with explicit proof limits.

Adapted from skills-workflow-alpha-20261031/validate_package.py, then from the v7 version:
writes only to --output.

The package must contain exactly the skills of one distribution recognised by
tools/rc_update.py (single registry). Rules depend on the role of each skill:

- RC skills keep the historical rules unchanged: frontmatter subset, name, description,
  metadata keys, UI strings quoted as JSON, short description length, explicit
  ``$skill`` invocation and normal discovery.
- Dependency copies are accepted as delivered and never rewritten to fit RC conventions.
  Checked: name and description, the limited ``agents/openai.yaml`` subset they use,
  icons resolved from the skill root, the invocation policy recorded at snapshot time
  (Unslop stays explicit-only), and closure of their local resources.

For every skill: Markdown links and in-page anchors, inline resource paths
(``references/``, ``scripts/``, ``assets/``, ``agents/``), compilation and standard-library
imports of Python files, no cache or temporary file, regular files only, no machine path or
40-hex snapshot in Markdown. With --provenance, the bytes of every package file are
compared with the recorded provenance.

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
import re
import sys
from pathlib import Path

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
    'unslop': {'allow_implicit_invocation': False, 'default_prompt': False},
}
TEXT_SUFFIXES = {'.md', '.py', '.yaml', '.yml', '.svg', '.txt', '.json'}
RESOURCE = re.compile(r'`((?:references|scripts|assets|agents)/[A-Za-z0-9_.\-/]+)`')
LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')


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


def slug(heading):
    heading = re.sub(r'[^\w\- ]', '', heading.strip().lower())
    return heading.replace(' ', '-')


def anchors(text):
    return {slug(m[1]) for m in re.finditer(r'^#{1,6}\s+(.+?)\s*#*\s*$', text, re.M)}


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
    checks = []
    files = []

    def check(name, condition, detail=''):
        checks.append({'check': name, 'passed': bool(condition), 'detail': detail})

    present = {p.name for p in root.iterdir() if p.is_dir()}
    distribution = next((d for d, skills in DISTRIBUTIONS.items() if present == set(skills)), None)
    check('distribution_directories', distribution is not None, distribution or sorted(present))
    check('no_file_at_package_root', not [p for p in root.iterdir() if p.is_file()])
    roles = DISTRIBUTIONS.get(distribution, {s: ('rc' if s in NAMES else 'dependency') for s in present})

    for name in [s for s in ALL_SKILLS if s in roles]:
        folder = root / name
        path = folder / 'SKILL.md'
        check(f'{name}:skill_exists', path.is_file())
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
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
                check(f'{name}:no_machine_snapshot', not re.search(r'[A-Z]:[\\/]|[a-f0-9]{40}\b', body))
            except (ValueError, json.JSONDecodeError) as exc:
                check(f'{name}:frontmatter_subset', False, str(exc))
            ui = folder / 'agents/openai.yaml'
            check(f'{name}:ui_exists', ui.is_file())
            if ui.is_file():
                values = {}
                for line in ui.read_text(encoding='utf-8').splitlines():
                    if line.startswith('  '):
                        key, _, value = line.strip().partition(':')
                        try:
                            values[key] = json.loads(value.strip())
                        except json.JSONDecodeError as exc:
                            check(f'{name}:ui_string:{key}', False, str(exc))
                short = values.get('short_description', '')
                check(f'{name}:ui_short_description', 25 <= len(short) <= 64)
                check(f'{name}:ui_invocation', f'${name}' in values.get('default_prompt', ''))
                check(f'{name}:ui_normal_discovery', 'allow_implicit_invocation: false' not in ui.read_text(encoding='utf-8'))
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
            ui = folder / 'agents/openai.yaml'
            check(f'{name}:ui_exists', ui.is_file())
            if ui.is_file():
                try:
                    doc = read_ui(ui.read_text(encoding='utf-8'))
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
                            icon = interface[key]
                            dest = (folder / icon).resolve() if isinstance(icon, str) else None
                            check(f'{name}:ui_{key}', dest is not None and not Path(icon).is_absolute()
                                  and dest.is_file() and dest.is_relative_to(folder.resolve()), icon)
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

    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if path.is_file() and path.suffix == '.md':
            body = path.read_text(encoding='utf-8')
            check(f'{rel}:no_machine_snapshot', not re.search(r'[A-Z]:[\/]|[a-f0-9]{40}', body))
        if path.is_file() and path.suffix == '.py':
            try:
                source = path.read_text(encoding='utf-8')
                compile(source, str(path), 'exec')
                check(f'{rel}:compiles', True)
                outside = stdlib_imports(source, str(path))
                check(f'{rel}:stdlib_imports', not outside, outside)
            except SyntaxError as exc:
                check(f'{rel}:compiles', False, str(exc))
        if path.is_file() and ('__pycache__' in path.parts or path.suffix in {'.pyc', '.lock', '.tmp'}):
            check(f'{rel}:no_cache_or_temp', False)
        if path.is_file():
            check(f'file:{rel}:regular', not path.is_symlink())
            data = path.read_bytes()
            entry = {'path': rel.as_posix(), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
            if path.suffix in TEXT_SUFFIXES:
                entry['words'] = len(data.decode('utf-8').split())
            files.append(entry)
            if path.suffix == '.md':
                text = data.decode('utf-8')
                skill_dir = root / rel.parts[0]
                for index, target in enumerate(LINK.findall(text)):
                    if re.match(r'^[a-z][a-z0-9+.-]*://', target) or target.startswith('mailto:'):
                        continue
                    file_part, _, anchor = target.partition('#')
                    if not file_part:
                        check(f'{rel}:link:{index}', anchor in anchors(text), target)
                        continue
                    dest = (path.parent / file_part).resolve()
                    ok = dest.is_file() and dest.is_relative_to(root)
                    if ok and anchor and dest.suffix == '.md':
                        ok = anchor in anchors(dest.read_text(encoding='utf-8'))
                    check(f'{rel}:link:{index}', ok, target)
                for index, target in enumerate(RESOURCE.findall(text)):
                    candidates = [(skill_dir / target).resolve(), (path.parent / target).resolve()]
                    check(f'{rel}:resource:{index}', any(c.is_file() and c.is_relative_to(skill_dir.resolve())
                                                         for c in candidates), target)
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
