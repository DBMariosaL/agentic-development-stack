"""Deterministic state tool for Radio Chantier programs and waves (stdlib only).

Commands validate, compute ready work, migrate formats, and perform guarded writes
(owner + expected revision + locks + full validation + atomic replace + journal).
Declarations are checked, never certified: the tool cannot prove authority,
review quality, runtime delivery or execution.
"""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave caches inside an installed skill
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('rc_check_wave_v1', HERE / 'check_wave.py')
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)

PROGRAM_SCHEMA = 'rc-program/1'
WAVE_V2_PHASES = v1.PHASES | {'waiting_human', 'waiting_runtime', 'failed', 'stopped'}
WAITING_PHASES = {'waiting_children', 'waiting_quota', 'waiting_runtime', 'waiting_human'}
WAITLIKE = WAITING_PHASES | {'blocked'}
TERMINAL_PHASES = {'completed', 'completed_partial', 'failed', 'stopped'}
ACTIVE_FROM_WAIT = {'preparing', 'launched', 'integrating'}
TRANSITIONS = {
    'planning': {'preparing', 'blocked', 'stopped'},
    'preparing': {'ready', 'waiting_children', 'waiting_quota', 'blocked', 'stopped'},
    'ready': {'preparing', 'launched', 'stopped'},
    'launched': {'integrating', 'waiting_children', 'waiting_quota', 'waiting_runtime',
                 'waiting_human', 'blocked', 'completed', 'completed_partial', 'failed',
                 'stopped', 'handed_off'},
    'handed_off': {'launched', 'integrating'},
}
TRANSITIONS['integrating'] = (TRANSITIONS['launched'] - {'integrating'}) | {'launched'}
for _wait in WAITLIKE:
    TRANSITIONS[_wait] = (ACTIVE_FROM_WAIT | WAITLIKE | {'failed', 'stopped'}) - {_wait}
ACTOR_STATUSES = {'running', 'waiting', 'completed', 'failed', 'cancelled', 'interrupted', 'unknown'}
LIVE_ACTOR = {'running', 'waiting', 'unknown'}
INTENT_OPS = {'launch', 'send', 'write', 'promote'}
INTENT_STATUSES = {'pending', 'confirmed', 'absent', 'failed'}
OUTCOME_STATUSES = {'pending', 'admitted', 'accepted', 'accepted_partial', 'failed', 'abandoned', 'blocked'}
CLOSED_OUTCOMES = {'accepted', 'accepted_partial', 'abandoned'}
PROGRAM_STATUSES = {'active', 'waiting_human', 'waiting_quota', 'waiting_runtime', 'stopped', 'completed'}
WAIT_KINDS = {'human', 'quota', 'runtime', 'dependency', 'resource'}
WAVE_WAIT_KINDS = WAIT_KINDS | {'children'}
MANAGED_PATHS = ('owner', 'revision', 'schema', 'schema_version', 'migrated_from', 'state.owner')
LAUNCH_CONTEXT = ('project', 'authorization', 'socles', 'batches', 'artifacts', 'reviews', 'candidate')
LIMITS = ('Checks declarations, revisions and local files only. Cannot certify authority, '
          'review quality, runtime delivery, idempotence of runtime calls or execution.')

text, digest, string_list, local_path = v1.text, v1.digest, v1.string_list, v1.local_path


def member(value, options):
    return isinstance(value, str) and value in options


def sval(mapping, key):
    """String field or None, so malformed values never reach set/dict membership."""
    value = mapping.get(key) if isinstance(mapping, dict) else None
    return value if isinstance(value, str) else None


def relative_ref(value):
    """Relative path that may climb to a parent program directory; no drive, root or NUL."""
    if not text(value) or '\x00' in value or ':' in value:
        return False
    return not (value.startswith('/') or value.startswith('\\'))


class StateError(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kind_of(doc):
    if isinstance(doc, dict) and doc.get('schema') == PROGRAM_SCHEMA:
        return 'program'
    if isinstance(doc, dict) and doc.get('schema_version') == 2 and type(doc.get('schema_version')) is int:
        return 'wave2'
    if isinstance(doc, dict) and doc.get('schema_version') == 1 and type(doc.get('schema_version')) is int:
        return 'wave1'
    return 'unknown'


def _items(value):
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


# ---------------------------------------------------------------- wave v2

def _wait_shape(value):
    return (isinstance(value, dict) and member(value.get('kind'), WAVE_WAIT_KINDS)
            and all(text(value.get(k)) for k in ('detail', 'trigger', 'resume'))
            and 'from' in value and (value['from'] is None or member(value['from'], ACTIVE_FROM_WAIT)))


def _program_back_reference(wave_path, program_path):
    """True when program_path is a program whose outcomes reference wave_path."""
    try:
        program = load(program_path)
    except (OSError, ValueError):
        return False
    if kind_of(program) != 'program':
        return False
    for outcome in _items(program.get('outcomes')):
        ref = outcome.get('state_ref')
        if text(ref) and local_path(ref) and (program_path.parent / ref).resolve() == wave_path:
            return True
    return False


def validate_wave2(doc, directory=None, check_paths=False, self_path=None):
    errors = []

    def require(cond, msg):
        if not cond:
            errors.append(msg)

    if not isinstance(doc, dict):
        return ['wave must be an object']
    state = doc.get('state') if isinstance(doc.get('state'), dict) else {}
    phase = sval(state, 'phase')
    require(member(phase, WAVE_V2_PHASES), 'invalid phase')
    actors = _items(doc.get('actors'))
    # Shared v1 field rules: project v2 onto the frozen v1 validator.
    projected = copy.deepcopy(doc)
    projected['schema_version'] = 1
    if isinstance(projected.get('state'), dict):
        pstate = projected['state']
        pstate['runtime_refs'] = [a.get('ref') for a in actors] or None
        if phase in {'waiting_human', 'waiting_runtime'}:
            pstate['phase'] = 'waiting_children'
        elif phase in {'failed', 'stopped'}:
            pstate['phase'] = 'blocked'
    for message in v1.validate(projected, directory, check_paths=check_paths):
        errors.append('v1-fields: ' + message)

    require(kind_of(doc) == 'wave2', 'schema_version must be the integer 2')
    require(type(doc.get('revision')) is int and doc['revision'] >= 0, 'revision must be a non-negative integer')
    artifacts = doc.get('artifacts') if isinstance(doc.get('artifacts'), dict) else {}
    ref = doc.get('program_ref')
    require(ref is None or relative_ref(ref), 'program_ref must be null or a relative path')
    if relative_ref(ref) and self_path is not None:
        target = (Path(self_path).resolve().parent / ref).resolve()
        require(target.is_file() and _program_back_reference(Path(self_path).resolve(), target),
                'program_ref must resolve to an existing program whose outcomes reference this wave')
    cand = doc.get('candidate')
    cand_ok = cand is None or (isinstance(cand, dict) and type(cand.get('seq')) is int and cand['seq'] >= 1
                               and text(cand.get('ref')) and member(cand.get('artifact'), set(artifacts))
                               and digest(cand.get('sha256')))
    require(cand_ok, 'candidate must be null or {seq>=1, ref, artifact (key in artifacts), sha256}')
    if cand_ok and isinstance(cand, dict) and check_paths and directory is not None:
        target = (Path(directory) / str(artifacts[cand['artifact']]).replace('\\', '/')).resolve()
        require(target.is_file() and sha256_file(target) == cand['sha256'].lower(),
                'candidate artifact missing or sha256 mismatch with local file')
    env = doc.get('envelope')
    require(env is None or (isinstance(env, dict) and text(env.get('reason'))), 'envelope must be null or carry a reason')
    require(isinstance(doc.get('actors'), list) and len(actors) == len(doc['actors']), 'actors must be a list of objects')
    for index, actor in enumerate(actors):
        require(text(actor.get('role')) and text(actor.get('correlation')) and member(sval(actor, 'status'), ACTOR_STATUSES)
                and (actor.get('ref') is None or text(actor.get('ref')))
                and (actor.get('target') is None or text(actor.get('target'))),
                f'actors[{index}]: role, correlation, status, ref(text|null), target(text|null) required')
    correlations = [a.get('correlation') for a in actors if text(a.get('correlation'))]
    require(len(correlations) == len(set(correlations)), 'duplicate actor correlation')
    intents = _items(doc.get('intents'))
    require(isinstance(doc.get('intents'), list) and len(intents) == len(doc['intents']), 'intents must be a list of objects')
    seen, pending_targets = set(), set()
    for index, intent in enumerate(intents):
        label = f'intents[{index}]'
        ok = (text(intent.get('correlation')) and member(intent.get('op'), INTENT_OPS)
              and text(intent.get('target')) and member(sval(intent, 'status'), INTENT_STATUSES))
        require(ok, label + ': correlation, op, target, status required')
        if not ok:
            continue
        require(intent['correlation'] not in seen, label + ': duplicate correlation')
        seen.add(intent['correlation'])
        if intent['status'] == 'confirmed':
            require(text(intent.get('result_ref')), label + ': confirmed intent requires result_ref')
        if intent['status'] == 'pending':
            key = (intent['op'], intent['target'])
            require(key not in pending_targets, label + ': second pending intent for the same op/target')
            pending_targets.add(key)
    reviews = _items(doc.get('reviews'))
    for review in reviews:
        if 'candidate_seq' in review:
            require(type(review['candidate_seq']) is int, 'review candidate_seq must be an integer')
    if member(phase, WAITLIKE):
        require(_wait_shape(state.get('waiting')),
                f'{phase} requires state.waiting {{kind, detail, trigger, resume, from}}')
    if member(phase, TERMINAL_PHASES):
        live = [a.get('correlation') for a in actors if sval(a, 'status') in {'running', 'waiting'}]
        require(not live, f'{phase} with live actors: ' + ', '.join(map(str, live)))
        pending = [i.get('correlation') for i in intents if sval(i, 'status') == 'pending']
        require(not pending, f'{phase} with unresolved intents: ' + ', '.join(map(str, pending)))
    if phase in {'completed', 'completed_partial'}:
        require(isinstance(cand, dict), f'{phase} requires a frozen candidate')
        if cand_ok and isinstance(cand, dict):
            covering = [r for r in reviews if r.get('candidate_seq') == cand['seq'] and r.get('artifact') == cand['artifact']
                        and isinstance(r.get('sha256'), str) and r['sha256'].lower() == cand['sha256'].lower()]
            require(bool(covering) and all(member(sval(r, 'status'), v1.DISPOSED_STATUSES) for r in covering),
                    f'{phase} requires disposed reviews of candidate artifact {cand["artifact"]} '
                    f'with its sha256 on candidate_seq {cand["seq"]}')
        require(not any(sval(a, 'status') == 'unknown' for a in actors),
                f'{phase} requires reconciled actors (no unknown status)')
    if phase == 'failed':
        require(any(text(d) for d in doc.get('decisions', []) if isinstance(d, str)) if isinstance(doc.get('decisions'), list) else False,
                'failed requires a recorded cause and resumption condition in decisions')
    return errors


# ---------------------------------------------------------------- program

def _suspended(doc):
    out = set()
    for dec in _items(doc.get('decisions_pending')):
        if string_list(dec.get('suspends')):
            out.update(dec['suspends'])
    return out


def ready_view(doc):
    outcomes = [o for o in _items(doc.get('outcomes')) if text(o.get('id'))]
    by_id = {o['id']: o for o in outcomes}
    suspended = _suspended(doc)
    ready, admitted, waiting, blocked = [], [], {}, []
    for o in outcomes:
        status = sval(o, 'status')
        if status == 'admitted':
            admitted.append(o['id'])
        elif status == 'blocked':
            blocked.append(o['id'])
        if o.get('waiting_on'):
            waiting[o['id']] = o['waiting_on'].get('kind') if isinstance(o['waiting_on'], dict) else 'invalid'
        deps = o.get('depends_on') if string_list(o.get('depends_on')) else []
        if (status == 'pending' and not o.get('waiting_on') and o['id'] not in suspended
                and all(by_id.get(dep, {}).get('status') == 'accepted' for dep in deps)):
            ready.append(o['id'])

    def res(oid):
        values = by_id[oid].get('resources')
        return {r for r in values if isinstance(r, str)} if isinstance(values, list) else set()

    conflicts = []
    for i, a in enumerate(ready):
        for b in ready[i + 1:]:
            if res(a) & res(b):
                conflicts.append({'kind': 'ready-ready', 'outcomes': [a, b], 'resources': sorted(res(a) & res(b))})
        for holder in admitted:
            if res(a) & res(holder):
                conflicts.append({'kind': 'ready-admitted', 'outcomes': [a, holder], 'resources': sorted(res(a) & res(holder))})
    return {'ready': ready, 'admitted': admitted, 'waiting': waiting, 'blocked': blocked,
            'resource_conflicts': conflicts,
            'note': 'Declared resources only; reserve real resources yourself. Do not use this view while consistency errors exist.'}


def validate_program(doc, directory=None, check_paths=False, self_path=None):
    errors = []

    def require(cond, msg):
        if not cond:
            errors.append(msg)

    if not isinstance(doc, dict):
        return ['program must be an object']
    require(doc.get('schema') == PROGRAM_SCHEMA, 'schema must be ' + PROGRAM_SCHEMA)
    require(type(doc.get('revision')) is int and doc['revision'] >= 0, 'revision must be a non-negative integer')
    owner = doc.get('owner')
    require(owner is None or (isinstance(owner, dict) and text(owner.get('role')) and text(owner.get('ref'))),
            'owner must be null or {role, ref}')
    mandate = doc.get('mandate')
    require(isinstance(mandate, dict) and text(mandate.get('ref')) and string_list(mandate.get('scope'))
            and string_list(mandate.get('exclusions')) and text(mandate.get('end_criteria')),
            'mandate requires ref, scope, exclusions, end_criteria')
    skills = doc.get('skills_consumed')
    require(isinstance(skills, list) and all(isinstance(s, dict) and text(s.get('name')) and digest(s.get('sha256'))
                                             for s in skills), 'skills_consumed must list {name, sha256}')
    status = sval(doc, 'status')
    require(member(status, PROGRAM_STATUSES), 'invalid program status')
    require(text(doc.get('status_reason')), 'status_reason required')
    raw_outcomes = doc.get('outcomes')
    outcomes = _items(raw_outcomes)
    require(isinstance(raw_outcomes, list) and outcomes and len(outcomes) == len(raw_outcomes),
            'outcomes must be a nonempty list of objects')
    ids = [o.get('id') for o in outcomes]
    require(all(text(i) for i in ids), 'invalid outcome IDs')
    ids = [i for i in ids if text(i)]
    require(len(ids) == len(set(ids)), 'duplicate outcome ID')
    by_id = {o['id']: o for o in outcomes if text(o.get('id'))}
    graph = {i: set() for i in by_id}
    raw_decisions = doc.get('decisions_pending')
    decisions = _items(raw_decisions)
    require(isinstance(raw_decisions, list) and len(decisions) == len(raw_decisions), 'decisions_pending must be a list of objects')
    for index, dec in enumerate(decisions):
        ok = (all(text(dec.get(k)) for k in ('id', 'question', 'option', 'effects'))
              and string_list(dec.get('suspends')) and dec.get('suspends') and all(s in by_id for s in dec['suspends']))
        require(ok, f'decisions_pending[{index}]: id, question, concrete option, effects and known suspends required')
    suspended = _suspended(doc)
    base = Path(directory).resolve() if directory is not None else None
    program_path = Path(self_path).resolve() if self_path is not None else None
    for oid, o in by_id.items():
        st = sval(o, 'status')
        require(member(st, OUTCOME_STATUSES), f'{oid}: invalid status')
        require(text(o.get('outcome')) and text(o.get('next_action')), f'{oid}: outcome and next_action required')
        deps = o.get('depends_on')
        valid_deps = string_list(deps) and all(d in by_id for d in deps)
        require(valid_deps, f'{oid}: invalid depends_on')
        deps = deps if valid_deps else []
        graph[oid].update(deps)
        require(isinstance(o.get('resources'), list), f'{oid}: resources must be a list')
        ref = o.get('state_ref')
        require(ref is None or local_path(ref), f'{oid}: state_ref must be null or a local relative path')
        if st == 'admitted':
            require(text(ref), f'{oid}: admitted requires state_ref')
        if st in {'admitted', 'accepted', 'accepted_partial'}:
            for dep in deps:
                require(sval(by_id[dep], 'status') == 'accepted', f'{oid}: {st} while dependency {dep} is not accepted')
        if st in {'accepted_partial', 'abandoned', 'failed'}:
            closure = o.get('closure')
            require(isinstance(closure, dict) and text(closure.get('source')) and text(closure.get('remaining')),
                    f'{oid}: {st} requires closure {{source, remaining}}')
        wait = o.get('waiting_on')
        wait_ok = wait is None or (isinstance(wait, dict) and member(wait.get('kind'), WAIT_KINDS)
                                   and text(wait.get('detail')) and text(wait.get('trigger')))
        require(wait_ok, f'{oid}: waiting_on must be null or {{kind, detail, trigger}}')
        is_human = isinstance(wait, dict) and wait.get('kind') == 'human'
        if is_human:
            require(oid in suspended, f'{oid}: human wait requires a pending decision that suspends it')
        if oid in suspended:
            require(is_human, f'{oid}: suspended by a pending decision but waiting_on is not human')
        if st in CLOSED_OUTCOMES:
            require(wait is None, f'{oid}: closed outcome cannot wait')
        if base is not None and text(ref) and local_path(ref):
            target = (base / ref.replace('\\', '/')).resolve()
            if not (target.is_file() and base in target.parents):
                require(False, f'{oid}: state_ref not found inside program directory')
                continue
            try:
                wave = load(target)
            except (OSError, ValueError) as exc:
                require(False, f'{oid}: state_ref unreadable: {exc}')
                continue
            wkind = kind_of(wave)
            if wkind == 'wave2':
                werrors = validate_wave2(wave, target.parent, check_paths, self_path=target if program_path else None)
            elif wkind == 'wave1':
                werrors = v1.validate(wave, target.parent, check_paths=check_paths)
            else:
                werrors = ['unknown wave schema']
            for message in werrors:
                errors.append(f'{oid}: wave: {message}')
            wstate = wave.get('state') if isinstance(wave, dict) and isinstance(wave.get('state'), dict) else {}
            wphase = sval(wstate, 'phase')
            if st == 'admitted' and member(wphase, TERMINAL_PHASES):
                require(False, f'{oid}: contradictory state: outcome admitted but wave is {wphase}')
            if st in {'accepted', 'accepted_partial'} and wphase not in {'completed', 'completed_partial'}:
                require(False, f'{oid}: contradictory state: outcome {st} but wave is {wphase}')
            if st == 'accepted' and wphase == 'completed_partial':
                require(False, f'{oid}: contradictory state: wave partial but outcome fully accepted')
    require(not v1.cyclic_groups(graph), 'outcome dependency cycle')
    view = ready_view(doc)
    for oid in suspended & set(by_id):
        require(sval(by_id[oid], 'status') not in CLOSED_OUTCOMES, f'{oid}: decision suspends a closed outcome')
    if member(status, {'waiting_human', 'waiting_quota', 'waiting_runtime'}):
        require(not view['ready'], f'{status} while outcomes are ready: ' + ', '.join(view['ready']))
        unwaited = [o for o in view['admitted'] if not by_id[o].get('waiting_on')]
        require(not unwaited, f'{status} while admitted outcomes are not waiting: ' + ', '.join(unwaited))
    if status == 'waiting_human':
        require(bool(decisions), 'waiting_human requires decisions_pending')
    if status == 'completed':
        open_ = [o for o, v in by_id.items() if sval(v, 'status') not in CLOSED_OUTCOMES]
        require(not open_, 'completed with open outcomes: ' + ', '.join(open_))
        require(not decisions, 'completed with pending decisions')
    if status == 'active':
        moving = view['ready'] or [o for o in view['admitted'] if not by_id[o].get('waiting_on')]
        require(bool(moving), 'active without ready or unwaited admitted outcomes: declare a waiting status, stopped or completed')
    milestone = doc.get('last_milestone')
    require(milestone is None or (isinstance(milestone, dict) and all(text(milestone.get(k)) for k in ('at', 'summary', 'ref'))),
            'last_milestone must be null or {at, summary, ref}')
    return errors


def validate_any(doc, directory=None, check_paths=False, self_path=None):
    k = kind_of(doc)
    if k == 'program':
        return validate_program(doc, directory, check_paths, self_path)
    if k == 'wave2':
        return validate_wave2(doc, directory, check_paths, self_path)
    if k == 'wave1':
        return v1.validate(doc, directory, check_paths=check_paths)
    return ['unknown document schema']


# ---------------------------------------------------------------- guarded writes

def _get(doc, path):
    node = doc
    for part in path.split('.'):
        if not isinstance(node, dict) or part not in node:
            raise StateError(f'path not found: {path}')
        node = node[part]
    return node


def _set(doc, path, value):
    parts = path.split('.')
    node = doc
    for part in parts[:-1]:
        if not isinstance(node, dict) or not isinstance(node.get(part), dict):
            raise StateError(f'path not found: {path}')
        node = node[part]
    node[parts[-1]] = value


def apply_ops(doc, ops):
    """Apply set/append/update operations; owner, revision and schema are tool-managed."""
    result = copy.deepcopy(doc)
    if not isinstance(ops, list) or not ops:
        raise StateError('ops must be a nonempty list')
    for op in ops:
        if not isinstance(op, dict) or not member(op.get('op'), {'set', 'append', 'update'}) or not text(op.get('path')):
            raise StateError(f'invalid op: {op!r}')
        path = op['path']
        for managed in MANAGED_PATHS:
            if path == managed or path.startswith(managed + '.'):
                raise StateError(f'{path} is managed by claim/migrate, not by ops')
        if op['op'] == 'set':
            _set(result, path, copy.deepcopy(op.get('value')))
        elif op['op'] == 'append':
            target = _get(result, path)
            if not isinstance(target, list):
                raise StateError(f'{path} is not a list')
            target.append(copy.deepcopy(op.get('value')))
        else:
            target = _get(result, path)
            match = op.get('match')
            if not isinstance(target, list) or not isinstance(match, dict) or not match:
                raise StateError(f'update needs a list path and a nonempty match: {path}')
            hits = [item for item in target if isinstance(item, dict) and all(item.get(k) == v for k, v in match.items())]
            if len(hits) != 1:
                raise StateError(f'update on {path} must match exactly one item, matched {len(hits)}')
            if not isinstance(op.get('value'), dict):
                raise StateError('update value must be an object')
            hits[0].update(copy.deepcopy(op['value']))
    return result


def _owner_of(doc):
    if kind_of(doc) == 'program':
        return doc.get('owner')
    return (doc.get('state') or {}).get('owner') if isinstance(doc.get('state'), dict) else None


def check_evolution(old, new, owner_change=False):
    """Invariants between two versions of the same document."""
    errors = []
    k = kind_of(old)
    if kind_of(new) != k:
        return ['document kind changed']
    for field in ('schema', 'schema_version', 'migrated_from'):
        if old.get(field) != new.get(field):
            errors.append(f'{field} is immutable')
    if not owner_change and _owner_of(old) != _owner_of(new):
        errors.append('owner changes only through claim')
    if k == 'wave2':
        ostate, nstate = old.get('state') or {}, new.get('state') or {}
        po, pn = sval(ostate, 'phase'), sval(nstate, 'phase')
        if po in TERMINAL_PHASES:
            errors.append(f'wave is terminal ({po}); record late signals with event, start a new wave to resume')
        elif pn != po and pn not in TRANSITIONS.get(po, set()):
            errors.append(f'transition {po} -> {pn} not allowed')
        origin = (ostate.get('waiting') or {}).get('from') if po in WAITLIKE else None
        if po in WAITLIKE and pn in WAITLIKE and origin is not None and (nstate.get('waiting') or {}).get('from') != origin:
            errors.append(f'waiting origin {origin} cannot be changed while waiting')
        if po in WAITLIKE and pn in ACTIVE_FROM_WAIT and origin is not None and origin != pn:
            errors.append(f'wait was entered from {origin}; resume to {origin}, not {pn}')
        if old.get('program_ref') is not None and new.get('program_ref') != old.get('program_ref'):
            errors.append('program_ref is immutable once set')
        if ostate.get('launch_ready') is True and nstate.get('launch_ready') is True:
            changed = [f for f in LAUNCH_CONTEXT if old.get(f) != new.get(f)]
            if ostate.get('consumed') != nstate.get('consumed'):
                changed.append('state.consumed')
            if changed:
                errors.append('launch_ready must be reset to false when launch context changes: ' + ', '.join(changed))
        oi = {i['correlation']: i for i in _items(old.get('intents')) if text(i.get('correlation'))}
        ni = {i['correlation']: i for i in _items(new.get('intents')) if text(i.get('correlation'))}
        for corr, intent in oi.items():
            if corr not in ni:
                errors.append(f'intent {corr} removed')
                continue
            if sval(intent, 'status') != 'pending' and ni[corr] != intent:
                errors.append(f'intent {corr} is resolved and immutable')
            for field in ('op', 'target'):
                if ni[corr].get(field) != intent.get(field):
                    errors.append(f'intent {corr}: {field} is immutable')
        for corr, intent in ni.items():
            if corr not in oi and sval(intent, 'status') != 'pending':
                errors.append(f'intent {corr} must be created pending, before the runtime call')
        oa = {a['correlation']: a for a in _items(old.get('actors')) if text(a.get('correlation'))}
        na = {a['correlation']: a for a in _items(new.get('actors')) if text(a.get('correlation'))}
        for corr, actor in oa.items():
            if corr not in na:
                errors.append(f'actor {corr} removed (keep actors; mark their status)')
                continue
            for field in ('ref', 'target'):
                if actor.get(field) and na[corr].get(field) != actor.get(field):
                    errors.append(f'actor {corr}: known {field} is immutable')
        for corr in set(na) - set(oa):
            linked = ni.get(corr)
            if not linked or sval(linked, 'status') != 'confirmed' or linked.get('op') != 'launch':
                errors.append(f'actor {corr} needs a confirmed launch intent with the same correlation')
        oc, nc = old.get('candidate'), new.get('candidate')
        if isinstance(oc, dict):
            if not isinstance(nc, dict) or not isinstance(nc.get('seq'), int) or nc['seq'] < oc.get('seq', 0):
                errors.append('candidate seq cannot decrease or disappear')
            elif nc.get('seq') == oc.get('seq') and nc != oc:
                errors.append('a frozen candidate is immutable; freeze a new seq')
    elif k == 'program':
        oo = {o['id']: o for o in _items(old.get('outcomes')) if text(o.get('id'))}
        no = {o['id']: o for o in _items(new.get('outcomes')) if text(o.get('id'))}
        for oid, o in oo.items():
            if oid not in no:
                errors.append(f'outcome {oid} removed (close it with abandoned and a source)')
            elif sval(o, 'status') in CLOSED_OUTCOMES and sval(no[oid], 'status') != sval(o, 'status'):
                errors.append(f'outcome {oid} is closed ({o.get("status")})')
        if sval(old, 'status') in {'completed', 'stopped'} and sval(new, 'status') != sval(old, 'status'):
            errors.append(f'program is {old.get("status")}; a new mandate starts a new program')
    return errors


class Lock:
    def __init__(self, path):
        self.path = Path(str(path) + '.lock')
        self.fd = None

    def __enter__(self):
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise StateError(f'lock present: {self.path}. Another writer may be active; '
                             'verify no write is in progress before removing it')
        os.write(self.fd, json.dumps({'pid': os.getpid(), 'at': now()}).encode())
        return self

    def __exit__(self, *exc):
        os.close(self.fd)
        os.unlink(self.path)


def journal_path(path, doc):
    path = Path(path).resolve()
    if kind_of(doc) == 'wave2' and relative_ref(doc.get('program_ref')):
        return (path.parent / doc['program_ref']).resolve().parent / 'journal.jsonl'
    return path.parent / 'journal.jsonl'


def append_journal(jpath, entry):
    with open(jpath, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def read_journal(jpath):
    if not Path(jpath).is_file():
        return []
    return [json.loads(line) for line in Path(jpath).read_text(encoding='utf-8').splitlines() if line.strip()]


def guarded_write(path, actor, expected_revision, mutate, kind='write', detail=None, owner_check=True,
                  owner_change=False, applies_event=None):
    path = Path(path).resolve()
    with Lock(path):
        old = load(path)
        if kind_of(old) not in {'program', 'wave2'}:
            raise StateError('guarded writes need a program or a v2 wave; migrate v1 first')
        if old.get('revision') != expected_revision:
            raise StateError(f'revision conflict: expected {expected_revision}, found {old.get("revision")}; '
                             're-read and reconcile before retrying')
        owner = (_owner_of(old) or {}).get('ref')
        if owner_check and owner is None:
            raise StateError('no owner recorded: claim ownership first')
        if owner_check and owner != actor:
            raise StateError(f'actor {actor} is not the owner ({owner}); hand the need to the owner')
        new = mutate(copy.deepcopy(old))
        new['revision'] = old['revision'] + 1
        errors = validate_any(new, path.parent, check_paths=False, self_path=path)
        if not errors:
            errors = check_evolution(old, new, owner_change=owner_change)
        if errors:
            raise StateError('refused: ' + '; '.join(errors))
        jpath = journal_path(path, new)
        with Lock(jpath):  # both locks are held before the commit
            if applies_event is not None:
                entries = read_journal(jpath)
                if not any(e.get('id') == applies_event and e.get('kind', '').startswith('event:') for e in entries):
                    raise StateError(f'event {applies_event} was never received; record it with event first')
                if any(e.get('applies_event') == applies_event for e in entries):
                    raise StateError(f'event {applies_event} is already applied')
            tmp = path.with_name(path.name + '.tmp')
            with open(tmp, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(new, ensure_ascii=False, indent=2) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
            try:
                append_journal(jpath, {'id': f'write:{path.name}:{new["revision"]}', 'at': now(), 'kind': kind,
                                       'file': path.name, 'actor': actor, 'revision': new['revision'],
                                       'detail': detail, 'applies_event': applies_event})
            except OSError as exc:
                raise StateError(f'state committed at revision {new["revision"]} but journal append failed: {exc}; '
                                 'record the write before any other action')
        return {'written': str(path), 'revision': new['revision']}


# ---------------------------------------------------------------- commands

def cmd_check(args):
    path = Path(args.file).resolve()
    doc = load(path)
    errors = validate_any(doc, path.parent, args.check_paths, self_path=path)
    return {'valid': not errors, 'kind': kind_of(doc), 'errors': errors, 'limits': LIMITS}, bool(errors)


def cmd_ready(args):
    path = Path(args.program).resolve()
    doc = load(path)
    if kind_of(doc) != 'program':
        raise StateError('ready needs a program.json')
    errors = validate_program(doc, path.parent, self_path=path)
    return dict(ready_view(doc), consistency_errors=errors), bool(errors)


def _event_status(entries):
    """Map event id -> {'received': entry, 'applied': bool}."""
    status = {}
    for e in entries:
        if e.get('kind', '').startswith('event:'):
            status.setdefault(e['id'], {'received': e, 'applied': e.get('classification') in {'stale', 'late'}})
        if e.get('applies_event') in status:
            status[e['applies_event']]['applied'] = True
    return status


def cmd_resume(args):
    program_path = Path(args.program).resolve()
    doc = load(program_path)
    if kind_of(doc) != 'program':
        raise StateError('resume needs a program.json')
    errors = validate_program(doc, program_path.parent, self_path=program_path)
    actions, waves = [], []
    for o in _items(doc.get('outcomes')):
        ref = o.get('state_ref')
        if not (text(ref) and local_path(ref)):
            continue
        target = (program_path.parent / ref).resolve()
        if not target.is_file():
            continue
        wave = load(target)
        state = wave.get('state') if isinstance(wave.get('state'), dict) else {}
        pending = [i for i in _items(wave.get('intents')) if sval(i, 'status') == 'pending']
        live = [a for a in _items(wave.get('actors')) if sval(a, 'status') in LIVE_ACTOR]
        waves.append({'outcome': o.get('id'), 'wave': ref, 'schema_version': wave.get('schema_version'),
                      'phase': sval(state, 'phase'), 'revision': wave.get('revision'), 'owner': state.get('owner'),
                      'candidate': wave.get('candidate'), 'waiting': state.get('waiting'),
                      'next_action': state.get('next_action'), 'pending_intents': pending, 'live_actors': live,
                      'legacy_runtime_refs': state.get('legacy_runtime_refs') or state.get('runtime_refs')
                      if kind_of(wave) == 'wave1' else state.get('legacy_runtime_refs')})
        for intent in pending:
            actions.append(f'{ref}: reconcile intent {intent["correlation"]} ({intent["op"]} {intent["target"]}) '
                           'by reading the real runtime/file state before any retry')
        for actor in live:
            actions.append(f'{ref}: actor {actor["correlation"]} ref {actor.get("ref")} status {actor["status"]}: '
                           'confirm from a delivered signal or a targeted read; do not relaunch while it may be alive')
        if kind_of(wave) == 'wave1':
            actions.append(f'{ref}: v1 registry (runtime_refs {state.get("runtime_refs")}); reconcile them, '
                           'migrate to a new file at a stable wave boundary')
    journal = read_journal(program_path.parent / 'journal.jsonl')
    unapplied = [s['received'] for s in _event_status(journal).values() if not s['applied']]
    for event in unapplied:
        actions.append(f'event {event["id"]} ({event.get("kind")}) was received but never applied: process it now')
    view = ready_view(doc)
    if view['ready']:
        actions.append('ready outcomes to engage after reconciliation: ' + ', '.join(view['ready']))
    for dec in _items(doc.get('decisions_pending')):
        actions.append(f'decision {dec.get("id")} pending: {dec.get("question")} (suspends {dec.get("suspends")})')
    if errors:
        actions.insert(0, 'consistency errors must be reconciled before using this summary to launch anything')
    return {'owner': doc.get('owner'), 'status': sval(doc, 'status'), 'revision': doc.get('revision'),
            'last_milestone': doc.get('last_milestone'), 'ready': view, 'waves': waves,
            'unapplied_events': unapplied, 'journal_entries': len(journal),
            'consistency_errors': errors, 'actions': actions, 'limits': LIMITS}, bool(errors)


def migrate_v1(doc, source_path):
    errors = v1.validate(doc, Path(source_path).resolve().parent, check_paths=False)
    if errors:
        raise StateError('v1 source invalid; fix or record before migration: ' + '; '.join(errors))
    phase = sval(doc['state'], 'phase')
    if phase in {'completed', 'completed_partial'}:
        raise StateError(f'v1 wave is {phase}: keep it read-only as a historical v1 registry and reference it '
                         'from the program; no candidate or review is fabricated by migration')
    new = copy.deepcopy(doc)
    new.update(schema_version=2, revision=0, program_ref=None, candidate=None, envelope=None, intents=[])
    refs = doc['state'].get('runtime_refs') or []
    new['actors'] = [{'role': 'legacy', 'model': None, 'ref': ref if text(ref) else None,
                      'correlation': f'legacy/{index}', 'status': 'unknown', 'target': None}
                     for index, ref in enumerate(refs)]
    state = new['state']
    state['legacy_runtime_refs'] = doc['state'].get('runtime_refs')
    state['runtime_refs'] = None
    state['waiting'] = None
    if phase in WAITLIKE:
        kind = {'waiting_quota': 'quota', 'waiting_children': 'children', 'blocked': 'dependency'}.get(phase, 'runtime')
        state['waiting'] = {'kind': kind, 'detail': 'migrated from v1; verify', 'trigger': 'unknown after migration',
                            'resume': state.get('next_action') or 'reconcile before resuming', 'from': None}
    new['migrated_from'] = {'schema_version': 1, 'sha256': sha256_file(source_path), 'path': str(source_path)}
    return new


def cmd_migrate(args):
    source, dest = Path(args.source), Path(args.dest)
    if dest.exists():
        raise StateError(f'destination exists; migrations never overwrite: {dest}')
    doc = load(source)
    if kind_of(doc) != 'wave1':
        raise StateError('only wave schema_version 1 -> 2 is defined')
    new = migrate_v1(doc, source)
    errors = validate_wave2(new, dest.resolve().parent)
    if errors:
        raise StateError('migrated document invalid: ' + '; '.join(errors))
    with open(dest, 'x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(new, ensure_ascii=False, indent=2) + '\n')
    return {'migrated': str(dest), 'from_sha256': new['migrated_from']['sha256'],
            'unknown_actors': [a['correlation'] for a in new['actors']]}, False


def cmd_write(args):
    ops = load(args.ops_file) if args.ops_file else json.loads(args.ops)
    return guarded_write(args.file, args.actor, args.expect_revision, lambda d: apply_ops(d, ops),
                         detail=args.reason, applies_event=args.applies_event), False


def cmd_claim(args):
    previous = {}

    def mutate(doc):
        current = (_owner_of(doc) or {}).get('ref')
        previous['owner'] = current
        if current is not None and current != args.actor and not (args.takeover and text(args.evidence)):
            raise StateError(f'owner is {current}; takeover requires --takeover and --evidence '
                             'of a confirmed stop or recorded transfer')
        owner = {'role': args.role, 'ref': args.actor}
        if kind_of(doc) == 'program':
            doc['owner'] = owner
        else:
            doc['state']['owner'] = owner
        return doc

    result = guarded_write(args.file, args.actor, args.expect_revision, mutate, kind='claim',
                           detail={'evidence': args.evidence, 'takeover': bool(args.takeover)},
                           owner_check=False, owner_change=True)
    result.update(owner=args.actor, previous_owner=previous.get('owner'))
    return result, False


def cmd_transition(args):
    def mutate(doc):
        state = doc['state']
        current = sval(state, 'phase')
        ops = [{'op': 'set', 'path': 'state.phase', 'value': args.to}]
        if args.to in WAITLIKE:
            origin = current if current in ACTIVE_FROM_WAIT else (state.get('waiting') or {}).get('from')
            ops.append({'op': 'set', 'path': 'state.waiting', 'value': {
                'kind': args.waiting_kind, 'detail': args.detail, 'trigger': args.trigger,
                'resume': args.resume, 'from': origin}})
        else:
            ops.append({'op': 'set', 'path': 'state.waiting', 'value': None})
        if args.next_action:
            ops.append({'op': 'set', 'path': 'state.next_action', 'value': args.next_action})
        return apply_ops(doc, ops)

    return guarded_write(args.file, args.actor, args.expect_revision, mutate, kind='transition',
                         detail={'to': args.to}, applies_event=args.applies_event), False


def cmd_intent(args):
    if args.action == 'add':
        def mutate(doc):
            for intent in doc.get('intents', []):
                if intent.get('correlation') == args.correlation:
                    raise StateError(f'correlation {args.correlation} already used ({intent.get("status")}); '
                                     'reconcile it, then use a new attempt suffix')
                if sval(intent, 'status') == 'pending' and intent.get('op') == args.op and intent.get('target') == args.target:
                    raise StateError(f'pending intent {intent["correlation"]} for the same {args.op} {args.target}: reconcile first')
            if args.op == 'launch':
                for actor in _items(doc.get('actors')):
                    if actor.get('target') == args.target and sval(actor, 'status') in LIVE_ACTOR:
                        raise StateError(f'actor {actor.get("correlation")} on {args.target} is {actor.get("status")}: '
                                         'reconcile or record its end before another launch')
            doc['intents'].append({'correlation': args.correlation, 'op': args.op, 'target': args.target,
                                   'status': 'pending', 'result_ref': None, 'created_at': now()})
            return doc
        detail = {'correlation': args.correlation, 'op': args.op}
    else:
        def mutate(doc):
            doc = apply_ops(doc, [{'op': 'update', 'path': 'intents', 'match': {'correlation': args.correlation},
                                   'value': {'status': args.status, 'result_ref': args.result_ref, 'resolved_at': now()}}])
            intent = next(i for i in doc['intents'] if i['correlation'] == args.correlation)
            if args.status == 'confirmed' and intent['op'] == 'launch':
                doc['actors'].append({'role': args.role or 'unspecified', 'model': args.model, 'ref': args.result_ref,
                                      'correlation': args.correlation, 'status': 'running',
                                      'target': intent['target'], 'candidate_seq': None})
            return doc
        detail = {'correlation': args.correlation, 'status': args.status}
    return guarded_write(args.file, args.actor, args.expect_revision, mutate, kind='intent', detail=detail), False


def cmd_event(args):
    path = Path(args.file).resolve()
    doc = load(path)
    if kind_of(doc) != 'wave2':
        raise StateError('events are recorded against a v2 wave')
    owner = (_owner_of(doc) or {}).get('ref')
    if owner is not None and owner != args.actor:
        raise StateError(f'actor {args.actor} is not the owner ({owner})')
    jpath = journal_path(path, doc)
    with Lock(jpath):
        status = _event_status(read_journal(jpath)).get(args.id)
        if status and status['applied']:
            return {'classification': 'duplicate', 'effect': 'none: already applied'}, False
        if status:
            return {'classification': 'unapplied', 'effect': 'received earlier but never applied: process it now',
                    'received': status['received']}, False
        phase = doc['state']['phase']
        current = (doc.get('candidate') or {}).get('seq')
        if phase in TERMINAL_PHASES:
            cls = 'late'
        elif args.candidate_seq is not None and current is not None and args.candidate_seq < current:
            cls = 'stale'
        else:
            cls = 'new'
        append_journal(jpath, {'id': args.id, 'at': now(), 'kind': 'event:' + args.kind, 'file': path.name,
                               'actor': args.actor, 'classification': cls, 'candidate_seq': args.candidate_seq,
                               'wave_revision': doc.get('revision'), 'detail': args.detail})
    effect = {'new': 'process it, then write with --applies-event (or ack) using the read revision',
              'stale': 'recorded; does not close the current candidate',
              'late': 'recorded; terminal wave, no relaunch'}[cls]
    return {'classification': cls, 'effect': effect, 'wave_revision': doc.get('revision')}, False


def cmd_ack(args):
    """Mark a received event as applied when it needs no state change."""
    return guarded_write(args.file, args.actor, args.expect_revision, lambda d: copy.deepcopy(d), kind='ack',
                         detail=args.reason, applies_event=args.id), False


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('check', help='validate a program.json or wave.json (v1 or v2)')
    p.add_argument('file')
    p.add_argument('--check-paths', action='store_true', help='also check artifact files and hashes')
    p.set_defaults(func=cmd_check)
    p = sub.add_parser('ready', help='ready/admitted/waiting outcomes and declared resource conflicts')
    p.add_argument('program')
    p.set_defaults(func=cmd_ready)
    p = sub.add_parser('resume', help='cold-restart summary: owner, waves, intents, live actors, unapplied events')
    p.add_argument('program')
    p.set_defaults(func=cmd_resume)
    p = sub.add_parser('migrate', help='write a v2 copy of a non-terminal v1 wave.json into a new file')
    p.add_argument('source')
    p.add_argument('dest')
    p.set_defaults(func=cmd_migrate)
    specs = (('write', cmd_write, 'apply set/append/update ops under owner+revision'),
             ('claim', cmd_claim, 'set owner (takeover needs evidence)'),
             ('transition', cmd_transition, 'change wave phase along allowed transitions'),
             ('intent', cmd_intent, 'add a pending intent before a call, or resolve it'),
             ('event', cmd_event, 'classify and journal a received signal'),
             ('ack', cmd_ack, 'mark a received event applied without state change'))
    for name, func, help_ in specs:
        p = sub.add_parser(name, help=help_)
        p.add_argument('file')
        p.add_argument('--actor', required=True, help='runtime reference of the acting owner')
        if name != 'event':
            p.add_argument('--expect-revision', type=int, required=True)
        p.set_defaults(func=func)
        if name in {'write', 'transition'}:
            p.add_argument('--applies-event', help='id of the received event this write applies')
        if name == 'write':
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument('--ops', help='JSON list of {op:set|append|update, path, value, match}')
            group.add_argument('--ops-file')
            p.add_argument('--reason')
        elif name == 'claim':
            p.add_argument('--role', required=True)
            p.add_argument('--takeover', action='store_true')
            p.add_argument('--evidence')
        elif name == 'transition':
            p.add_argument('--to', required=True, choices=sorted(WAVE_V2_PHASES))
            p.add_argument('--waiting-kind', choices=sorted(WAVE_WAIT_KINDS))
            p.add_argument('--detail')
            p.add_argument('--trigger')
            p.add_argument('--resume')
            p.add_argument('--next-action')
        elif name == 'intent':
            p.add_argument('action', choices=['add', 'resolve'])
            p.add_argument('--correlation', required=True)
            p.add_argument('--op', choices=sorted(INTENT_OPS))
            p.add_argument('--target')
            p.add_argument('--status', choices=['confirmed', 'absent', 'failed'])
            p.add_argument('--result-ref')
            p.add_argument('--role', help='actor role recorded when a launch is confirmed')
            p.add_argument('--model')
        elif name in {'event', 'ack'}:
            p.add_argument('--id', required=True, help='stable signal id (taskId+runId or equivalent)')
            if name == 'event':
                p.add_argument('--kind', required=True)
                p.add_argument('--candidate-seq', type=int)
                p.add_argument('--detail')
            else:
                p.add_argument('--reason')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == 'intent':
        if args.action == 'add' and not (args.op and args.target):
            parser.error('intent add needs --op and --target')
        if args.action == 'resolve' and not args.status:
            parser.error('intent resolve needs --status')
    if args.command == 'transition' and args.to in WAITLIKE:
        if not all((args.waiting_kind, args.detail, args.trigger, args.resume)):
            parser.error('waiting and blocked phases need --waiting-kind, --detail, --trigger and --resume')
    try:
        result, failed = args.func(args)
    except (StateError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc), 'limits': LIMITS}, ensure_ascii=False))
        return 1
    except (TypeError, AttributeError) as exc:  # malformed input that escaped validation: reported, not hidden
        print(json.dumps({'ok': False, 'error': f'internal error on malformed input: {type(exc).__name__}: {exc}',
                          'internal': True, 'limits': LIMITS}, ensure_ascii=False))
        return 2
    print(json.dumps(dict(result, ok=not failed), ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
