"""Deterministic state tool for development programs and waves (stdlib only).

Commands validate, compute ready work, migrate formats, create initial states (init) and
perform guarded writes (owner + expected revision + locks + full validation + atomic replace
+ journal). `init --template program|wave` prints the expected format of each field.
Declarations are checked, never certified: the tool cannot prove authority,
review quality, runtime delivery or execution.
"""
import argparse
import contextlib
import copy
import datetime
import hashlib
import importlib.util
import json
import os
import posixpath
import secrets
import stat
import sys
import time
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
DOCUMENTARY_ROLE = 'reviewer'
PRE_LAUNCH_PHASES = {'planning', 'preparing', 'ready'}
INTENT_OPS = {'launch', 'send', 'write', 'promote'}
INTENT_STATUSES = {'pending', 'confirmed', 'absent', 'failed'}
OUTCOME_STATUSES = {'pending', 'admitted', 'accepted', 'accepted_partial', 'failed', 'abandoned', 'blocked'}
CLOSED_OUTCOMES = {'accepted', 'accepted_partial', 'abandoned'}
PROGRAM_STATUSES = {'active', 'waiting_human', 'waiting_quota', 'waiting_runtime', 'stopped', 'completed'}
WAIT_KINDS = {'human', 'quota', 'runtime', 'dependency', 'resource'}
WAVE_WAIT_KINDS = WAIT_KINDS | {'children'}
MANAGED_PATHS = ('owner', 'revision', 'schema', 'schema_version', 'migrated_from', 'state.owner')
LAUNCH_CONTEXT = ('project', 'authorization', 'socles', 'batches', 'artifacts', 'reviews', 'candidate')
CLOSED_KEYS = {
    'program': {'': {'schema', 'revision', 'owner', 'mandate', 'skills_consumed', 'status', 'status_reason',
                     'outcomes', 'decisions_pending', 'last_milestone'},
                'mandate': {'ref', 'sha256', 'scope', 'exclusions', 'end_criteria'}},
    'wave2': {'': {'schema_version', 'revision', 'mode', 'project', 'authorization', 'socles', 'batches', 'artifacts',
                   'reviews', 'decisions', 'state', 'program_ref', 'candidate', 'envelope', 'actors', 'intents',
                   'migrated_from'},
              'state': {'phase', 'owner', 'next_action', 'blockers', 'runtime_refs', 'consumed', 'launch_ready',
                        'waiting', 'legacy_runtime_refs'},
              'project': {'root', 'baseline', 'observed_at'},
              'authorization': {'launch', 'source', 'scope', 'exclusions'}},
}
LIMITS = ('Checks declarations, revisions and local files only. Cannot certify authority, '
          'review quality, runtime delivery, idempotence of runtime calls or execution.')

text, digest, string_list, local_path, got = v1.text, v1.digest, v1.string_list, v1.local_path, v1.got


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


def documentary_role(role):
    return isinstance(role, str) and role.strip().lower() == DOCUMENTARY_ROLE


def documentary_only(doc):
    """Why only documentary reviews may run in this wave, or '' when product actors may."""
    if not launch_authorized(doc):
        return 'without launch authorization (mode prepare or authorization.launch=false)'
    state = doc.get('state') if isinstance(doc.get('state'), dict) else {}
    if before_launch(state):
        return f'not launched yet (phase {sval(state, "phase")})'
    return ''


def before_launch(state):
    """True while the wave has not entered launched: a pre-launch phase, or a wait whose origin is one or null
    (entered from planning, or migrated). The origin is written only by the transition that opens the wait."""
    phase = sval(state, 'phase')
    if phase in WAITLIKE:
        phase = wait_origin(state)
    return phase is None or phase in PRE_LAUNCH_PHASES


def migrated_legacy(doc, actor):
    """Actor created by migrate for a v1 runtime_ref, still unknown: it predates any launch rule."""
    state = doc.get('state') if isinstance(doc.get('state'), dict) else {}
    refs, corr = state.get('legacy_runtime_refs'), actor.get('correlation')
    if not (isinstance(doc.get('migrated_from'), dict) and isinstance(refs, list) and actor.get('role') == 'legacy'
            and sval(actor, 'status') == 'unknown' and isinstance(corr, str) and corr.startswith('legacy/')
            and corr[len('legacy/'):].isdigit()):
        return False
    index = int(corr[len('legacy/'):])
    return index < len(refs) and actor.get('ref') == (refs[index] if text(refs[index]) else None)


def launch_authorized(doc):
    auth = doc.get('authorization') if isinstance(doc.get('authorization'), dict) else {}
    return doc.get('mode') == 'prepare-and-launch' and auth.get('launch') is True


class StateError(Exception):
    pass


class MalformedOwner(StateError):
    pass


class OpenOperation(StateError):
    """Failure after the prepare line was journaled: the operation stays open until reconcile."""


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def _no_constant(name):
    raise ValueError(f'{name} is not JSON')


def strict_json(data):
    """JSON as any strict reader accepts it: NaN, Infinity and -Infinity refused."""
    return json.loads(data, parse_constant=_no_constant)


def load(path):
    return strict_json(Path(path).read_text(encoding='utf-8-sig'))


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


def unknown_keys(doc):
    """Keys of the closed objects of a program or v2 wave that its format does not define."""
    out = []
    for where, known in CLOSED_KEYS.get(kind_of(doc), {}).items():
        obj = doc.get(where) if where else doc
        if isinstance(obj, dict):
            out.extend(f'{where}.{k}' if where else k for k in obj if k not in known)
    return out


# ---------------------------------------------------------------- per-field messages

def _one_of(options):
    return (lambda v: member(v, options)), 'one of ' + ', '.join(sorted(options))


TEXT = (text, 'nonempty text')
DIGEST = (digest, '64 hex characters')
TEXT_OR_NULL = ((lambda v: v is None or text(v)), 'text or null')
STRINGS = (string_list, 'list of strings')
STRINGS_OR_NULL = ((lambda v: v is None or string_list(v)), 'list of strings or null')
BOOL = ((lambda v: type(v) is bool), 'bool')
OBJECT = ((lambda v: isinstance(v, dict)), 'object')
LIST = ((lambda v: isinstance(v, list)), 'list')
MANDATE_FIELDS = (('ref', TEXT), ('scope', STRINGS), ('exclusions', STRINGS), ('end_criteria', TEXT))
AUTHORIZATION_FIELDS = (('launch', BOOL), ('source', TEXT_OR_NULL), ('scope', STRINGS_OR_NULL), ('exclusions', STRINGS))
PROJECT_FIELDS = tuple((k, TEXT_OR_NULL) for k in ('root', 'baseline', 'observed_at'))


def list_shape(value, present=True, empty_ok=False):
    """Received shape of a list of objects: its type, 'empty list', or its first item that is not an object."""
    if not isinstance(value, list):
        return got(value, present)
    bad = next((i for i, item in enumerate(value) if not isinstance(item, dict)), None)
    return f'list with {got(value[bad])} at [{bad}]' if bad is not None else 'empty list' if not empty_ok else 'list'


def field_errors(obj, prefix, fields, present=True, only_missing=False):
    """One message per failing field: '<prefix>.<key>: expected <type>, got <type>'."""
    if not isinstance(obj, dict):
        keys = ', '.join(k for k, _ in fields)
        return [f'{prefix}: expected object {{{keys}}}, got {got(obj, present)}']
    out = []
    for key, (check, expected) in fields:
        here = key in obj
        if (not here) if only_missing else (not here or not check(obj.get(key))):
            shown = repr(obj[key]) if here and expected.startswith('one of') and isinstance(obj[key], str) else \
                got(obj.get(key), here, items=expected.startswith('list of strings'))
            out.append(f'{prefix + "." if prefix else ""}{key}: expected {expected}, got {shown}')
    return out


def _v1_details(doc):
    """Per-field replacements for shared v1 messages on the same document (same validity, more detail)."""
    auth, project, state = doc.get('authorization'), doc.get('project'), doc.get('state')
    sobj = state if isinstance(state, dict) else {}
    details = {
        'invalid authorization fields': field_errors(auth, 'authorization', AUTHORIZATION_FIELDS,
                                                     'authorization' in doc, only_missing=True),
        'invalid project fields': field_errors(project, 'project', PROJECT_FIELDS, 'project' in doc, only_missing=True),
        'invalid mode': field_errors(doc, '', (('mode', _one_of({'prepare', 'prepare-and-launch'})),)),
        'decisions must be a list of text': field_errors(doc, '', (('decisions', STRINGS),)),
        'socles must be a list': field_errors(doc, '', (('socles', LIST),)),
        'batches must be a list': field_errors(doc, '', (('batches', LIST),)),
        'reviews must be a list': field_errors(doc, '', (('reviews', LIST),)),
        'artifacts must be an object': field_errors(doc, '', (('artifacts', OBJECT),)),
        'state.launch_ready must be boolean': field_errors(sobj, 'state', (('launch_ready', BOOL),)),
        'state.blockers must be a list of text': field_errors(sobj, 'state', (('blockers', STRINGS),)),
        'state.next_action must be nonempty text': field_errors(sobj, 'state', (('next_action', TEXT),)),
        'state.consumed must be an object': field_errors(sobj, 'state', (('consumed', OBJECT),)),
    }
    if isinstance(state, dict):
        missing = sorted({'phase', 'owner', 'next_action', 'blockers', 'runtime_refs', 'consumed', 'launch_ready'} - set(state))
        details['invalid state fields'] = ['state: missing ' + ', '.join(missing)] if missing else []
    v1_auth = ('authorization.launch must be boolean', 'authorization.source: text or null required',
               'authorization.scope must be a list of actions/cibles or null',
               'authorization.exclusions must be a list of text')
    for message, field in zip(v1_auth, AUTHORIZATION_FIELDS):  # not an object: one message for the whole field
        details[message] = field_errors(auth, 'authorization', (field,)) if isinstance(auth, dict) \
            else details['invalid authorization fields']
    for field in PROJECT_FIELDS:
        details[f'project.{field[0]}: text or null required'] = field_errors(project, 'project', (field,)) \
            if isinstance(project, dict) else details['invalid project fields']
    return details


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
    # A closed wave is an archive: the documents it consumed and reviewed may evolve; its frozen candidate may not.
    live_files = check_paths and phase not in TERMINAL_PHASES
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
        if pstate.get('launch_ready') is True and not before_launch(state):
            pstate['launch_ready'] = False  # launched: the launch conditions were checked at the entry, not again
    details = _v1_details(projected)
    for message in v1.validate(projected, directory, check_paths=live_files):
        replacement = details.get(message)
        if replacement:  # same rule, one message per faulty field with expected and received types
            errors.extend(m for m in replacement if m not in errors)
        else:
            errors.append(message)  # v1 rule shared by v2; no version prefix in a v2 report

    require(kind_of(doc) == 'wave2', 'schema_version must be the integer 2')
    auth = doc.get('authorization') if isinstance(doc.get('authorization'), dict) else {}
    require(auth.get('launch') is not True or text(auth.get('source')),
            f'authorization.source: expected nonempty text when authorization.launch is true, '
            f'got {got(auth.get("source"), "source" in auth)}')
    require(type(doc.get('revision')) is int and doc['revision'] >= 0, 'revision must be a non-negative integer')
    artifacts = doc.get('artifacts') if isinstance(doc.get('artifacts'), dict) else {}
    ref = doc.get('program_ref')
    require(ref is None or relative_ref(ref), 'program_ref must be null or a relative path')
    if relative_ref(ref) and self_path is not None:
        target = (Path(self_path).resolve().parent / ref).resolve()
        require(target.is_file() and _program_back_reference(Path(self_path).resolve(), target),
                'program_ref must resolve to an existing program whose outcomes reference this wave')
    cand = doc.get('candidate')
    cand_errors = [] if cand is None else field_errors(cand, 'candidate', (
        ('seq', ((lambda v: type(v) is int and v >= 1), 'integer >= 1')), ('ref', TEXT),
        ('artifact', ((lambda v: member(v, set(artifacts))), 'key of artifacts')), ('sha256', DIGEST)))
    cand_ok = not cand_errors
    errors.extend(cand_errors)
    if cand_ok and isinstance(cand, dict) and check_paths and directory is not None:
        target = (Path(directory) / str(artifacts[cand['artifact']]).replace('\\', '/')).resolve()
        require(target.is_file() and sha256_file(target) == cand['sha256'].lower(),
                'candidate artifact missing or sha256 mismatch with local file')
    if live_files and directory is not None:
        consumed = state.get('consumed') if isinstance(state.get('consumed'), dict) else {}
        documentary = {}
        for review in _items(doc.get('reviews')):
            name = review.get('artifact')
            if (review.get('candidate_seq') is None and member(name, set(artifacts)) and name not in consumed
                    and digest(review.get('sha256'))):
                documentary.setdefault(name, set()).add(review['sha256'].lower())
        base = Path(directory).resolve()
        for name, shas in sorted(documentary.items()):
            if not local_path(artifacts[name]):
                continue
            target = (base / artifacts[name].replace('\\', '/')).resolve()
            if target.is_file() and base in target.parents:
                require(sha256_file(target) in shas,
                        f'{name}: no documentary review sha256 matches the local artifact (its reviews cover other bytes)')
    env = doc.get('envelope')
    errors.extend([] if env is None else field_errors(env, 'envelope', (('reason', TEXT),)))
    require(isinstance(doc.get('actors'), list) and len(actors) == len(doc['actors']), 'actors must be a list of objects')
    for index, actor in enumerate(actors):
        require(text(actor.get('role')) and text(actor.get('correlation')) and member(sval(actor, 'status'), ACTOR_STATUSES)
                and (actor.get('ref') is None or text(actor.get('ref')))
                and (actor.get('target') is None or text(actor.get('target'))),
                f'actors[{index}]: role, correlation, status, ref(text|null), target(text|null) required')
    where = documentary_only(doc)
    if where:
        for index, actor in enumerate(actors):
            require(sval(actor, 'status') not in LIVE_ACTOR or documentary_role(actor.get('role'))
                    or migrated_legacy(doc, actor),
                    f'actors[{index}]: live actor with role {actor.get("role")!r} in a wave {where}: only role '
                    '"reviewer" (documentary review) may be live; record its end with status and evidence, '
                    'or authorize and pass launched first')
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
            require(text(intent.get('result_ref')) or text(intent.get('evidence')),
                    label + ': confirmed intent requires result_ref, or an evidence of what was observed')
        if intent['status'] == 'pending':
            key = (intent['op'], intent['target'])
            require(key not in pending_targets, label + ': second pending intent for the same op/target')
            pending_targets.add(key)
    reviews = _items(doc.get('reviews'))
    for index, review in enumerate(doc.get('reviews') if isinstance(doc.get('reviews'), list) else []):
        if not isinstance(review, dict):
            continue
        seq = review.get('candidate_seq')  # null (documentary review) is the same as absent
        top = cand['seq'] if cand_ok and isinstance(cand, dict) else 0
        require(seq is None or (type(seq) is int and 1 <= seq <= top),
                f'reviews[{index}].candidate_seq: expected null or the seq of a frozen candidate (1 to {top}), got '
                + (repr(seq) if type(seq) is int else got(seq)))
    if member(phase, WAITLIKE):
        require(_wait_shape(state.get('waiting')),
                f'{phase} requires state.waiting {{kind, detail, trigger, resume, from}}')
    else:
        require(state.get('waiting') is None, 'state.waiting must be null outside blocked and waiting phases')
    live_targets = [a.get('target') for a in actors if sval(a, 'status') in LIVE_ACTOR and text(a.get('target'))]
    require(len(live_targets) == len(set(live_targets)), 'two live actors on the same target')
    if member(phase, TERMINAL_PHASES):
        live = [a.get('correlation') for a in actors if sval(a, 'status') in LIVE_ACTOR]
        require(not live, f'{phase} with live or unknown actors (reconcile them first): ' + ', '.join(map(str, live)))
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
    if phase in {'failed', 'completed_partial'}:
        require(isinstance(doc.get('decisions'), list) and any(text(d) for d in doc['decisions']),
                'failed requires a recorded cause and resumption condition in decisions' if phase == 'failed' else
                'completed_partial requires the unqualified scope named in decisions')
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
        elif status in {'blocked', 'failed'}:
            blocked.append(o['id'])
        deps = o.get('depends_on') if string_list(o.get('depends_on')) else []
        unmet = [dep for dep in deps if by_id.get(dep, {}).get('status') != 'accepted']
        if o.get('waiting_on'):
            waiting[o['id']] = o['waiting_on'].get('kind') if isinstance(o['waiting_on'], dict) else 'invalid'
        elif status == 'pending' and unmet:  # every open outcome is listed with what it waits for
            waiting[o['id']] = 'depends_on ' + ', '.join(unmet)
        if status == 'pending' and not o.get('waiting_on') and o['id'] not in suspended and not unmet:
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

    def wave_of(oid):
        ref = by_id[oid].get('state_ref')
        return posixpath.normpath(ref.replace('\\', '/')) if text(ref) else None

    for i, a in enumerate(admitted):  # two admitted outcomes of the same wave share its resources by design
        for b in admitted[i + 1:]:
            if res(a) & res(b) and (wave_of(a) is None or wave_of(a) != wave_of(b)):
                conflicts.append({'kind': 'admitted-admitted', 'outcomes': [a, b], 'resources': sorted(res(a) & res(b))})
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
    require(type(doc.get('revision')) is int and doc['revision'] >= 0,
            f'revision must be a non-negative integer, got {got(doc.get("revision"), "revision" in doc)}')
    owner = doc.get('owner')
    require(owner is None or (isinstance(owner, dict) and text(owner.get('role')) and text(owner.get('ref'))),
            'owner must be null or {role, ref}')
    errors.extend(field_errors(doc.get('mandate'), 'mandate', MANDATE_FIELDS, 'mandate' in doc))
    mandate = doc.get('mandate') if isinstance(doc.get('mandate'), dict) else {}
    require('sha256' not in mandate or digest(mandate['sha256']),
            f'mandate.sha256: expected 64 hex characters or absent, got {got(mandate.get("sha256"))}')
    skills = doc.get('skills_consumed')
    bad_skills = [i for i, s in enumerate(skills) if not (isinstance(s, dict) and text(s.get('name'))
                                                           and digest(s.get('sha256')))] if isinstance(skills, list) else None
    if bad_skills != []:
        errors.append('skills_consumed must list {name, sha256 (64 hex)}: ' +
                      (f'got {got(skills, "skills_consumed" in doc)}' if bad_skills is None
                       else f'invalid item at [{bad_skills[0]}]'))
    status = sval(doc, 'status')
    errors.extend('invalid program status: ' + m for m in
                  field_errors(doc, '', (('status', _one_of(PROGRAM_STATUSES)),)))
    require(text(doc.get('status_reason')),
            f'status_reason required: expected nonempty text, got {got(doc.get("status_reason"), "status_reason" in doc)}')
    raw_outcomes = doc.get('outcomes')
    outcomes = _items(raw_outcomes)
    require(isinstance(raw_outcomes, list) and outcomes and len(outcomes) == len(raw_outcomes),
            'outcomes: expected nonempty list of objects, got ' + list_shape(raw_outcomes, 'outcomes' in doc))
    ids = [o.get('id') for o in outcomes]
    errors.extend(f'outcomes[{i}].id: expected nonempty text, got {got(o.get("id"), "id" in o)}'
                  for i, o in enumerate(outcomes) if not text(o.get('id')))
    ids = [i for i in ids if text(i)]
    require(len(ids) == len(set(ids)), 'duplicate outcome ID')
    by_id = {o['id']: o for o in outcomes if text(o.get('id'))}
    graph = {i: set() for i in by_id}
    raw_decisions = doc.get('decisions_pending')
    decisions = _items(raw_decisions)
    require(isinstance(raw_decisions, list) and len(decisions) == len(raw_decisions),
            'decisions_pending: expected list of objects, got ' + list_shape(raw_decisions, 'decisions_pending' in doc,
                                                                             empty_ok=True))
    for index, dec in enumerate(decisions):
        errors.extend(field_errors(dec, f'decisions_pending[{index}]', (
            ('id', TEXT), ('question', TEXT), ('option', (text, 'nonempty text (a concrete option)')),
            ('effects', TEXT), ('suspends', ((lambda v: string_list(v) and all(x in by_id for x in v)),
                                             'list of known outcome ids, empty when it suspends nothing')))))
    suspended = _suspended(doc)
    base = Path(directory).resolve() if directory is not None else None
    program_path = Path(self_path).resolve() if self_path is not None else None
    for oid, o in by_id.items():
        st = sval(o, 'status')
        require(member(st, OUTCOME_STATUSES), f'{oid}: invalid status: ' +
                '; '.join(field_errors(o, 'outcomes.' + oid, (('status', _one_of(OUTCOME_STATUSES)),))))
        require(text(o.get('outcome')) and text(o.get('next_action')), f'{oid}: outcome and next_action required: ' +
                '; '.join(field_errors(o, 'outcomes.' + oid, (('outcome', TEXT), ('next_action', TEXT)))))
        deps = o.get('depends_on')
        valid_deps = string_list(deps) and all(d in by_id for d in deps)
        require(valid_deps, f'{oid}: depends_on: expected list of known outcome ids, got '
                + (f'unknown {sorted(set(deps) - set(by_id))}' if string_list(deps) else got(deps, 'depends_on' in o, True)))
        deps = deps if valid_deps else []
        graph[oid].update(deps)
        require(string_list(o.get('resources')),
                f'{oid}: resources must be a list of strings, got {got(o.get("resources"), "resources" in o, items=True)}')
        ref = o.get('state_ref')
        require(ref is None or local_path(ref), f'{oid}: state_ref must be null or a local relative path')
        if st == 'admitted':
            require(text(ref), f'{oid}: admitted requires state_ref')
        if st in {'accepted', 'accepted_partial'} and not text(ref):
            closure = o.get('closure')
            require(isinstance(closure, dict) and text(closure.get('source')) and text(closure.get('remaining')),
                    f'{oid}: {st} requires state_ref (its closed wave) or, accepted outside any wave, '
                    'closure {source, remaining} naming that acceptance')
        if st in {'admitted', 'accepted', 'accepted_partial'}:
            for dep in deps:
                require(sval(by_id[dep], 'status') == 'accepted', f'{oid}: {st} while dependency {dep} is not accepted')
        if st in {'accepted_partial', 'abandoned', 'failed'}:
            closure = o.get('closure')
            require(isinstance(closure, dict) and text(closure.get('source')) and text(closure.get('remaining')),
                    f'{oid}: {st} requires closure {{source, remaining}}')
        wait = o.get('waiting_on')
        errors.extend([] if wait is None else field_errors(wait, f'outcomes.{oid}.waiting_on', (
            ('kind', _one_of(WAIT_KINDS)), ('detail', TEXT), ('trigger', TEXT))))
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
        require(not [d for d in decisions if d.get('suspends')], 'completed with pending decisions that suspend outcomes')
    if status == 'active':
        moving = view['ready'] or [o for o in view['admitted'] if not by_id[o].get('waiting_on')]
        require(bool(moving), 'active without ready or unwaited admitted outcomes: declare a waiting status, stopped or completed')
    milestone = doc.get('last_milestone')
    errors.extend([] if milestone is None else
                  field_errors(milestone, 'last_milestone', tuple((k, TEXT) for k in ('at', 'summary', 'ref'))))
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

WRITE_EXAMPLES = '''examples (--ops takes a JSON list; a path names object keys only, never a list index):
  set a field:          [{"op":"set","path":"status_reason","value":"B1 admitted"}]
  change a list item:   [{"op":"update","path":"outcomes","match":{"id":"B1"},
                          "value":{"status":"admitted","state_ref":"waves/b1/wave.json"}}]
  add a list item:      [{"op":"append","path":"decisions","value":"lot B1 cut in two"}]
update merges value into the single item whose fields equal match; it refuses zero or several matches.

actor return in one command (signal receipt, intent resolution and application in a single revision):
  write FILE --actor A --expect-revision N --resolve-intent CORR --status confirmed --result-ref R
        --record-event ID --kind K [--candidate-seq S] [--ops ...]
  ops apply after the resolution, so they can update the actor it creates (its status included, without more
  evidence). A launch proven without receipt: --status confirmed --evidence "what was observed", no --result-ref;
  the actor is born with ref null and takes the status the ops give it. The signal is recorded first, as
  event does; the write runs only when it is new or received but unapplied on a wave not closed, otherwise its
  class is reported, nothing is written and the exit code is 1. After the write, event.effect reads "applied by
  this write". A refused write, invalid --ops included, leaves the event recorded
  and unapplied: rerun the same command once the cause is fixed. A failure after the prepare line leaves the
  event uncertain: run reconcile, never rerun. Ops are checked against the resolved intent: they cannot
  reopen it. An actor status change needs a new "evidence" on the actor, or the applied signal.'''


COMMAND_EXAMPLES = {
    'write': WRITE_EXAMPLES,
    'claim': '''example (--actor, --role and --expect-revision are required; N is the revision you read):
  claim FILE --actor A --role pilot --expect-revision N
  claim FILE --actor B --role pilot --expect-revision N --takeover --evidence "stop of A confirmed by task list"''',
    'transition': '''examples (--to, --actor and --expect-revision are required):
  transition FILE --actor A --expect-revision N --to preparing --next-action "write the mandates"
  transition FILE --actor A --expect-revision N --to blocked --waiting-kind dependency --detail "input missing"
             --trigger "input delivered" --resume "resume preparing"
  transition FILE --actor A --expect-revision N --to integrating --applies-event task-1:run-1''',
    'event': '''example (--actor, --id and --kind are required; event takes no --expect-revision):
  event FILE --actor A --id task-1:run-1 --kind review [--candidate-seq S] [--detail TEXT]
then apply it: write ... --applies-event task-1:run-1, or ack if it changes nothing.''',
    'intent': '''examples (FILE comes before the action; --actor, --expect-revision and --correlation are required):
  intent FILE add --actor A --expect-revision N --correlation w1/A/champion/1 --op launch --target A
  intent FILE resolve --actor A --expect-revision N --correlation w1/A/champion/1 --status confirmed
         --result-ref task-1 --role champion''',
    'reconcile': '''example (--actor, --op and --evidence are required; the op id is listed by resume):
  reconcile FILE --actor A --op op:wave.json:3:1a2b3c4d --evidence "state sha256 compared with the prepare line"
  add --declare committed|not_committed only when the bytes match neither side (the owner alone may declare)''',
    'dispose': '''example (--actor, --id, --disposition and --evidence are required; terminal waves only):
  dispose FILE --actor A --id task-1:run-1 --disposition late --evidence "wave stopped before this return"''',
    'ack': '''example (--actor, --expect-revision and --id are required):
  ack FILE --actor A --expect-revision N --id task-1:run-1 --reason "signal needs no state change"''',
}


def _list_in_path(path, parts, index):
    """Refusal for a path that walks into a list, pointing to update with match."""
    prefix = '.'.join(parts[:index])
    return StateError(f'{path}: {prefix} is a list; a path cannot index a list item. Use '
                      f'{{"op":"update","path":"{prefix}","match":{{"<key>":"<value>"}},"value":{{...}}}} '
                      '(see write --help)')


def _get(doc, path):
    node = doc
    parts = path.split('.')
    for index, part in enumerate(parts):
        if isinstance(node, list):
            raise _list_in_path(path, parts, index)
        if not isinstance(node, dict) or part not in node:
            raise StateError(f'path not found: {path}')
        node = node[part]
    return node


def _set(doc, path, value):
    parts = path.split('.')
    node = doc
    for index, part in enumerate(parts[:-1]):
        if isinstance(node.get(part) if isinstance(node, dict) else None, list):
            raise _list_in_path(path, parts, index + 1)
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
            target.append(with_item_defaults(copy.deepcopy(op.get('value')), ITEM_DEFAULTS.get((kind_of(result), path))))
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


def owner_ref(doc):
    owner = _owner_of(doc)
    if owner is None or isinstance(owner, dict):
        return (owner or {}).get('ref')
    raise MalformedOwner(f'owner is malformed (got {got(owner)}, expected null or {{role, ref}}): record the owner '
                         'again with claim --takeover --evidence')


def previous_owner(doc):
    owner = _owner_of(doc)
    return owner.get('ref') if isinstance(owner, dict) else owner


def wait_origin(state):
    waiting = state.get('waiting') if isinstance(state, dict) else None
    return waiting.get('from') if isinstance(waiting, dict) else None


def launch_context_changes(old, new):
    """Launch-context fields changed, before launch, by a write whose new version declares launch_ready true.
    launch_ready only guards the entry into launched: once the wave is launched it no longer moves."""
    ostate, nstate = old.get('state'), new.get('state')
    if not (isinstance(ostate, dict) and isinstance(nstate, dict) and nstate.get('launch_ready') is True
            and before_launch(ostate)):
        return []
    changed = [f for f in LAUNCH_CONTEXT if old.get(f) != new.get(f)]
    if ostate.get('consumed') != nstate.get('consumed'):
        changed.append('state.consumed')
    return changed


def check_evolution(old, new, owner_change=False, applies_event=None):
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
        if po in TERMINAL_PHASES and not owner_change:  # claim, which only changes the owner, stays open
            errors.append(f'wave is terminal ({po}); record late signals with event, start a new wave to resume')
        elif pn != po and pn not in TRANSITIONS.get(po, set()):
            hint = ('; a wait entered from planning keeps waiting.from=null and resumes to preparing'
                    if po in WAITLIKE and pn == 'planning' else '')
            errors.append(f'transition {po} -> {pn} not allowed{hint}')
        elif pn == 'launched' and po == 'ready' and nstate.get('launch_ready') is not True:
            errors.append('entering launched requires state.launch_ready=true, set by the owner after checking the launch context')
        if not before_launch(ostate) and nstate.get('launch_ready') != ostate.get('launch_ready'):
            errors.append('state.launch_ready only guards the entry into launched: it no longer changes once the wave '
                          'is launched')
        # The origin of a wait is the active phase it leaves (null from planning), recorded when the wait opens and
        # never changed while waiting; the only active exit is that origin, or preparing for a null origin.
        origin = wait_origin(ostate) if po in WAITLIKE else None
        if po not in WAITLIKE and pn in WAITLIKE:
            entered = wait_origin(nstate)
            expected = po if po in ACTIVE_FROM_WAIT else None
            if entered != expected:
                errors.append(f'entering {pn} from {po} requires waiting.from={expected}, not {entered}')
        if po in WAITLIKE and pn in WAITLIKE and wait_origin(nstate) != origin:
            errors.append(f'waiting origin {origin} cannot be changed while waiting')
        if po in WAITLIKE and pn in ACTIVE_FROM_WAIT and pn != (origin or 'preparing'):
            errors.append(f'wait was entered from {origin}; resume to {origin}, not {pn}' if origin else
                          f'wait was entered before launch (waiting.from=null); resume to preparing, not {pn}: the wave '
                          'enters launched only from ready, with state.launch_ready=true')
        if old.get('program_ref') is not None and new.get('program_ref') != old.get('program_ref'):
            errors.append('program_ref is immutable once set')
        oa = {a['correlation']: a for a in _items(old.get('actors')) if text(a.get('correlation'))}
        na = {a['correlation']: a for a in _items(new.get('actors')) if text(a.get('correlation'))}
        oi = {i['correlation']: i for i in _items(old.get('intents')) if text(i.get('correlation'))}
        ni = {i['correlation']: i for i in _items(new.get('intents')) if text(i.get('correlation'))}
        for corr, intent in oi.items():
            if corr not in ni:
                errors.append(f'intent {corr} removed')
                continue
            if sval(intent, 'status') != 'pending' and ni[corr] != intent:
                errors.append(f'intent {corr} is resolved and immutable')
            elif (intent.get('op') == 'launch' and sval(ni[corr], 'status') == 'confirmed'
                  and sval(intent, 'status') != 'confirmed' and corr not in set(na) - set(oa)):
                errors.append(f'intent {corr}: a launch is confirmed only with the actor it creates; use intent '
                              'resolve or write --resolve-intent, which record it')
            for field in ('op', 'target'):
                if ni[corr].get(field) != intent.get(field):
                    errors.append(f'intent {corr}: {field} is immutable')
        for corr, intent in ni.items():
            if corr not in oi and sval(intent, 'status') != 'pending':
                errors.append(f'intent {corr} must be created pending, before the runtime call')
        for corr, actor in oa.items():
            if corr not in na:
                errors.append(f'actor {corr} removed (keep actors; mark their status)')
                continue
            for field in ('ref', 'target'):
                if actor.get(field) and na[corr].get(field) != actor.get(field):
                    errors.append(f'actor {corr}: known {field} is immutable')
            evidence = na[corr].get('evidence')
            if (sval(na[corr], 'status') != sval(actor, 'status') and applies_event is None
                    and not (text(evidence) and evidence != actor.get('evidence'))):
                errors.append(f'actor {corr}: {actor.get("status")} -> {na[corr].get("status")} needs its evidence: '
                              'give the actor a new "evidence" (task status read, delivered signal, file) or apply '
                              'the signal that proves it with --applies-event')
        where = documentary_only(new)
        for corr, actor in sorted(na.items()):  # the role rule is judged on the resulting state, requalification included
            role = actor.get('role')
            if where and not documentary_role(role) and (corr not in oa or oa[corr].get('role') != role):
                errors.append(f'actor {corr}: role {role!r} refused in a wave {where}: only a documentary '
                              'review, --role reviewer')
        for corr in sorted(set(na) - set(oa)):
            linked = ni.get(corr)
            if not linked or sval(linked, 'status') != 'confirmed' or linked.get('op') != 'launch':
                errors.append(f'actor {corr} needs a confirmed launch intent with the same correlation')
            elif na[corr].get('target') != linked.get('target'):
                errors.append(f'actor {corr} target must be its launch intent target')
        for corr, intent in ni.items():
            if corr in oi or intent.get('op') != 'launch':
                continue
            for actor in na.values():
                if sval(actor, 'status') in LIVE_ACTOR and actor.get('target') == intent.get('target'):
                    errors.append(f'launch intent {corr}: actor {actor.get("correlation")} on {intent.get("target")} '
                                  f'is {sval(actor, "status")}; reconcile it first')
                elif sval(actor, 'status') == 'unknown' and actor.get('target') is None:
                    errors.append(f'launch intent {corr}: actor {actor.get("correlation")} has unknown status and no '
                                  'known target; reconcile it before any launch in this wave')
        oc, nc = old.get('candidate'), new.get('candidate')
        if isinstance(oc, dict):
            old_seq = oc.get('seq') if type(oc.get('seq')) is int else 0
            if not isinstance(nc, dict) or type(nc.get('seq')) is not int or nc['seq'] < old_seq:
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


REPARSE_POINT = 0x400


def _is_link(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & REPARSE_POINT)


def check_ancestors(path):
    """Refuse symbolic links and reparse points (junctions) on the existing ancestors of path."""
    for node in Path(path).parents:
        try:
            st = os.lstat(node)
        except FileNotFoundError:
            continue
        if _is_link(st):
            raise StateError(f'link or reparse point refused in ancestors: {node}')


def check_state_file(path):
    """The state file itself must be a regular file reached without link or reparse point."""
    st = os.lstat(path)
    if _is_link(st) or not stat.S_ISREG(st.st_mode):
        raise StateError(f'state file must be a regular file, not a link or reparse point: {path}')


def replace_file(source, target, attempts=10):
    """os.replace, retried briefly: under Windows a mere reader of target makes it fail with PermissionError."""
    for attempt in range(attempts):
        try:
            return os.replace(source, target)
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def write_new_file(name, data):
    """Write data into a file created exclusively at name; False if an entry already exists there."""
    try:
        fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0))
    except FileExistsError:
        return False
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def write_exclusive_temp(directory, base, data):
    """Create a new temporary file that never reuses a pre-existing entry; return its path."""
    for _ in range(8):
        name = Path(directory) / f'.{base}.{os.getpid()}.{secrets.token_hex(8)}.tmp'
        if write_new_file(name, data):
            return name
    raise StateError(f'could not create an exclusive temporary file in {directory}')


def checked_path(path):
    """Check the path as given (links and junctions are not followed first), then return it resolved."""
    given = Path(path).absolute()
    check_ancestors(given)
    check_state_file(given)
    return given.resolve()


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


def wave_identity(path, jpath):
    """Stable identity of a state file relative to its journal directory."""
    path, base = Path(path).resolve(), Path(jpath).resolve().parent
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


def journal_path(path, doc):
    path = Path(path).resolve()
    if kind_of(doc) == 'wave2' and relative_ref(doc.get('program_ref')):
        return (path.parent / doc['program_ref']).resolve().parent / 'journal.jsonl'
    return path.parent / 'journal.jsonl'


def append_journal(jpath, entry):
    """Append one line to a journal that is a regular, singly-linked file (created exclusively if absent)."""
    jpath = Path(jpath)
    problem = entry_problem(entry)
    if problem:  # never write a line that read_journal would declare damaged
        raise StateError(f'journal entry refused before writing: it {problem}')
    check_ancestors(jpath)
    line = (json.dumps(entry, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    flags = os.O_WRONLY | os.O_APPEND | getattr(os, 'O_BINARY', 0)
    try:
        if _is_link(os.lstat(jpath)):
            raise StateError(f'journal must not be a link or reparse point: {jpath}')
        fd = os.open(jpath, flags)
    except FileNotFoundError:
        fd = os.open(jpath, flags | os.O_CREAT | os.O_EXCL)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise StateError(f'journal refused: regular file with a single link required ({jpath}, links={st.st_nlink})')
        if st.st_size and unterminated_journal(jpath):
            line = b'\n' + line
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


JOURNAL_TEXT_FIELDS = ('kind', 'commits', 'resolves', 'applies_event', 'attaches_event', 'pending_applies_event',
                       'wave', 'file', 'op_kind', 'outcome', 'classification', 'tmp')


def entry_problem(entry):
    """Why a journal entry is unusable, or None; the same rule for writing and reading."""
    if not isinstance(entry, dict):
        return f'is a JSON {got(entry)}, not an entry object'
    if not text(entry.get('id')):
        return f'has no text id (got {got(entry.get("id"), "id" in entry)})'
    bad = [k for k in JOURNAL_TEXT_FIELDS if entry.get(k) is not None and not isinstance(entry[k], str)]
    if entry.get('journals') is not None and not (isinstance(entry['journals'], list)
                                                   and all(isinstance(x, str) for x in entry['journals'])):
        bad.append('journals')
    return 'has malformed fields: ' + ', '.join(f'{k} ({got(entry[k])})' for k in bad) if bad else None


def journal_line_error(jpath, number, why):
    return StateError(f'journal {jpath} line {number} {why} (interrupted write?); move the damaged line aside with its '
                      'evidence before any other action')


def read_journal(jpath):
    if not Path(jpath).is_file():
        return []
    entries = []
    for number, raw in enumerate(Path(jpath).read_bytes().split(b'\n'), 1):
        try:
            line = raw.decode('utf-8')
        except UnicodeDecodeError:
            raise journal_line_error(jpath, number, 'is not valid UTF-8')
        if not line.strip():
            continue
        try:
            entry = strict_json(line)
        except ValueError:
            raise journal_line_error(jpath, number, 'is not valid JSON')
        problem = entry_problem(entry)
        if problem:
            raise journal_line_error(jpath, number, problem)
        entries.append(entry)
    return entries


def unterminated_journal(jpath):
    """True when the journal ends with a complete entry but no line feed; the next append terminates it first."""
    try:
        with open(jpath, 'rb') as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                return False
            stream.seek(-1, os.SEEK_END)
            return stream.read(1) != b'\n'
    except FileNotFoundError:
        return False


def _carry_events_on_attach(old_j, new_j, entries, idents, actor, file_name):
    """First attachment of a wave to its program. Only events explicitly belonging to this wave (received with its
    identity, or legacy receipts attached to it by event --attach-legacy) are carried, as applied, into the program
    journal. A legacy receipt without identity that may concern this file blocks until it is attached with evidence;
    receipts known to belong to another file are left to that file."""
    statuses = _event_status(entries[old_j])
    legacy = sorted(k for k, v in statuses.items()
                    if v['wave'] is None and v['received'].get('file') in (None, file_name))
    if legacy:
        raise StateError('attach refused: legacy events without wave identity may concern this file; attach each one '
                         'to its wave with event --attach-legacy --evidence first: ' + ', '.join(legacy))
    own = {k: v for k, v in statuses.items() if v['wave'] == idents[old_j]}
    unsettled = sorted(k for k, v in own.items() if not v['applied'] or v.get('uncertain'))
    if unsettled:
        raise StateError('attach refused: local events not yet applied or disposed: ' + ', '.join(unsettled))
    shared = _event_status(entries[new_j])
    for event_id, status in sorted(own.items()):
        if event_id in shared:
            if shared[event_id]['wave'] != idents[new_j]:
                raise StateError(f'attach refused: event id {event_id} already belongs to {shared[event_id]["wave"]}')
            continue
        append_journal(new_j, {'id': event_id, 'at': now(), 'kind': 'event:carried', 'wave': idents[new_j],
                               'classification': 'carried', 'actor': actor, 'carried_from': str(old_j),
                               'original_wave': status['wave'], 'original_kind': status['received'].get('kind')})


def local_journal(path):
    return Path(path).resolve().parent / 'journal.jsonl'


def participating_journals(path, doc):
    """Journals that may hold an operation on this state file: its current journal, its local journal, and every
    journal listed by a prepare of this file found there (open or closed)."""
    path = Path(path).resolve()
    found = {journal_path(path, doc), local_journal(path)}
    for j in list(found):
        for e in read_journal(j):
            if e.get('kind') == 'prepare' and e.get('wave') == wave_identity(path, j):
                listed = ((path.parent / x).resolve() for x in e.get('journals') or [])
                found.update(x for x in listed if x.is_file())  # a moved or removed folder holds nothing open
    return sorted(found, key=str)


def journal_refs(path, journals):
    """Journals named relative to the state file directory, so that moving the folder keeps them valid."""
    out = []
    for j in journals:
        try:
            out.append(os.path.relpath(j, Path(path).parent).replace(os.sep, '/'))
        except ValueError:  # another drive
            out.append(str(j))
    return out


def open_operations(path, journals):
    """(journal, prepare) pairs still open for this state file in the given journals."""
    return [(j, op) for j in journals for op in _unresolved_ops(read_journal(j), wave_identity(path, j))]


def _unresolved_ops(entries, ident=None):
    """Prepared state replacements with no commit or resolution entry."""
    closed = {e.get('commits') for e in entries} | {e.get('resolves') for e in entries}
    return [e for e in entries if e.get('kind') == 'prepare' and e.get('id') not in closed
            and (ident is None or e.get('wave') == ident)]


def guarded_write(path, actor, expected_revision, mutate, kind='write', detail=None, owner_check=True,
                  owner_change=False, applies_event=None):
    path = checked_path(path)
    with Lock(path):
        old_bytes = path.read_bytes()
        old = strict_json(old_bytes.decode('utf-8-sig'))
        if kind_of(old) not in {'program', 'wave2'}:
            raise StateError('guarded writes need a program or a v2 wave; migrate v1 first')
        if old.get('revision') != expected_revision:
            raise StateError(f'revision conflict: expected {expected_revision}, found {old.get("revision")}; '
                             're-read and reconcile before retrying')
        owner = owner_ref(old) if owner_check else None
        if owner_check and owner is None:
            raise StateError('no owner recorded: claim ownership first')
        if owner_check and owner != actor:
            raise StateError(f'actor {actor} is not the owner ({owner}); hand the need to the owner')
        new = mutate(copy.deepcopy(old))
        new['revision'] = old['revision'] + 1
        reset = launch_context_changes(old, new) if kind_of(old) == 'wave2' else []
        if reset:
            new['state']['launch_ready'] = False
        errors = validate_any(new, path.parent, check_paths=False, self_path=path)
        inherited = []
        if owner_change:  # a takeover is refused only for what it changes: inconsistencies already there stay reported
            before = validate_any(old, path.parent, check_paths=False, self_path=path)
            inherited = [e for e in errors if e in before]
            errors = [e for e in errors if e not in before]
        if not errors:
            errors = check_evolution(old, new, owner_change=owner_change, applies_event=applies_event)
        if errors:
            raise StateError('refused: ' + '; '.join(errors))
        old_j, new_j = journal_path(path, old), journal_path(path, new)
        attaching = old_j != new_j  # only when program_ref is first set
        participants = sorted(set(participating_journals(path, old)) | {new_j}, key=str)
        jpaths = [old_j]  # the operation has a single copy, in the journal of the current state
        idents = {j: wave_identity(path, j) for j in participants}
        with contextlib.ExitStack() as stack:
            for j in participants:  # all participating journal locks held before the commit
                stack.enter_context(Lock(j))
            entries = {j: read_journal(j) for j in participants}
            for j in participants:
                pending_ops = _unresolved_ops(entries[j], idents[j])
                if pending_ops:
                    raise StateError(f'unresolved state operation {pending_ops[0]["id"]} on {idents[j]} ({j}): its '
                                     'effect may be committed without journal; run reconcile before any other write')
            if attaching:
                if applies_event is not None:
                    raise StateError('apply events before or after attaching the wave to its program, not in the same write')
                _carry_events_on_attach(old_j, new_j, entries, idents, actor, path.name)
            jpath, ident = old_j, idents[old_j]
            if applies_event is not None:
                status = _event_status(entries[jpath]).get(applies_event)
                if status is None:
                    raise StateError(f'event {applies_event} was never received; record it with event first')
                if status['wave'] is None:
                    raise StateError(f'event {applies_event} has no wave identity (journal written by an older tool); '
                                     'attach it first with event --attach-legacy --evidence')
                if status['wave'] != ident:
                    raise StateError(f'event {applies_event} was received for {status["wave"]}, not for {ident}')
                if status['applied']:
                    raise StateError(f'event {applies_event} is already applied')
                seq = status['received'].get('candidate_seq')
                current = old['candidate'].get('seq') if isinstance(old.get('candidate'), dict) else None
                if type(seq) is int and type(current) is int and seq < current:
                    raise StateError(f'event {applies_event} was received for candidate_seq {seq}, older than the current '
                                     f'candidate {current}: it is stale and applies to nothing; record it as stale with '
                                     f'event --id {applies_event}')
            new_bytes = (json.dumps(new, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
            op_id = f'op:{ident}:{new["revision"]}:{secrets.token_hex(4)}'
            tmp = write_exclusive_temp(path.parent, path.name, new_bytes)
            recorded = []
            for j in jpaths:  # the journal of the current state first: it is the one later writes consult
                try:
                    append_journal(j, {'id': op_id, 'at': now(), 'kind': 'prepare', 'op_kind': kind, 'file': path.name,
                                       'wave': idents[j], 'actor': actor, 'previous_owner': previous_owner(old),
                                       'from_revision': old['revision'], 'revision': new['revision'],
                                       'old_sha256': hashlib.sha256(old_bytes).hexdigest(),
                                       'new_sha256': hashlib.sha256(new_bytes).hexdigest(), 'tmp': tmp.name,
                                       'pending_applies_event': applies_event, 'journals': journal_refs(path, jpaths)})
                    recorded.append(j)
                except (OSError, StateError) as exc:
                    if not recorded:
                        os.unlink(tmp)
                        raise
                    raise OpenOperation(f'operation {op_id} prepared in {recorded[0]} only ({exc}); state not replaced: '
                                        'run reconcile before any other write')
            try:
                replace_file(tmp, path)
            except OSError as exc:
                raise OpenOperation(f'operation {op_id} prepared but the state replacement failed ({exc}): '
                                    'run reconcile before any other write')
            for j in jpaths:
                try:
                    append_journal(j, {'id': f'write:{idents[j]}:{new["revision"]}', 'at': now(), 'kind': kind,
                                       'file': path.name, 'wave': idents[j], 'actor': actor, 'revision': new['revision'],
                                       'detail': detail, 'applies_event': applies_event if j == jpath else None,
                                       'commits': op_id})
                except (OSError, StateError) as exc:
                    raise OpenOperation(f'state committed at revision {new["revision"]} but its journal commit failed in '
                                        f'{j}: {exc}; operation {op_id} stays unresolved: run reconcile before any other '
                                        'action')
        result = {'written': str(path), 'revision': new['revision']}
        if inherited:
            result['consistency_errors'] = inherited
        if reset:
            result['launch_ready_reset'] = {'changed': reset, 'effect': 'launch_ready set to false by this write; '
                                            'the owner sets it to true again once the launch conditions hold'}
        return result


# ---------------------------------------------------------------- commands

def cmd_check(args):
    path = Path(args.file).resolve()
    doc = load(path)
    errors = validate_any(doc, path.parent, args.check_paths, self_path=path)
    result = {'valid': not errors, 'kind': kind_of(doc), 'errors': errors, 'limits': LIMITS}
    if kind_of(doc) in CLOSED_KEYS:
        result['unknown_keys'] = unknown_keys(doc)
    return result, bool(errors)


def cmd_ready(args):
    path = Path(args.program).resolve()
    doc = load(path)
    if kind_of(doc) != 'program':
        raise StateError('ready needs a program.json')
    errors = validate_program(doc, path.parent, self_path=path)
    return dict(ready_view(doc), consistency_errors=errors), bool(errors)


def _event_status(entries):
    """Map event id -> {'received', 'applied', 'wave'}; 'wave' may come from a sourced legacy attachment."""
    status = {}
    for e in entries:
        kind = str(e.get('kind', ''))
        if kind.startswith('event:'):
            status.setdefault(e['id'], {'received': e, 'applied': e.get('classification') in {'stale', 'late', 'carried'},
                                        'wave': e.get('wave')})
        if kind == 'attach' and e.get('attaches_event') in status and status[e['attaches_event']]['wave'] is None:
            status[e['attaches_event']]['wave'] = e.get('wave')
        if e.get('applies_event') in status:
            status[e['applies_event']]['applied'] = True
    for op in _unresolved_ops(entries):
        event = op.get('pending_applies_event')
        if event in status and not status[event]['applied']:
            status[event]['uncertain'] = op['id']
    return status


def cmd_resume(args):
    program_path = Path(args.program).resolve()
    doc = load(program_path)
    if kind_of(doc) != 'program':
        raise StateError('resume needs a program.json')
    errors = validate_program(doc, program_path.parent, self_path=program_path)
    jpath = program_path.parent / 'journal.jsonl'
    successor = 'a successor first takes the file with claim --takeover --evidence'
    actions, waves, ops, known = [], [], [], {}  # known: (journal, identity) -> wave group
    shared = {}  # resolved wave file -> its group: one entry and one set of actions per wave
    for o in _items(doc.get('outcomes')):
        ref = o.get('state_ref')
        if text(ref) and local_path(ref) and (program_path.parent / ref).resolve().is_file():
            target = (program_path.parent / ref).resolve()
            shared.setdefault(target, {'ref': ref, 'outcomes': [], 'file': target})['outcomes'].append(o)
    for target, group in shared.items():
        wave = group['wave'] = load(target)
        ref, ids = group['ref'], [o.get('id') for o in group['outcomes']]
        state = wave.get('state') if isinstance(wave.get('state'), dict) else {}
        phase = group['phase'] = sval(state, 'phase')
        group['ident'] = wave_identity(target, jpath)
        pending = [i for i in _items(wave.get('intents')) if sval(i, 'status') == 'pending']
        live = [a for a in _items(wave.get('actors')) if sval(a, 'status') in LIVE_ACTOR]
        waves.append({'outcomes': ids, 'wave': ref, 'schema_version': wave.get('schema_version'), 'phase': phase,
                      'revision': wave.get('revision'), 'owner': state.get('owner'), 'candidate': wave.get('candidate'),
                      'waiting': state.get('waiting'), 'next_action': state.get('next_action'),
                      'pending_intents': pending, 'live_actors': live,
                      'legacy_runtime_refs': state.get('legacy_runtime_refs') or state.get('runtime_refs')
                      if kind_of(wave) == 'wave1' else state.get('legacy_runtime_refs')})
        label = f'{ref} (outcomes {", ".join(map(str, ids))})'
        if kind_of(wave) == 'wave2':
            group['journal'] = journal_path(target, wave)
            known[(group['journal'], wave_identity(target, group['journal']))] = group
            ops += open_operations(target, participating_journals(target, wave))
        else:
            known[(jpath, group['ident'])] = group
        for intent in pending:
            actions.append(f'{label}: reconcile intent {intent["correlation"]} ({intent["op"]} {intent["target"]}) '
                           'by reading the real runtime/file state before any retry')
        for actor in live:
            actions.append(f'{label}: actor {actor["correlation"]} ref {actor.get("ref")} status {actor["status"]}: '
                           'confirm from a delivered signal or a targeted read; do not relaunch while it may be alive')
        if kind_of(wave) == 'wave1' and phase not in {'completed', 'completed_partial'}:
            actions.append(f'{label}: v1 registry (runtime_refs {state.get("runtime_refs")}); reconcile them, '
                           'migrate to a new file at a stable wave boundary')
        for o in group['outcomes']:
            if sval(o, 'status') == 'admitted' and phase in TERMINAL_PHASES:
                actions.append(f'{label}: wave is {phase} but outcome {o.get("id")} is still admitted: record its '
                               f'outcome in the index (write {program_path.name} --ops update outcomes match id); '
                               f'{successor}')
    journal = read_journal(jpath)
    ops += open_operations(program_path, participating_journals(program_path, doc))
    ops += [(jpath, op) for op in _unresolved_ops(journal)]
    uncertain = {}
    for j, op in ops:
        uncertain.setdefault((op['id'], str(Path(j).resolve())),
                             dict(op, journal=str(j), state_file=str(Path(j).parent / str(op.get('wave')))))
    uncertain = list(uncertain.values())
    for op in uncertain:
        actions.insert(0, f'uncertain state operation {op["id"]} (revision {op.get("revision")}, event '
                          f'{op.get("pending_applies_event")}): run reconcile {op["state_file"]} --actor <you> '
                          f'--op {op["id"]} --evidence "..." before any other write of that file; its bytes decide the '
                          f'outcome for any actor, then {successor} if its owner stopped')
    unapplied = []
    for j in [jpath] + sorted({g['journal'] for g in shared.values() if 'journal' in g} - {jpath}, key=str):
        for status in _event_status(journal if j == jpath else read_journal(j)).values():
            group = known.get((j, status['wave']))
            if status['applied'] or status.get('uncertain') or (j != jpath and not group and status['wave']):
                continue
            event = dict(status['received'], wave=group['ident'] if group else status['wave'])
            unapplied.append(event)
            name = f'event {event["id"]} ({event.get("kind")})'
            cand = group['wave'].get('candidate') if group else None
            seq, current = event.get('candidate_seq'), cand.get('seq') if isinstance(cand, dict) else None
            if event['wave'] is None:
                actions.append(f'{name} was received by an older tool without wave identity and never applied: '
                               'establish its wave, attach it (event --attach-legacy), then process it')
            elif group and group['phase'] in TERMINAL_PHASES:
                actions.append(f'{name} received for {event["wave"]}, now {group["phase"]}, was never applied: dispose '
                               f'{group["file"]} --actor <owner> --id {event["id"]} --disposition '
                               f'late|handled_elsewhere|not_applicable --evidence "..." (the wave stays closed); '
                               f'{successor}')
            elif type(seq) is int and type(current) is int and seq < current:
                actions.append(f'{name} was received for candidate_seq {seq}, older than the current candidate '
                               f'{current}: record it as stale with event {group["file"]} --actor <owner> --id '
                               f'{event["id"]} --kind {str(event.get("kind"))[len("event:"):]}')
            else:
                actions.append(f'{name} for {event["wave"]} was received but never applied: process it on that wave now')
    view = ready_view(doc)
    if view['ready']:
        actions.append('ready outcomes (engage those not tied to a pending intent or unknown actor while '
                       'reconciling the others): ' + ', '.join(view['ready']))
    for dec in _items(doc.get('decisions_pending')):
        actions.append(f'decision {dec.get("id")} pending: {dec.get("question")} (suspends {dec.get("suspends")})')
    if errors:
        actions.insert(0, 'consistency errors must be reconciled before using this summary to launch anything')
    actions = list(dict.fromkeys(actions))  # same text once, first position kept
    return {'owner': doc.get('owner'), 'status': sval(doc, 'status'), 'revision': doc.get('revision'),
            'last_milestone': doc.get('last_milestone'), 'ready': view, 'waves': waves,
            'unapplied_events': unapplied, 'uncertain_operations': uncertain, 'journal_entries': len(journal),
            'consistency_errors': errors, 'actions': actions, 'limits': LIMITS}, bool(errors or uncertain)


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
        stream.write(json.dumps(new, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return {'migrated': str(dest), 'from_sha256': new['migrated_from']['sha256'],
            'unknown_actors': [a['correlation'] for a in new['actors']]}, False


# ---------------------------------------------------------------- init

INIT_REASON = 'initialized by rc_state.py init'
OUTCOME_DEFAULTS = {'depends_on': [], 'status': 'pending', 'state_ref': None, 'waiting_on': None, 'resources': []}
SOCLE_DEFAULTS = {'depends_on': [], 'resources': [], 'source_refs': []}
REVIEW_DEFAULTS = {'disposition': None, 'reference': None}
ITEM_DEFAULTS = {('program', 'outcomes'): OUTCOME_DEFAULTS, ('wave2', 'socles'): SOCLE_DEFAULTS,
                 ('wave2', 'reviews'): REVIEW_DEFAULTS}


def with_item_defaults(item, defaults):
    """List item completed with the defaults init applies to its missing fields."""
    if not (defaults and isinstance(item, dict)):
        return item
    return {**item, **{k: copy.deepcopy(v) for k, v in defaults.items() if k not in item}}


INIT_TEMPLATES = {
    'program': {
        'mandate': {'ref': 'required: nonempty text', 'sha256': 'optional: 64 hex characters',
                    'scope': 'required: list of strings', 'exclusions': 'required: list of strings (may be empty)',
                    'end_criteria': 'required: nonempty text'},
        'outcomes': [{'id': 'required: nonempty text, unique', 'outcome': 'required: nonempty text',
                      'next_action': 'required: nonempty text',
                      'depends_on': 'default []: list of outcome ids',
                      'status': 'default "pending": one of ' + ', '.join(sorted(OUTCOME_STATUSES)),
                      'state_ref': 'default null: null or local relative path of a wave.json (required when admitted; '
                                   'accepted or accepted_partial needs it, or a closure for an acceptance outside '
                                   'any wave)',
                      'waiting_on': 'default null: null or {kind: one of ' + ', '.join(sorted(WAIT_KINDS)) +
                                    ', detail: text, trigger: text}',
                      'resources': 'default []: list of strings',
                      'closure': 'when accepted_partial, abandoned or failed, or accepted without state_ref: '
                                 '{source: text, remaining: text}'}],
        'skills_consumed': 'default []: list of {name: text, sha256: 64 hex of its SKILL.md}',
        'status': 'default "active": one of ' + ', '.join(sorted(PROGRAM_STATUSES)),
        'status_reason': f'default "{INIT_REASON}": nonempty text',
        'decisions_pending': 'default []: list of {id, question, option, effects: text, suspends: list of outcome ids, '
                             'empty for a decision that suspends nothing and does not prevent completion}',
        'last_milestone': 'default null: null or {at, summary, ref: text}'},
    'wave': {
        'mode': 'default "prepare": one of prepare, prepare-and-launch',
        'project': {k: 'default null: text or null' for k in ('root', 'baseline', 'observed_at')},
        'authorization': {'launch': 'default false: bool (true needs prepare-and-launch and a source)',
                          'source': 'default null: text or null', 'scope': 'default null: list of strings or null',
                          'exclusions': 'required: list of strings (may be empty)'},
        'socles': [{'id': 'required: nonempty text, unique', 'outcome': 'required: nonempty text',
                    'readiness': 'required: one of blocked, partial, ready',
                    'depends_on': 'default []: list of socle ids', 'resources': 'default []: list',
                    'source_refs': 'default []: list', 'prompt_artifact': 'required before launch_ready=true: key of artifacts naming the champion mandate',
                    'ready_scope': 'text, required when partial', 'blocked_scope': 'text, required when partial',
                    'consumption_dependencies': 'optional: list of {producer, artifact, consumer_scope, continue_scope}'}],
        'batches': 'default []: list of lists of socle ids',
        'artifacts': 'default {}: object name -> local relative path',
        'reviews': 'default []: list of {artifact: key of artifacts, sha256: 64 hex, status: one of ' +
                   ', '.join(sorted(v1.REVIEW_STATUSES)) + ', disposition: default null: text or null, reference: '
                   'default null: text or null (both text when status is done or not_required), '
                   'candidate_seq: null (documentary review) or the seq of a frozen candidate, 1 to the current seq}',
        'decisions': 'default []: list of strings',
        'envelope': 'default null: null or {reason: text, ...}',
        'state': {'next_action': 'required: nonempty text', 'blockers': 'default []: list of strings',
                  'consumed': 'default {}: object artifact -> {version: text, sha256: 64 hex}'}},
}
INIT_SET = {
    'program': {'schema': PROGRAM_SCHEMA, 'revision': 0, 'owner': '{role: --role, ref: --actor}'},
    'wave': {'schema_version': 2, 'revision': 0, 'program_ref': None,
             'candidate': 'null; frozen later with write: {seq: int >= 1, increasing; ref: text, exact reference of the '
                          'frozen candidate (commit SHA, branch@SHA or manifest name); artifact: key of artifacts naming '
                          'its manifest; sha256: 64 hex of that artifact}',
             'actors': [], 'intents': [],
             'state.phase': 'planning', 'state.owner': '{role: --role, ref: --actor}', 'state.launch_ready': False,
             'state.waiting': None, 'state.runtime_refs': None},
}


def init_template(kind):
    return {'kind': kind, 'command': f'init FILE --kind {kind} --actor REF --role ROLE --spec SPEC.json',
            'spec': INIT_TEMPLATES[kind], 'set_by_init': INIT_SET[kind],
            'note': 'SPEC is a partial document: give the required fields, omit defaults you accept. A field set by '
                    'init may appear in SPEC only with the value init sets. Unknown value: null, never a plausible '
                    'identifier. Later changes go through claim, write, transition, intent.'}


def build_initial(kind, spec, actor, role):
    """Complete a partial spec with structural fields; refuse missing business fields by name."""
    if not isinstance(spec, dict):
        raise StateError(f'spec must be a JSON object, got {got(spec)}')
    owner = {'role': role, 'ref': actor}
    if kind == 'program':
        managed = {'schema': PROGRAM_SCHEMA, 'revision': 0, 'owner': owner}
        defaults = {'skills_consumed': [], 'status': 'active', 'status_reason': INIT_REASON,
                    'decisions_pending': [], 'last_milestone': None}
        nested = {}
    else:
        managed = {'schema_version': 2, 'revision': 0, 'program_ref': None, 'candidate': None, 'actors': [], 'intents': []}
        defaults = {'mode': 'prepare', 'socles': [], 'batches': [], 'artifacts': {}, 'reviews': [], 'decisions': [],
                    'envelope': None}
        nested = {'project': ({'root': None, 'baseline': None, 'observed_at': None}, {}),
                  'authorization': ({'launch': False, 'source': None, 'scope': None}, {}),
                  'state': ({'blockers': [], 'consumed': {}},
                            {'phase': 'planning', 'owner': owner, 'launch_ready': False, 'waiting': None,
                             'runtime_refs': None})}
    def differs(a, b):
        return type(a) is not type(b) or a != b
    fixed = [k for k, v in managed.items() if k in spec and differs(spec[k], v)]
    fixed += ['migrated_from'] if 'migrated_from' in spec else []
    for key, (_, values) in nested.items():
        part = spec.get(key)
        if isinstance(part, dict):
            fixed += [f'{key}.{k}' for k, v in values.items() if k in part and differs(part[k], v)]
    if fixed:
        raise StateError('init sets these fields itself; remove them from the spec: ' + ', '.join(fixed) +
                         f' (see init --template {kind})')
    missing = []

    def need(obj, prefix, keys):
        obj = {} if obj is None else obj
        if isinstance(obj, dict):
            missing.extend(f'{prefix}.{k}' for k in keys if k not in obj)

    if kind == 'program':
        need(spec.get('mandate'), 'mandate', ('ref', 'scope', 'exclusions', 'end_criteria'))
        if 'outcomes' not in spec:
            missing.append('outcomes')
        for index, outcome in enumerate(spec.get('outcomes') if isinstance(spec.get('outcomes'), list) else []):
            need(outcome, f'outcomes[{index}]', ('id', 'outcome', 'next_action'))
    else:
        need(spec.get('authorization'), 'authorization', ('exclusions',))
        need(spec.get('state'), 'state', ('next_action',))
        for index, socle in enumerate(spec.get('socles') if isinstance(spec.get('socles'), list) else []):
            need(socle, f'socles[{index}]', ('id', 'outcome', 'readiness'))
    if missing:
        raise StateError('init needs these business fields, absent from the spec (init never invents them): ' +
                         ', '.join(missing) + f' (see init --template {kind})')
    doc = copy.deepcopy(managed)
    doc.update(copy.deepcopy(defaults))
    doc.update({key: copy.deepcopy(base) for key, (base, _) in nested.items()})
    doc.update(copy.deepcopy(spec))
    for key, (base, values) in nested.items():
        if isinstance(doc[key], dict):
            doc[key] = {**copy.deepcopy(base), **doc[key], **copy.deepcopy(values)}
    for item_kind, defaults in ITEM_DEFAULTS.items():
        if item_kind[0] == kind_of(managed) and isinstance(doc.get(item_kind[1]), list):
            doc[item_kind[1]] = [with_item_defaults(item, defaults) for item in doc[item_kind[1]]]
    doc.update(copy.deepcopy(managed))
    return doc


def replaceable_state(path, actor, kind):
    """Old state that init --replace-invalid may replace: readable, invalid, revision 0, no owner but the actor."""
    old_bytes = path.read_bytes()
    try:
        old = strict_json(old_bytes.decode('utf-8-sig'))
    except ValueError as exc:
        raise StateError(f'--replace-invalid refused: {path.name} is not readable JSON ({exc}); its revision and owner '
                         'cannot be checked: move it aside yourself with its evidence, then run init')
    if not isinstance(old, dict):
        raise StateError(f'--replace-invalid refused: {path.name} is not a JSON object; move it aside yourself, then run init')
    old_kind, expected = kind_of(old), ('program' if kind == 'program' else 'wave2')
    if old_kind not in {expected, 'unknown'}:
        raise StateError(f'--replace-invalid refused: {path.name} is a {old_kind} document, not a {kind}')
    errors = validate_any(old, path.parent, check_paths=False, self_path=path)
    if not errors:
        raise StateError(f'--replace-invalid refused: {path.name} is valid; change it with claim, write or transition')
    if type(old.get('revision')) is not int or old['revision'] != 0:
        raise StateError(f'--replace-invalid refused: revision is {old.get("revision")!r}, not 0; only an initial '
                         'state never written by the tool can be replaced')
    state = old.get('state') if isinstance(old.get('state'), dict) else {}
    owners = [value for value in (old.get('owner'), state.get('owner')) if value is not None]
    for value in owners:
        if not (isinstance(value, dict) and value.get('ref') == actor):
            raise StateError(f'--replace-invalid refused: {path.name} has an owner other than {actor} ({value!r}); '
                             'only that owner may replace it')
    return {'bytes': old_bytes, 'errors': errors, 'previous_owner': actor if owners else None}


def preserve_copy(path, data):
    """Byte-identical copy of a replaced state under a new exclusive name <stem>.invalid-<n><suffix>."""
    for number in range(1, 1000):
        name = path.with_name(f'{path.stem}.invalid-{number}{path.suffix}')
        if write_new_file(name, data):
            return name
    raise StateError(f'no free name to preserve {path.name}; nothing replaced')


def create_exclusive(tmp, path):
    """Publish tmp at path only if path does not exist (hard link, or Windows rename which never replaces)."""
    try:
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise
        except OSError:
            if os.name != 'nt':
                raise
            os.rename(tmp, path)
            return
        os.unlink(tmp)
    except FileExistsError:
        os.unlink(tmp)
        raise StateError(f'{path} appeared during init: nothing written')
    except OSError:
        if tmp.exists():
            os.unlink(tmp)
        raise


def check_journal_writable(jpath):
    """Refuse, before any publication, a journal that append_journal would refuse (link, reparse point, hard links)."""
    jpath = Path(jpath)
    check_ancestors(jpath)
    try:
        st = os.lstat(jpath)
    except FileNotFoundError:
        return
    if _is_link(st) or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise StateError(f'journal refused before any write: regular file with a single link required '
                         f'({jpath}, links={st.st_nlink})')


def state_history(path, journals):
    """(journal, entry) of the first record about this state file, or None. An init whose prepare was resolved
    not_committed left no state and does not count."""
    local = local_journal(path)
    for j in journals:
        ident = wave_identity(path, j)
        entries = read_journal(j)
        inits = {e.get('id') for e in entries if e.get('kind') == 'prepare' and e.get('op_kind') == 'init'
                 and e.get('wave') == ident}
        void = inits & {e.get('resolves') for e in entries
                        if e.get('kind') == 'resolve' and e.get('outcome') == 'not_committed'}
        for e in entries:
            mine = e.get('wave') == ident or (e.get('wave') is None and j == local and e.get('file') == path.name)
            if mine and e.get('id') not in void and e.get('resolves') not in void:
                return j, e
    return None


def cmd_init(args):
    if args.template:
        return init_template(args.template), False
    doc = build_initial(args.kind, load(args.spec) if args.spec else {}, args.actor, args.role)
    given = Path(args.file).absolute()
    check_ancestors(given)
    if not given.parent.is_dir():
        raise StateError(f'directory not found: {given.parent}')
    path = given.parent.resolve() / given.name
    exists = os.path.lexists(given)
    if exists and not args.replace_invalid:
        raise StateError(f'{path} exists: init never overwrites. An invalid revision-0 state without owner (or owned '
                         'by the actor) can be replaced with --replace-invalid --evidence')
    if args.replace_invalid and not exists:
        raise StateError(f'--replace-invalid: no file to replace at {path}; run init without it')
    if exists:
        check_state_file(given)
    errors = validate_any(doc, path.parent, check_paths=False, self_path=path)
    errors += [f'unknown key {key}' for key in unknown_keys(doc)]
    if errors:
        raise StateError('refused: initial state invalid: ' + '; '.join(errors))
    new_bytes = (json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    jpath = journal_path(path, doc)
    with Lock(path):
        old = replaceable_state(path, args.actor, args.kind) if exists else None
        journals = set(participating_journals(path, doc)) | {jpath}
        if old is not None:
            try:
                journals |= set(participating_journals(path, strict_json(old['bytes'].decode('utf-8-sig'))))
            except (StateError, TypeError, AttributeError):
                pass
        journals = sorted(journals, key=str)
        with contextlib.ExitStack() as stack:
            for j in journals:  # all participating journal locks held, as for guarded writes
                stack.enter_context(Lock(j))
            ident = wave_identity(path, jpath)
            check_journal_writable(jpath)  # before any copy, temporary or publication
            pending_ops = open_operations(path, journals)
            if pending_ops:
                raise StateError(f'unresolved state operation {pending_ops[0][1]["id"]} on {ident} ({pending_ops[0][0]}): '
                                 'run reconcile first')
            history = state_history(path, journals)
            if history and old is None:
                raise StateError(f'journal {history[0]} already records operations on {ident} but the file is missing: '
                                 'restore its last known version instead of re-creating it')
            if history:
                raise StateError(f'--replace-invalid refused: journal {history[0]} already records operations on {ident} '
                                 f'({history[1].get("kind")} {history[1].get("id")}): this state went through the tool; '
                                 'reconcile its inconsistency (check, then write under its owner) instead of '
                                 're-initializing it')
            preserved = preserve_copy(path, old['bytes']) if old is not None else None
            replaced = None if old is None else {
                'preserved_as': preserved.name, 'old_sha256': hashlib.sha256(old['bytes']).hexdigest(),
                'old_errors': old['errors'], 'previous_owner': old['previous_owner'], 'evidence': args.evidence}
            new_sha = hashlib.sha256(new_bytes).hexdigest()
            token = secrets.token_hex(4)
            op_id = f'op:{ident}:0:{token}'
            tmp = write_exclusive_temp(path.parent, path.name, new_bytes)
            try:
                append_journal(jpath, {'id': op_id, 'at': now(), 'kind': 'prepare', 'op_kind': 'init', 'file': path.name,
                                       'wave': ident, 'actor': args.actor, 'role': args.role, 'state_kind': args.kind,
                                       'previous_owner': None, 'from_revision': None, 'revision': 0,
                                       'old_sha256': replaced['old_sha256'] if replaced else None,
                                       'new_sha256': new_sha, 'tmp': tmp.name, 'pending_applies_event': None,
                                       'journals': journal_refs(path, [jpath]), 'replaces': replaced})
            except (OSError, StateError):
                os.unlink(tmp)
                raise
            try:
                if old is not None:
                    replace_file(tmp, path)
                else:
                    create_exclusive(tmp, path)
            except (OSError, StateError) as exc:  # not published: remove only our own temporary, keep the evidence copy
                if tmp.is_file() and not _is_link(os.lstat(tmp)) and \
                        hashlib.sha256(tmp.read_bytes()).hexdigest() == new_sha:
                    os.unlink(tmp)
                raise StateError(f'init not published ({exc}); own temporary removed' +
                                 (f', evidence copy kept as {preserved.name}' if preserved else '') +
                                 f'; operation {op_id} stays open: run reconcile --op {op_id} --evidence, then retry')
            try:
                append_journal(jpath, {'id': f'init:{ident}:0:{token}', 'at': now(), 'kind': 'init', 'file': path.name,
                                       'wave': ident, 'actor': args.actor, 'role': args.role, 'state_kind': args.kind,
                                       'revision': 0, 'new_sha256': new_sha, 'replaces': replaced, 'commits': op_id})
            except (OSError, StateError) as exc:
                raise StateError(f'{path} published at revision 0 but its journal commit failed in {jpath}: {exc}; '
                                 f'operation {op_id} stays unresolved: run reconcile before any other action')
    return {'written': str(path), 'revision': 0, 'kind': args.kind, 'owner': args.actor, 'journal': str(jpath),
            'operation': op_id, 'replaced': replaced}, False


def read_ops(args):
    try:
        ops = load(args.ops_file) if args.ops_file else strict_json(args.ops) if args.ops is not None else None
    except (OSError, ValueError) as exc:
        raise StateError(f'--ops{"-file" if args.ops_file else ""} unreadable or not valid JSON: {exc}')
    if (args.ops_file or args.ops is not None) and not (isinstance(ops, list) and ops):
        raise StateError(f'ops must be a nonempty list, got {got(ops)}')
    return ops


def cmd_write(args):
    def mutate(doc):
        mid = resolve_intent(doc, args.resolve_intent, args) if args.resolve_intent else doc
        new = apply_ops(mid, ops) if ops else mid
        created = [k for k in unknown_keys(new) if k not in unknown_keys(doc)]
        if created:
            raise StateError(f'refused: unknown key {", ".join(created)}: the {kind_of(doc)} format does not define it. '
                             'A path joins object keys with ".", never "/" (state.next_action, not state/next_action); '
                             'see write --help and init --template')
        if mid is not doc and ops:
            resolved = [i for i in _items(mid.get('intents')) if i.get('correlation') == args.resolve_intent]
            if resolved != [i for i in _items(new.get('intents')) if i.get('correlation') == args.resolve_intent]:
                raise StateError(f'refused: ops after the intent resolution: intent {args.resolve_intent} is resolved '
                                 'and immutable')
        return new

    event, applies = None, args.applies_event
    if args.record_event:
        event, _ = cmd_event(argparse.Namespace(file=args.file, actor=args.actor, id=args.record_event, kind=args.kind,
                                                candidate_seq=args.candidate_seq, detail=None, attach_legacy=False,
                                                evidence=None))
        if event['classification'] not in {'new', 'unapplied'} or event.get('wave_phase') in TERMINAL_PHASES:
            return {'event': event, 'written': None}, True
        applies = args.record_event
    detail = {'reason': args.reason, 'correlation': args.resolve_intent, 'status': args.status} \
        if args.resolve_intent else args.reason
    try:
        ops = read_ops(args)
        result = guarded_write(args.file, args.actor, args.expect_revision, mutate, detail=detail, applies_event=applies)
    except OpenOperation as exc:
        if event is None:
            raise
        raise OpenOperation(f'{exc}; event {args.record_event} is now uncertain: run reconcile, do not rerun this '
                            'command')
    except StateError as exc:
        if event is None:
            raise
        raise StateError(f'{exc}; event {args.record_event} is recorded and stays unapplied: rerun this command '
                         'once the cause is fixed')
    if event:
        event = dict(event, applied=True, effect=f'applied by this write (revision {result["revision"]})')
    return dict(result, event=event) if event else result, False


def cmd_claim(args):
    previous = {}

    def mutate(doc):
        try:
            current, malformed = owner_ref(doc), False
        except MalformedOwner:
            current, malformed = previous_owner(doc), True
        previous['owner'] = current
        if (malformed or current not in (None, args.actor)) and not (args.takeover and text(args.evidence)):
            raise StateError(f'owner is {current}; takeover requires --takeover and --evidence '
                             'of a confirmed stop or recorded transfer')
        owner = {'role': args.role, 'ref': args.actor}
        if kind_of(doc) == 'program':
            doc['owner'] = owner
        elif isinstance(doc.get('state'), dict):
            doc['state']['owner'] = owner
        else:
            raise StateError(f'state must be an object, got {got(doc.get("state"), "state" in doc)}: restore the last '
                             'known version of this file; no owner can be recorded in it')
        return doc

    result = guarded_write(args.file, args.actor, args.expect_revision, mutate, kind='claim',
                           detail={'evidence': args.evidence, 'takeover': bool(args.takeover)},
                           owner_check=False, owner_change=True)
    result.update(owner=args.actor, previous_owner=previous.get('owner'))
    return result, False


def wave_only(doc, command):
    """Wave-only commands refuse a program explicitly instead of failing on a missing wave field."""
    if kind_of(doc) == 'program':
        raise StateError(f'{command} refused: a program.json has no ' +
                         ('intents; intents live in the wave.json of an outcome (its state_ref): run intent on that wave'
                          if command == 'intent' else 'phase; change program status with write, wave phases with '
                          'transition on the wave.json'))


def cmd_transition(args):
    def mutate(doc):
        wave_only(doc, 'transition')
        state = doc['state']
        current = sval(state, 'phase')
        ops = [{'op': 'set', 'path': 'state.phase', 'value': args.to}]
        if args.to in WAITLIKE:
            origin = current if current in ACTIVE_FROM_WAIT else wait_origin(state)
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


def resolve_intent(doc, correlation, args):
    wave_only(doc, 'intent')
    current = next((i for i in _items(doc.get('intents')) if i.get('correlation') == correlation), None)
    if current is not None and sval(current, 'status') != 'pending':
        raise StateError(f'intent {correlation} is resolved and immutable ({current.get("status")}): '
                         'a new attempt takes a new correlation')
    observed = {'evidence': args.evidence} if text(args.evidence) else {}
    doc = apply_ops(doc, [{'op': 'update', 'path': 'intents', 'match': {'correlation': correlation},
                           'value': {'status': args.status, 'result_ref': args.result_ref, 'resolved_at': now(),
                                     **observed}}])
    intent = next(i for i in _items(doc['intents']) if i.get('correlation') == correlation)
    if args.status == 'confirmed' and intent.get('op') == 'launch':
        if not isinstance(doc.get('actors'), list):
            raise StateError(f'actors must be a list, got {got(doc.get("actors"), "actors" in doc)}: repair it with '
                             'write --ops (set actors) before confirming a launch')
        doc['actors'].append({'role': args.role or 'unspecified', 'model': args.model, 'ref': args.result_ref,
                              'correlation': correlation, 'status': 'running',
                              'target': intent.get('target'), 'candidate_seq': None, **observed})
    if args.status == 'confirmed' and intent.get('op') == 'send':  # the actor it reaches is alive again
        reached = [a for a in _items(doc.get('actors')) if a.get('target') == intent.get('target')]
        if reached and sval(reached[-1], 'status') not in LIVE_ACTOR:
            reached[-1].update(status='running', evidence=f'send {correlation} confirmed: '
                               f'{args.result_ref or args.evidence}')
    return doc


def cmd_intent(args):
    if args.action == 'add':
        def mutate(doc):
            wave_only(doc, 'intent')
            if not isinstance(doc.get('intents'), list):
                raise StateError(f'intents must be a list, got {got(doc.get("intents"), "intents" in doc)}: '
                                 'repair it with write --ops (set intents) before adding one')
            for intent in _items(doc['intents']):
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
            return resolve_intent(doc, args.correlation, args)
        detail = {'correlation': args.correlation, 'status': args.status}
    return guarded_write(args.file, args.actor, args.expect_revision, mutate, kind='intent', detail=detail), False


def _event_wave(path, args):
    doc = load(path)
    if kind_of(doc) != 'wave2':
        raise StateError('events are recorded against a v2 wave')
    owner = owner_ref(doc)
    if owner is not None and owner != args.actor:
        raise StateError(f'actor {args.actor} is not the owner ({owner})')
    return doc


def cmd_event(args):
    path = checked_path(args.file)
    while True:
        jpath = journal_path(path, _event_wave(path, args))
        with Lock(jpath):
            doc = _event_wave(path, args)  # read again under the lock: an attachment may have moved the journal
            if journal_path(path, doc) == jpath:
                return _record_event(args, path, doc, jpath)


def _record_event(args, path, doc, jpath):
    ident = wave_identity(path, jpath)
    status = _event_status(read_journal(jpath)).get(args.id)
    if args.attach_legacy:
        if not text(args.evidence):
            raise StateError('--attach-legacy needs --evidence showing which wave received this event')
        if status is None or status['wave'] is not None:
            raise StateError(f'event {args.id} is not a received legacy event without wave identity')
        origin = status['received'].get('file')
        if origin is not None and origin != path.name:
            raise StateError(f'legacy event {args.id} was received for file {origin}, not {path.name}; '
                             'attach it from that file')
        append_journal(jpath, {'id': f'attach:{args.id}', 'at': now(), 'kind': 'attach', 'attaches_event': args.id,
                               'wave': ident, 'actor': args.actor, 'evidence': args.evidence})
        return {'classification': 'attached', 'effect': f'legacy event now belongs to {ident}; process or ack it'}, False
    if status and status['wave'] is None:
        return {'classification': 'legacy-unattached',
                'effect': 'received by an older tool without wave identity: attach it with --attach-legacy and evidence',
                'received': status['received']}, False
    if status and status['wave'] != ident:
        raise StateError(f'event {args.id} belongs to {status["wave"]}, not {ident}; handle it on that wave')
    if status and status['applied']:
        return {'classification': 'duplicate', 'effect': 'none: already applied'}, False
    if status and status.get('uncertain'):
        return {'classification': 'uncertain', 'operation': status['uncertain'],
                'effect': 'an application may be committed without journal: run reconcile, do not reprocess'}, False
    phase = sval(doc.get('state'), 'phase')
    current = doc['candidate'].get('seq') if isinstance(doc.get('candidate'), dict) else None
    current = current if type(current) is int else None
    if status:
        seq = status['received'].get('candidate_seq')
        if args.candidate_seq is not None and seq is not None and args.candidate_seq != seq:
            raise StateError(f'event {args.id} was received for candidate_seq {seq}, not {args.candidate_seq}')
        seq = args.candidate_seq if seq is None else seq
        if type(seq) is int and type(current) is int and seq < current:
            append_journal(jpath, {'id': f'reclassify:{args.id}', 'at': now(), 'kind': 'reclassify',
                                   'wave': ident, 'actor': args.actor,
                                   'classification': 'stale', 'applies_event': args.id})
            return {'classification': 'stale',
                    'effect': 'received earlier for an older candidate; now recorded as stale, no closure'}, False
        if phase in TERMINAL_PHASES:
            return {'classification': 'unapplied', 'received': status['received'], 'wave_phase': phase,
                    'effect': f'received before the wave became {phase}: record its disposition with dispose '
                              f'{path} --actor {args.actor} --id {args.id} --disposition '
                              'late|handled_elsewhere|not_applicable --evidence ...'}, False
        return {'classification': 'unapplied', 'effect': 'received earlier but never applied: process it now',
                'received': status['received']}, False
    if phase in TERMINAL_PHASES:
        cls = 'late'
    elif args.candidate_seq is not None and current is not None and args.candidate_seq < current:
        cls = 'stale'
    else:
        cls = 'new'
    append_journal(jpath, {'id': args.id, 'at': now(), 'kind': 'event:' + args.kind, 'file': path.name,
                           'wave': ident,
                           'actor': args.actor, 'classification': cls, 'candidate_seq': args.candidate_seq,
                           'wave_revision': doc.get('revision'), 'detail': args.detail})
    effect = {'new': 'process it, then write with --applies-event (or ack) using the read revision',
              'stale': 'recorded; does not close the current candidate',
              'late': 'recorded; terminal wave, no relaunch'}[cls]
    return {'classification': cls, 'effect': effect, 'wave_revision': doc.get('revision')}, False


def _journal_only_context(args, need_terminal=None, owner_check=True):
    """Owner-checked context for journal-only records on a v2 wave (no state replacement)."""
    path = checked_path(args.file)
    doc = load(path)
    if kind_of(doc) not in {'wave2', 'program'}:
        raise StateError('needs a v2 wave or a program')
    owner = owner_ref(doc) if owner_check else None
    if owner_check and owner != args.actor:
        raise StateError(f'actor {args.actor} is not the owner ({owner}); hand the need to the owner')
    phase = sval(doc.get('state'), 'phase') if kind_of(doc) == 'wave2' else None
    if need_terminal is True and phase not in TERMINAL_PHASES:
        raise StateError(f'wave is {phase}: dispose applies to terminal waves; apply events with ack or --applies-event')
    if not text(args.evidence):
        raise StateError('--evidence is required')
    jpath = journal_path(path, doc)
    return path, doc, jpath, wave_identity(path, jpath)


def cmd_reconcile(args):
    """Resolve a prepared state replacement left open in any participating journal of this file.

    The operation is found by its identity in every participating journal, even where a copy is already closed.
    Missing closures are completed with the outcome already recorded, verified against the state bytes; a repeated
    reconciliation of a fully closed operation reports it and changes nothing. An outcome the bytes decide is recorded
    for any actor with evidence (a successor included); a declaration is the owner's, or for an init its author's.
    An init's file may be absent (not_committed) or still hold the invalid state it was replacing."""
    given = Path(args.file).absolute()
    check_ancestors(given)
    if os.path.lexists(given):
        check_state_file(given)
    if not text(args.evidence):
        raise StateError('--evidence is required')
    path = given.parent.resolve() / given.name
    with Lock(path):
        # An init may leave no file (never published) or the invalid file it was replacing: still reconcilable.
        try:
            doc = load(path) if path.is_file() else None
        except ValueError:
            doc = None
        ident = wave_identity(path, journal_path(path, doc))
        participants = participating_journals(path, doc)
        with contextlib.ExitStack() as stack:
            for j in participants:
                stack.enter_context(Lock(j))
            copies, closures = {}, {}
            for j in participants:
                entries, wid = read_journal(j), wave_identity(path, j)
                for e in entries:
                    if e.get('kind') == 'prepare' and e.get('id') == args.op and e.get('wave') == wid:
                        copies.setdefault(j, []).append(e)
                if j in copies:
                    found = [e for e in entries if args.op in (e.get('commits'), e.get('resolves'))]
                    if found:
                        closures[j] = found
            if not copies:
                raise StateError(f'no operation {args.op} on {ident} in its participating journals')
            every = [c for found in copies.values() for c in found]
            op = every[0]
            if any(c.get(k) != op.get(k) for c in every
                   for k in ('old_sha256', 'new_sha256', 'revision', 'actor', 'file', 'op_kind')):
                raise StateError(f'operation {args.op} has prepare lines that differ (between or within journals): '
                                 'inspect them before reconciling')
            recorded = {('committed' if e.get('commits') else e.get('outcome')) for found in closures.values()
                        for e in found}
            if len(recorded) > 1:
                raise StateError(f'operation {args.op} has contradictory closures {sorted(recorded)}: inspect the journals')
            recorded = next(iter(recorded)) if recorded else None
            open_js = [j for j in participants if j in copies and j not in closures]
            if not open_js:
                return {'operation': args.op, 'outcome': recorded, 'already_resolved': True, 'resolved_in': [],
                        'closed_in': [str(j) for j in closures]}, False
            if op.get('op_kind') != 'init' and kind_of(doc) not in {'wave2', 'program'}:
                raise StateError('needs a v2 wave or a program')
            current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            computed = ('committed' if current is not None and current == op.get('new_sha256') else
                        'not_committed' if current == op.get('old_sha256') else None)  # init: absent == no old bytes
            if recorded and computed and computed != recorded:
                raise StateError(f'state bytes show {computed} but {args.op} is already closed as {recorded}: inspect')
            expected = recorded or computed
            if expected and args.declare and args.declare != expected:
                raise StateError(f'{args.op} is {expected} by its bytes or closures; a contrary declaration is refused')
            if expected is None:
                # Bytes decide for anyone (a successor included); a declaration is the owner's (an init's: its author).
                try:
                    owner = op.get('actor') if op.get('op_kind') == 'init' else owner_ref(doc)
                except MalformedOwner:
                    owner = None
                if owner != args.actor:
                    raise StateError(f'uncertain application: {ident} matches neither the bytes before nor after '
                                     f'{args.op}, and actor {args.actor} is not the owner ({owner}), who alone may declare its outcome '
                                     '(reconcile --declare committed|not_committed --evidence)')
                if not args.declare:
                    raise StateError(f'uncertain application: {ident} matches neither the bytes before nor after '
                                     f'{args.op}; inspect state and journal, then rerun with --declare '
                                     'committed|not_committed --evidence')
            outcome = expected or args.declare
            for j in open_js:
                entry = {'id': f'resolve:{args.op}', 'at': now(), 'kind': 'resolve', 'resolves': args.op,
                         'wave': wave_identity(path, j), 'outcome': outcome, 'declared': expected is None,
                         'state_sha256': current, 'actor': args.actor, 'evidence': args.evidence,
                         'revision': op.get('revision'),
                         'completes_closure': recorded is not None}
                event = op.get('pending_applies_event')
                if outcome == 'committed' and event and event in _event_status(read_journal(j)):
                    entry['applies_event'] = event
                append_journal(j, entry)
            leftover = path.parent / str(op.get('tmp'))
            removed = None
            if op.get('tmp') and leftover.is_file() and not _is_link(os.lstat(leftover)) and \
                    hashlib.sha256(leftover.read_bytes()).hexdigest() == op.get('new_sha256'):
                os.unlink(leftover)
                removed = leftover.name
    return {'operation': args.op, 'outcome': outcome, 'declared': expected is None, 'already_resolved': False,
            'resolved_in': [str(j) for j in open_js], 'closed_in': [str(j) for j in closures],
            'event_marked_applied': op.get('pending_applies_event') if outcome == 'committed' else None,
            'removed_own_temporary': removed}, False


def cmd_dispose(args):
    """Record the disposition of an event left unapplied on a terminal wave, without reopening it."""
    path, doc, jpath, ident = _journal_only_context(args, need_terminal=True)
    with Lock(jpath):
        status = _event_status(read_journal(jpath)).get(args.id)
        if status is None:
            raise StateError(f'event {args.id} was never received')
        if status['wave'] is None:
            raise StateError(f'event {args.id} has no wave identity: attach it first with event --attach-legacy')
        if status['wave'] != ident:
            raise StateError(f'event {args.id} belongs to {status["wave"]}, not {ident}')
        if status.get('uncertain'):
            raise StateError(f'event {args.id} has an uncertain application ({status["uncertain"]}): reconcile first')
        if status['applied']:
            raise StateError(f'event {args.id} is already applied')
        append_journal(jpath, {'id': f'dispose:{args.id}', 'at': now(), 'kind': 'dispose', 'applies_event': args.id,
                               'wave': ident, 'disposition': args.disposition, 'evidence': args.evidence,
                               'actor': args.actor, 'wave_phase': sval(doc.get('state'), 'phase')})
    return {'disposed': args.id, 'disposition': args.disposition, 'wave_unchanged': True}, False


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
    p = sub.add_parser('reconcile', help='resolve an unresolved prepared write (commit missing from journal)',
                       epilog=COMMAND_EXAMPLES['reconcile'], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file')
    p.add_argument('--actor', required=True)
    p.add_argument('--op', required=True, help='id of the prepare entry listed by resume')
    p.add_argument('--evidence', required=True)
    p.add_argument('--declare', choices=['committed', 'not_committed'],
                   help='sourced declaration, only when the state bytes match neither side')
    p.set_defaults(func=cmd_reconcile)
    p = sub.add_parser('dispose', help='record the disposition of an unapplied event of a terminal wave',
                       epilog=COMMAND_EXAMPLES['dispose'], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file')
    p.add_argument('--actor', required=True)
    p.add_argument('--id', required=True)
    p.add_argument('--disposition', required=True, choices=['late', 'handled_elsewhere', 'not_applicable'])
    p.add_argument('--evidence', required=True)
    p.set_defaults(func=cmd_dispose)
    p = sub.add_parser('init', help='create a program.json or a detached v2 wave at revision 0, owned by --actor; '
                       '--template prints the field formats')
    p.add_argument('file', nargs='?', help='state file to create (never overwritten, except --replace-invalid)')
    p.add_argument('--kind', choices=['program', 'wave'])
    p.add_argument('--actor', help='runtime reference of the new owner')
    p.add_argument('--role', help='owner role, e.g. pilot')
    p.add_argument('--spec', help='JSON file: partial document with the business fields (see --template)')
    p.add_argument('--template', choices=['program', 'wave'], help='print the spec skeleton and field types; writes nothing')
    p.add_argument('--replace-invalid', action='store_true',
                   help='replace an existing invalid revision-0 state without owner (or owned by --actor); the old '
                        'file is kept as <name>.invalid-<n>.json')
    p.add_argument('--evidence', help='required with --replace-invalid: why the initial file is replaced')
    p.set_defaults(func=cmd_init)
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
        p = sub.add_parser(name, help=help_, epilog=COMMAND_EXAMPLES.get(name),
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        p.add_argument('file')
        p.add_argument('--actor', required=True, help='runtime reference of the acting owner')
        if name != 'event':
            p.add_argument('--expect-revision', type=int, required=True)
        p.set_defaults(func=func)
        if name in {'write', 'transition'}:
            p.add_argument('--applies-event', help='id of the received event this write applies')
        if name == 'write':
            group = p.add_mutually_exclusive_group()
            group.add_argument('--ops', help='JSON list of {op:set|append|update, path, value, match}')
            group.add_argument('--ops-file')
            p.add_argument('--reason')
            p.add_argument('--resolve-intent', metavar='CORRELATION',
                           help='resolve this pending intent in the same write, as intent resolve does')
            p.add_argument('--status', choices=['confirmed', 'absent', 'failed'])
            p.add_argument('--result-ref')
            p.add_argument('--evidence', help='what was observed: confirms a launch without receipt (no --result-ref)')
            p.add_argument('--role', help='actor role recorded when a launch is confirmed')
            p.add_argument('--model')
            p.add_argument('--record-event', metavar='ID',
                           help='record this signal as event does, then write only if it is new or unapplied, '
                                'applying it')
            p.add_argument('--kind', help='signal kind, with --record-event')
            p.add_argument('--candidate-seq', type=int, help='with --record-event')
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
            p.add_argument('--evidence', help='what was observed: confirms a launch without receipt (no --result-ref)')
            p.add_argument('--role', help='actor role recorded when a launch is confirmed')
            p.add_argument('--model')
        elif name in {'event', 'ack'}:
            p.add_argument('--id', required=True, help='stable signal id (taskId+runId or equivalent)')
            if name == 'event':
                p.add_argument('--kind', required=True)
                p.add_argument('--candidate-seq', type=int)
                p.add_argument('--detail')
                p.add_argument('--attach-legacy', action='store_true',
                               help='attach a received legacy event (no wave identity) to this wave, with --evidence')
                p.add_argument('--evidence')
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
    if args.command == 'write':
        if args.ops is None and args.ops_file is None and not args.resolve_intent:
            parser.error('write needs --ops, --ops-file or --resolve-intent')
        if bool(args.resolve_intent) != bool(args.status) or \
                (not args.resolve_intent and (args.result_ref or args.role or args.model or args.evidence)):
            parser.error('--resolve-intent goes with --status; --result-ref, --evidence, --role and --model need '
                         '--resolve-intent')
        if bool(args.record_event) != bool(args.kind) or (args.candidate_seq is not None and not args.record_event):
            parser.error('--record-event goes with --kind; --candidate-seq needs --record-event')
        if args.record_event and args.applies_event:
            parser.error('--record-event already applies the event it records; drop --applies-event')
    if args.command == 'init':
        if args.template and any((args.file, args.kind, args.actor, args.role, args.spec, args.replace_invalid)):
            parser.error('init --template only prints a template; it takes no FILE or other option')
        if not args.template and not all((args.file, args.kind, args.actor, args.role)):
            parser.error('init needs FILE, --kind, --actor and --role (or --template program|wave)')
        if args.replace_invalid and not (args.evidence and args.evidence.strip()):
            parser.error('init --replace-invalid needs --evidence')
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
    for stream in (sys.stdout, sys.stderr):  # agents read this text raw: UTF-8 whatever the console code page
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    raise SystemExit(main())
