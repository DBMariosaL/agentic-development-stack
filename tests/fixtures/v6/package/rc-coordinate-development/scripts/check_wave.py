"""Read-only wave.json checks; declarations never certify authority or execution."""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

PHASES = {'planning', 'preparing', 'ready', 'launched', 'waiting_children',
          'waiting_quota', 'integrating', 'completed', 'completed_partial',
          'blocked', 'handed_off'}
PRODUCT_PHASES = {'launched', 'integrating', 'completed', 'completed_partial',
                  'handed_off'}
REVIEW_STATUSES = {'done', 'pending', 'not_executed', 'not_required'}
DISPOSED_STATUSES = {'done', 'not_required'}
LIMITS = ('Document declarations only; local hashes are compared with --check-paths. '
          'Cannot certify review quality, real authority, runtime context, scope '
          'feasibility, resources, ownership transfer or execution.')


def text(value):
    return isinstance(value, str) and bool(value.strip())


def digest(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) is not None


def string_list(value):
    return isinstance(value, list) and all(text(item) for item in value)


def local_path(value):
    """Reject absolute/drive paths and lexical escapes on Windows and POSIX."""
    if not text(value) or '\x00' in value or ':' in value:
        return False
    windows = PureWindowsPath(value)
    portable = PurePosixPath(value.replace('\\', '/'))
    if windows.drive or windows.root or portable.is_absolute():
        return False
    depth = 0
    for part in portable.parts:
        depth += -1 if part == '..' else 1
        if depth < 0:
            return False
    return True


def cyclic_groups(graph):
    """Return cyclic strongly connected groups, without deciding a business order."""
    seen, order = set(), []
    for start in graph:
        if start in seen:
            continue
        stack = [(start, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                order.append(node)
            elif node not in seen:
                seen.add(node)
                stack.append((node, True))
                stack.extend((other, False) for other in graph[node] if other not in seen)
    reverse = {node: set() for node in graph}
    for node, edges in graph.items():
        for other in edges:
            reverse[other].add(node)
    seen, groups = set(), []
    for start in reversed(order):
        if start in seen:
            continue
        group, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                group.add(node)
                stack.extend(reverse[node] - seen)
        if len(group) > 1 or start in graph[start]:
            groups.append(group)
    return groups


def validate(doc, directory=None, check_paths=None):
    """Return errors without mutating doc or writing files.

    Passing directory alone retains the original API's existence checks. The CLI
    always supplies its wave directory for containment, and explicitly selects
    whether artifact contents/existence are checked.
    """
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    if not isinstance(doc, dict):
        return ['wave must be an object']
    required = {'schema_version', 'mode', 'project', 'authorization', 'socles',
                'batches', 'artifacts', 'reviews', 'decisions', 'state'}
    require(required.issubset(doc), 'missing required fields: ' +
            ', '.join(sorted(required - set(doc))))
    require(type(doc.get('schema_version')) is int and doc.get('schema_version') == 1,
            'unsupported schema_version')
    mode = doc.get('mode')
    require(isinstance(mode, str) and mode in {'prepare', 'prepare-and-launch'}, 'invalid mode')
    project = doc.get('project')
    if not isinstance(project, dict):
        project = {}
    require({'root', 'baseline', 'observed_at'}.issubset(project), 'invalid project fields')
    for field in ('root', 'baseline', 'observed_at'):
        require(project.get(field) is None or text(project.get(field)), f'project.{field}: text or null required')
    auth = doc.get('authorization')
    if not isinstance(auth, dict):
        auth = {}
    require({'launch', 'source', 'scope', 'exclusions'}.issubset(auth), 'invalid authorization fields')
    require(type(auth.get('launch')) is bool, 'authorization.launch must be boolean')
    require(auth.get('source') is None or text(auth.get('source')), 'authorization.source: text or null required')
    require(auth.get('scope') is None or string_list(auth.get('scope')), 'authorization.scope must be a list of actions/cibles or null')
    require(string_list(auth.get('exclusions')), 'authorization.exclusions must be a list of text')
    state = doc.get('state')
    if not isinstance(state, dict):
        state = {}
    require({'phase', 'owner', 'next_action', 'blockers', 'runtime_refs', 'consumed',
             'launch_ready'}.issubset(state), 'invalid state fields')
    phase = state.get('phase')
    require(isinstance(phase, str) and phase in PHASES, 'invalid phase')
    require(type(state.get('launch_ready')) is bool, 'state.launch_ready must be boolean')
    require(string_list(state.get('blockers')), 'state.blockers must be a list of text')
    require(text(state.get('next_action')), 'state.next_action must be nonempty text')
    require(state.get('runtime_refs') is None or isinstance(state.get('runtime_refs'), list), 'invalid runtime_refs')
    owner = state.get('owner')
    owner_shape = (isinstance(owner, dict) and {'role', 'ref'}.issubset(owner)
                   and text(owner.get('role')) and (owner.get('ref') is None or text(owner.get('ref'))))
    require(owner is None or owner_shape, 'state.owner must be null or {role, ref}')
    known_owner = bool(owner_shape and text(owner.get('ref')))
    product_phase = isinstance(phase, str) and phase in PRODUCT_PHASES
    if mode == 'prepare':
        require(auth.get('launch') is False, 'prepare requires authorization.launch=false')
        require(state.get('launch_ready') is False, 'prepare requires launch_ready=false')
        require(not product_phase, 'prepare mode cannot claim operational execution')
    if product_phase or state.get('launch_ready') is True:
        require(mode == 'prepare-and-launch' and auth.get('launch') is True and text(auth.get('source')),
                'operational state lacks declared launch mode/authorization/source')
        require(known_owner, 'operational state requires state.owner.ref')
        require(string_list(auth.get('scope')) and bool(auth.get('scope')),
                'operational state requires a declared authorization.scope')
    if (mode == 'prepare-and-launch' and isinstance(phase, str)
            and phase in {'waiting_children', 'waiting_quota'}
            and isinstance(state.get('runtime_refs'), list) and state['runtime_refs']):
        require(known_owner, 'operational waiting with runtime_refs requires state.owner.ref')
    decisions = doc.get('decisions')
    require(string_list(decisions), 'decisions must be a list of text')

    socles = doc.get('socles')
    require(isinstance(socles, list), 'socles must be a list')
    socles = socles if isinstance(socles, list) else []
    ids = [s.get('id') for s in socles if isinstance(s, dict) and text(s.get('id'))]
    require(len(ids) == len(socles), 'invalid socle IDs')
    require(len(ids) == len(set(ids)), 'duplicate socle ID')
    by_id = {s['id']: s for s in socles if isinstance(s, dict) and text(s.get('id'))}
    graph = {identifier: set() for identifier in by_id}
    consumption_graph = {identifier: set() for identifier in by_id}
    for identifier, socle in by_id.items():
        require({'id', 'outcome', 'depends_on', 'readiness', 'resources', 'source_refs'}.issubset(socle),
                f'{identifier}: missing fields')
        require(text(socle.get('outcome')), f'{identifier}: outcome must be nonempty text')
        readiness = socle.get('readiness')
        require(isinstance(readiness, str) and readiness in {'ready', 'partial', 'blocked'}, f'{identifier}: invalid readiness')
        for field in ('resources', 'source_refs'):
            require(isinstance(socle.get(field), list), f'{identifier}: {field} must be a list')
        if readiness == 'partial':
            require(text(socle.get('ready_scope')) and text(socle.get('blocked_scope')),
                    f'{identifier}: partial requires ready_scope and blocked_scope')
        deps = socle.get('depends_on')
        valid_deps = string_list(deps) and all(dep in by_id for dep in deps)
        require(valid_deps, f'{identifier}: invalid hard dependencies')
        if valid_deps:
            graph[identifier].update(deps)
        consumption = socle.get('consumption_dependencies', [])
        require(isinstance(consumption, list), f'{identifier}: invalid consumption dependencies')
        for item in consumption if isinstance(consumption, list) else []:
            valid = (isinstance(item, dict) and text(item.get('producer')) and item['producer'] in by_id
                     and all(text(item.get(k)) for k in ('artifact', 'consumer_scope', 'continue_scope')))
            require(valid, f'{identifier}: incomplete consumption dependency')
            if valid:
                require(item['producer'] != identifier, f'{identifier}: self-consumption is invalid')
                consumption_graph[identifier].add(item['producer'])
    require(not cyclic_groups(graph), 'hard dependency cycle')
    for group in cyclic_groups(consumption_graph):
        if len(group) > 1:
            require(all(text(by_id[node].get('ready_scope')) for node in group)
                    and string_list(decisions) and bool(decisions),
                    'consumption cycle requires explicit ready_scope for each participant and a bootstrap decision: '
                    + ', '.join(sorted(group)))

    batches = doc.get('batches')
    require(isinstance(batches, list), 'batches must be a list')
    seen = set()
    for batch in batches if isinstance(batches, list) else []:
        if not string_list(batch):
            require(False, 'batch must contain string IDs')
            continue
        require(all(identifier in by_id for identifier in batch), 'unknown batch ID')
        require(len(batch) == len(set(batch)) and not seen.intersection(batch), 'duplicate batch ID')
        for identifier in batch:
            require(all(dep in seen for dep in graph.get(identifier, [])), f'{identifier}: hard dependency not admitted earlier')
        seen.update(batch)

    artifacts = doc.get('artifacts')
    require(isinstance(artifacts, dict), 'artifacts must be an object')
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    consumed = state.get('consumed')
    require(isinstance(consumed, dict), 'state.consumed must be an object')
    consumed = consumed if isinstance(consumed, dict) else {}
    if product_phase or state.get('launch_ready') is True:
        require(bool(consumed), 'operational state requires nonempty consumed mandates')
    for name, entry in consumed.items():
        require(name in artifacts, f'{name}: consumed artifact is unknown')
        require(isinstance(entry, dict) and text(entry.get('version')) and digest(entry.get('sha256')),
                f'{name}: consumed version and sha256 required')
    reviews = doc.get('reviews')
    require(isinstance(reviews, list), 'reviews must be a list')
    reviews = reviews if isinstance(reviews, list) else []
    valid_reviews = []
    for index, review in enumerate(reviews):
        label = f'reviews[{index}]'
        if not isinstance(review, dict):
            require(False, label + ': review must be an object')
            continue
        name, status = review.get('artifact'), review.get('status')
        require({'artifact', 'sha256', 'status', 'disposition', 'reference'}.issubset(review), label + ': missing fields')
        require(text(name) and name in artifacts, label + ': unknown artifact')
        require(digest(review.get('sha256')), label + ': sha256 required')
        require(isinstance(status, str) and status in REVIEW_STATUSES, label + ': invalid status')
        for field in ('disposition', 'reference'):
            require(review.get(field) is None or text(review.get(field)), f'{label}: {field} must be text or null')
        if isinstance(status, str) and status in DISPOSED_STATUSES:
            require(text(review.get('disposition')) and text(review.get('reference')),
                    label + ': disposed review requires disposition and reference')
        if text(name) and name in artifacts and digest(review.get('sha256')):
            valid_reviews.append(review)

    if state.get('launch_ready') is True:
        require(all(text(project.get(field)) for field in ('root', 'baseline', 'observed_at')),
                'launch_ready requires declared project context: root, baseline, observed_at')
        require(state.get('blockers') == [], 'launch_ready requires no blockers')
        admitted = [by_id[identifier] for identifier in seen if identifier in by_id]
        require(any(s.get('readiness') in ('ready', 'partial') for s in admitted),
                'launch_ready requires an executable admitted scope (ready or scoped partial)')
        if 'supervisor' in artifacts:
            require('supervisor' in consumed, 'launch_ready requires consumed declared supervisor')
        for socle in admitted:
            if socle.get('readiness') == 'blocked':
                continue
            name = socle.get('prompt_artifact')
            known_prompt = text(name) and name in artifacts
            require(known_prompt, f"{socle['id']}: admitted socle requires prompt_artifact key in artifacts")
            if known_prompt:
                require(name in consumed, f"{socle['id']}: admitted prompt_artifact must be consumed")
        for name, entry in consumed.items():
            if not isinstance(entry, dict) or not digest(entry.get('sha256')):
                continue
            matching = [r for r in valid_reviews if r['artifact'] == name
                        and r['sha256'].lower() == entry['sha256'].lower()]
            require(bool(matching) and all(isinstance(r.get('status'), str)
                    and r['status'] in DISPOSED_STATUSES for r in matching),
                    f'{name}: launch_ready requires disposed reviews on the consumed sha256')

    if check_paths is None:
        check_paths = directory is not None
    root = None
    if directory is not None:
        try:
            root = Path(directory).resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            require(False, 'invalid wave directory: ' + str(exc))
    for name, relative in artifacts.items():
        safe = local_path(relative)
        require(safe, f'{name}: local relative artifact path required (no escape)')
        if not safe or root is None:
            continue
        try:
            target = (root / relative.replace('\\', '/')).resolve()
            if root not in target.parents:
                require(False, f'{name}: artifact path escapes wave directory')
                continue
            if not check_paths:
                continue
            if not target.is_file():
                require(False, f'{name}: artifact not found')
                continue
            expected = []
            entry = consumed.get(name)
            if isinstance(entry, dict) and digest(entry.get('sha256')):
                expected.append(('consumed', entry['sha256']))
                expected.extend(('review', r['sha256']) for r in valid_reviews
                                if r['artifact'] == name and r['sha256'].lower() == entry['sha256'].lower())
            if expected:
                hasher = hashlib.sha256()
                with target.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(65536), b''):
                        hasher.update(chunk)
                actual = hasher.hexdigest()
                for origin, sha256 in expected:
                    require(actual == sha256.lower(), f'{name}: {origin} sha256 mismatch with local artifact')
        except (OSError, ValueError, RuntimeError) as exc:
            require(False, f'{name}: artifact path/read error: {exc}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wave', type=Path)
    parser.add_argument('--check-paths', action='store_true',
                        help='Check local artifact existence and consumed SHA-256 hashes (read only)')
    args = parser.parse_args()
    try:
        doc = json.loads(args.wave.read_text(encoding='utf-8-sig'))
        errors = validate(doc, args.wave.parent, check_paths=args.check_paths)
    except (ValueError, OSError, RuntimeError) as exc:
        errors = [str(exc)]
    print(json.dumps({'valid': not errors, 'errors': errors, 'limits': LIMITS}))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
