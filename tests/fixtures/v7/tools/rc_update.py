"""Mise à jour ciblée des trois skills Radio Chantier dans des profils existants.

Lancer avec ``python -B``. Bibliothèque standard seulement (Python 3.10).

Commandes :
  manifest   calcule le manifeste d'un paquet (chemin POSIX relatif, sha256, octets).
  preflight  compare chaque profil à la version précédente et à la nouvelle ; écrit
             seulement le plan (hors des cibles) ; n'écrit rien dans les cibles.
  apply      exécute exactement un plan dont l'empreinte correspond encore à l'état.
  resume     termine le même plan après une issue partielle.
  rollback   restaure l'état antérieur depuis les sauvegardes et vérifie les octets.
  verify     relecture seule des octets publiés (aucune écriture).

Codes de sortie : 0 succès, 1 refus ou erreur, 2 plan bloqué (conflit ou profil
refusé), 3 plan périmé (l'état observé ne correspond plus à l'empreinte).

Seuls les dossiers des trois skills sont lus et modifiés dans chaque cible.

Fichiers temporaires (version corrigée après pré-revue 2, constats R2-05 à R2-07) :
- tout temporaire est créé de façon exclusive (O_EXCL) sous un nom aléatoire propre à
  l'opération ; une entrée préexistante sous ce nom est refusée, jamais réutilisée ;
- les temporaires des cibles et des sauvegardes sont consignés au journal (événement
  ``tmp-created`` avec chemin exact et identité de fichier) dès leur création, avant toute
  écriture de données ; resume et rollback ne retirent que ces temporaires-là, après le
  contrôle des conflits, et seulement si l'identité relue correspond ;
- un fichier non consigné, quel que soit son nom, n'est jamais supprimé : il fait refuser
  la reprise ou le retour arrière ;
- plan, manifeste et plan copié dans l'état sont créés sans remplacement (sortie déjà
  présente refusée) ; status.json et rapports sont remplacés atomiquement ; une
  destination ou un journal à plusieurs liens physiques est refusé.
"""
import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import secrets  # noqa: E402
import stat  # noqa: E402
from pathlib import Path  # noqa: E402

SKILLS = ('rc-coordinate-development', 'rc-prepare-socle-prompts', 'rc-prepare-supervisor')
TMP_PREFIX = '.rc-update-'
REPARSE_ATTR = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
PLAN_FORMAT = 'rc-update-plan/1'
MANIFEST_FORMAT = 'rc-update-manifest/1'
OPS_ORDER = {'create': 0, 'replace': 1, 'remove': 2}


class UpdateError(Exception):
    code = 1


class BlockedPlan(UpdateError):
    code = 2


class StalePlan(UpdateError):
    code = 3


# --------------------------------------------------------------------------- outils

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def is_reparse(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & REPARSE_ATTR)


def refuse_reparse_chain(path):
    """Refuse un point de réparse sur le chemin ou l'un de ses parents existants."""
    path = Path(os.path.abspath(path))
    for node in (path, *path.parents):
        try:
            st = os.lstat(node)
        except FileNotFoundError:
            continue
        if is_reparse(st):
            raise UpdateError(f'Point de réparse refusé : {node}')


def real(path):
    refuse_reparse_chain(path)
    return Path(os.path.abspath(path)).resolve()


def inside(child, parent):
    try:
        Path(child).relative_to(Path(parent))
        return True
    except ValueError:
        return False


def check_rel(rel):
    """Valide un chemin relatif de manifeste : POSIX, sous l'un des trois skills."""
    if not isinstance(rel, str) or not rel or '\\' in rel or ':' in rel or rel.startswith('/'):
        raise UpdateError(f'Chemin de manifeste refusé : {rel!r}')
    parts = rel.split('/')
    if len(parts) < 2 or parts[0] not in SKILLS:
        raise UpdateError(f'Chemin hors des trois skills : {rel!r}')
    for part in parts:
        if part in ('', '.', '..') or part == '__pycache__' or part.startswith(TMP_PREFIX):
            raise UpdateError(f'Chemin de manifeste refusé : {rel!r}')
    if rel.endswith('.pyc'):
        raise UpdateError(f'Fichier compilé refusé : {rel!r}')
    return rel


def dest_path(target_root, rel):
    """Chemin de destination contrôlé : contenu dans target/<skill>, sans réparse."""
    check_rel(rel)
    root = Path(target_root)
    skill_dir = root / rel.split('/')[0]
    dest = root.joinpath(*rel.split('/'))
    refuse_reparse_chain(dest)
    if not inside(dest.resolve(), skill_dir.resolve()) or not inside(skill_dir.resolve(), root.resolve()):
        raise UpdateError(f'Chemin sortant de la cible refusé : {dest}')
    return dest


def single_link_or_none(path):
    """lstat d'un fichier ordinaire à lien unique ; None si absent ; refus sinon."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if is_reparse(st):
        raise UpdateError(f'Point de réparse refusé : {path}')
    if not stat.S_ISREG(st.st_mode):
        raise UpdateError(f'Entrée non régulière refusée : {path}')
    if st.st_nlink != 1:
        raise UpdateError(f'Lien physique refusé ({st.st_nlink} liens) : {path}')
    return st


def file_sha_or_none(path):
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if is_reparse(st):
        raise UpdateError(f'Point de réparse refusé : {path}')
    if not stat.S_ISREG(st.st_mode):
        raise UpdateError(f'Entrée non régulière refusée : {path}')
    return sha256(Path(path).read_bytes())


def scan_tree(base, top_names, prefix_rel=''):
    """Inventaire {rel posix: {sha256, bytes}} sous base/<top>, sans suivre de lien."""
    found = {}
    for top in top_names:
        folder = Path(base) / top
        try:
            st = os.lstat(folder)
        except FileNotFoundError:
            continue
        if is_reparse(st) or not stat.S_ISDIR(st.st_mode):
            raise UpdateError(f'Dossier de skill invalide ou point de réparse : {folder}')
        for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
            for name in list(dirnames):
                if is_reparse(os.lstat(os.path.join(dirpath, name))):
                    raise UpdateError(f'Point de réparse refusé : {os.path.join(dirpath, name)}')
            for name in filenames:
                full = os.path.join(dirpath, name)
                fst = os.lstat(full)
                if is_reparse(fst) or not stat.S_ISREG(fst.st_mode):
                    raise UpdateError(f'Entrée non régulière ou point de réparse refusé : {full}')
                rel = Path(full).relative_to(base).as_posix()
                data = Path(full).read_bytes()
                found[rel] = {'sha256': sha256(data), 'bytes': len(data)}
    return found


# --------------------------------------------------------------------------- manifestes

def manifest_doc(files):
    items = [{'path': p, 'sha256': files[p]['sha256'], 'bytes': files[p]['bytes']} for p in sorted(files)]
    return {'format': MANIFEST_FORMAT, 'files': items, 'digest': sha256(canonical(items))}


def files_from_doc(doc):
    files = {}
    for item in doc.get('files', []):
        rel = check_rel(str(item['path']).replace('\\', '/'))
        if rel in files:
            raise UpdateError(f'Entrée en double dans le manifeste : {rel}')
        if not isinstance(item.get('sha256'), str) or len(item['sha256']) != 64 or not isinstance(item.get('bytes'), int):
            raise UpdateError(f'Entrée de manifeste invalide : {rel}')
        files[rel] = {'sha256': item['sha256'].lower(), 'bytes': item['bytes']}
    if {p.split('/')[0] for p in files} != set(SKILLS):
        raise UpdateError('Le manifeste doit couvrir exactement les trois skills')
    return files


def load_manifest(path):
    refuse_reparse_chain(path)
    return files_from_doc(json.loads(Path(path).read_text(encoding='utf-8')))


def compute_manifest(package):
    package = real(package)
    if not package.is_dir():
        raise UpdateError(f'Paquet introuvable : {package}')
    extras = [e.name for e in package.iterdir() if e.name not in SKILLS]
    if extras:
        raise UpdateError(f'Entrées hors des trois skills dans le paquet : {sorted(extras)}')
    files = scan_tree(package, SKILLS)
    for rel in files:
        check_rel(rel)
    if {p.split('/')[0] for p in files} != set(SKILLS):
        raise UpdateError('Le paquet doit contenir exactement les trois skills')
    return files


def check_package(package, new_files):
    actual = compute_manifest(package)
    if actual != new_files:
        diff = sorted(set(actual) ^ set(new_files)) or sorted(p for p in actual if actual[p] != new_files.get(p))
        raise UpdateError(f'Paquet source différent du manifeste attendu : {diff}')


# --------------------------------------------------------------------------- plan

def classify_skill(skill, observed, prev, new):
    p_paths = {r for r in prev if r.split('/')[0] == skill}
    n_paths = {r for r in new if r.split('/')[0] == skill}
    managed = p_paths | n_paths
    local = {r: v for r, v in observed.items() if r.split('/')[0] == skill}
    unknown = sorted(r for r in local if r not in managed)
    folded = {r.casefold(): r for r in managed}
    collisions = sorted(r for r in unknown if r.casefold() in folded)
    sha = {r: (local[r]['sha256'] if r in local else None) for r in managed}
    out = {'name': skill, 'status': None, 'reasons': [], 'conflicts': [], 'unknown': unknown, 'files': [], 'actions': []}
    if collisions:
        out['status'] = 'unexpected'
        out['reasons'].append(f'casse différente du manifeste : {collisions}')
        return out
    if not local and not any(sha.values()):
        out['status'] = 'unexpected'
        out['reasons'].append('dossier de skill absent ou vide')
        return out
    at_new = all(sha[r] == new[r]['sha256'] for r in n_paths) and all(sha[r] is None for r in p_paths - n_paths)
    if at_new:
        out['status'] = 'already-new'
        out['files'] = [{'path': r, 'decision': 'unchanged'} for r in sorted(n_paths)]
    else:
        missing = sorted(r for r in p_paths if sha[r] is None)
        new_only = sorted(r for r in n_paths - p_paths if sha[r] is not None)
        mixed = sorted(r for r in p_paths & n_paths
                       if prev[r]['sha256'] != new[r]['sha256'] and sha[r] == new[r]['sha256'])
        custom = sorted(r for r in p_paths if sha[r] is not None and sha[r] != prev[r]['sha256']
                        and not (r in n_paths and sha[r] == new[r]['sha256']))
        if missing:
            out['reasons'].append(f'fichiers attendus de la version précédente absents : {missing}')
        if new_only:
            out['reasons'].append(f'fichiers de la nouvelle version déjà présents : {new_only}')
        if mixed:
            out['reasons'].append(f'mélange de versions : {mixed}')
        if out['reasons']:
            out['status'] = 'unexpected'
        elif custom:
            out['status'] = 'conflict'
            out['conflicts'] = custom
            out['files'] = [{'path': r, 'decision': 'conflict' if r in custom else 'blocked'} for r in sorted(managed)]
        else:
            out['status'] = 'update'
            for r in sorted(managed):
                if r not in p_paths:
                    op = 'create'
                elif r not in n_paths:
                    op = 'remove'
                elif prev[r]['sha256'] != new[r]['sha256']:
                    op = 'replace'
                else:
                    out['files'].append({'path': r, 'decision': 'unchanged'})
                    continue
                out['files'].append({'path': r, 'decision': op})
                out['actions'].append({'op': op, 'path': r, 'before': sha[r],
                                       'after': new[r]['sha256'] if op != 'remove' else None})
    out['files'] += [{'path': r, 'decision': 'preserve-unknown'} for r in unknown]
    out['files'].sort(key=lambda f: f['path'])
    return out


def check_layout(targets, package, extra_paths=()):
    roots = [real(t) for t in targets]
    for i, a in enumerate(roots):
        if not a.is_dir():
            raise UpdateError(f'Racine de skills absente : {a}')
        for b in roots[i + 1:]:
            if inside(a, b) or inside(b, a):
                raise UpdateError(f'Cibles imbriquées : {a} / {b}')
    pkg = real(package)
    extras = [real(x) for x in extra_paths]
    for p in [pkg, *extras]:
        for r in roots:
            if inside(p, r) or inside(r, p):
                raise UpdateError(f'Chemin de travail non séparé de la cible : {p} / {r}')
    for p in extras:
        if inside(p, pkg):
            raise UpdateError(f'Chemin de travail dans le paquet source : {p}')
    return roots, pkg


def build_plan(prev, new, package, targets):
    roots, pkg = check_layout(targets, package)
    check_package(pkg, new)
    plan = {'format': PLAN_FORMAT, 'skills': list(SKILLS),
            'previous_manifest': manifest_doc(prev), 'new_manifest': manifest_doc(new),
            'new_package': str(pkg), 'targets': [], 'actions': []}
    for i, root in enumerate(roots):
        observed = scan_tree(root, SKILLS)
        skills = [classify_skill(s, observed, prev, new) for s in SKILLS]
        refused = [s for s in skills if s['status'] == 'unexpected']
        entry = {'index': i, 'root': str(root), 'status': 'refused' if refused else 'ok',
                 'reasons': [f"{s['name']} : {r}" for s in refused for r in s['reasons']],
                 'observed': observed, 'skills': []}
        for s in skills:
            actions = s.pop('actions')
            if refused:
                s['files'] = [{'path': f['path'], 'decision': 'refused' if f['decision'] != 'preserve-unknown'
                               else 'preserve-unknown'} for f in s['files']]
            else:
                for a in sorted(actions, key=lambda a: (OPS_ORDER[a['op']], a['path'])):
                    plan['actions'].append({'id': f"T{i}:{a['op']}:{a['path']}", 'target': i, **a})
            entry['skills'].append(s)
        plan['targets'].append(entry)
    counts = {}
    for t in plan['targets']:
        for s in t['skills']:
            for f in s['files']:
                counts[f['decision']] = counts.get(f['decision'], 0) + 1
    plan['summary'] = counts
    plan['blocked'] = any(t['status'] == 'refused' or any(s['status'] == 'conflict' for s in t['skills'])
                          for t in plan['targets'])
    plan['fingerprint'] = plan_fingerprint(plan)
    plan['plan_id'] = plan['fingerprint'][:16]
    return plan


def plan_fingerprint(plan):
    body = {k: v for k, v in plan.items() if k not in ('fingerprint', 'plan_id', 'created_at')}
    return sha256(canonical(body))


def load_plan(path):
    refuse_reparse_chain(path)
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    if plan.get('format') != PLAN_FORMAT or plan_fingerprint(plan) != plan.get('fingerprint') \
            or plan.get('plan_id') != plan['fingerprint'][:16]:
        raise UpdateError('Plan illisible ou altéré (empreinte interne incohérente)')
    return plan


def plan_inputs(plan):
    prev = files_from_doc(plan['previous_manifest'])
    new = files_from_doc(plan['new_manifest'])
    return prev, new, plan['new_package'], [t['root'] for t in plan['targets']]


# --------------------------------------------------------------------------- état et journal

class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.seq = 0
        self.events = []
        if self.path.exists():
            for line in self.path.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    self.events.append(json.loads(line))
            self.seq = len(self.events)

    def append(self, event, step=None, **data):
        entry = {'seq': self.seq + 1, 'ts': now_iso(), 'event': event, 'step': step, **data}
        line = (json.dumps(entry, ensure_ascii=False) + '\n').encode('utf-8')
        refuse_reparse_chain(self.path.parent)
        before = single_link_or_none(self.path)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_BINARY', 0))
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 \
                    or (before is not None and (st.st_dev, st.st_ino) != (before.st_dev, before.st_ino)):
                raise UpdateError(f'Journal remplacé ou lié ailleurs, aucune écriture : {self.path}')
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        self.seq += 1
        self.events.append(entry)

    def verified_steps(self):
        return {e['step'] for e in self.events if e['event'] == 'verified'}

    def created_dirs(self):
        return [e for e in self.events if e['event'] == 'mkdir']

    def pending_temps(self):
        """Temporaires consignés comme créés et pas encore consignés comme disparus."""
        gone = {e['path'] for e in self.events if e['event'] == 'tmp-gone'}
        return [e for e in self.events if e['event'] == 'tmp-created' and e['path'] not in gone]


class Lock:
    def __init__(self, state):
        self.path = Path(state) / 'lock'

    def __enter__(self):
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise UpdateError(f'Verrou présent (autre exécution ou arrêt brutal) : {self.path}')
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return False


def state_dir(state_root, plan, targets, package):
    root = Path(os.path.abspath(state_root))
    check_layout(targets, package, extra_paths=[root])
    return root / plan['plan_id']


def _token():
    return secrets.token_hex(6)


def _create_exclusive(path):
    """Crée path de façon exclusive ; refuse toute entrée préexistante. Rend (fd, stat)."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0))
    except FileExistsError:
        raise UpdateError(f'Entrée préexistante refusée pour un temporaire : {path}')
    return fd, os.fstat(fd)


def _write_fd(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]
    os.fsync(fd)


def _same_file(path, ident):
    """True si path est encore le fichier ordinaire, non lié ailleurs, d'identité ident."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    return (not is_reparse(st) and stat.S_ISREG(st.st_mode) and st.st_nlink == 1
            and (st.st_dev, st.st_ino) == tuple(ident))


def _discard_tmp(path, ident):
    """Retire un temporaire créé par cette exécution s'il est encore le même fichier."""
    if _same_file(path, ident):
        os.remove(path)
        return True
    return False


def write_json(path, obj, replace=False):
    """Écrit un document JSON hors des cibles par temporaire exclusif propre à l'opération.

    replace=False : la destination ne doit pas exister (création sans remplacement).
    replace=True : remplacement atomique d'un fichier ordinaire à lien unique.
    """
    path = Path(path)
    refuse_reparse_chain(path.parent)
    existing = single_link_or_none(path)
    if existing is not None and not replace:
        raise UpdateError(f'Sortie déjà présente, aucune écriture : {path}')
    data = (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    tmp = path.parent / f'.{path.name}.{_token()}.tmp'
    fd, st = _create_exclusive(tmp)
    ident = (st.st_dev, st.st_ino)
    try:
        try:
            _write_fd(fd, data)
        finally:
            os.close(fd)
        if not _same_file(tmp, ident):
            raise UpdateError(f'Temporaire remplacé pendant l\'écriture : {tmp}')
        if replace:
            single_link_or_none(path)
            os.replace(tmp, path)
        else:
            _swap(tmp, path, exclusive=True)
    finally:
        _discard_tmp(tmp, ident)


def set_status(state, status, **data):
    write_json(Path(state) / 'status.json', {'status': status, 'ts': now_iso(), **data}, replace=True)


def read_status(state):
    p = Path(state) / 'status.json'
    return json.loads(p.read_text(encoding='utf-8'))['status'] if p.exists() else None


# --------------------------------------------------------------------------- écritures

def _swap(tmp, dest, exclusive):
    """Remplacement atomique ; création exclusive quand la destination doit être absente."""
    if not exclusive:
        os.replace(tmp, dest)
    elif os.name == 'nt':
        os.rename(tmp, dest)  # MoveFileEx sans REPLACE_EXISTING : échoue si dest existe
    else:
        os.link(tmp, dest)
        os.unlink(tmp)


def _journaled_tmp(tmp, data, journal, step, **meta):
    """Crée tmp exclusivement, le consigne (chemin et identité) avant d'y écrire data."""
    fd, st = _create_exclusive(tmp)
    ident = [st.st_dev, st.st_ino]
    try:
        try:
            journal.append('tmp-created', step, path=str(tmp), ident=ident, **meta)
        except BaseException:
            os.close(fd)
            fd = None
            _discard_tmp(tmp, ident)
            raise
        _write_fd(fd, data)
    finally:
        if fd is not None:
            os.close(fd)
    if not _same_file(tmp, ident):
        raise UpdateError(f'Temporaire remplacé pendant l\'écriture : {tmp}')
    return ident


def _finish_tmp(tmp, ident, journal, step, how):
    """Après usage : retire le temporaire s'il reste, puis consigne sa disparition."""
    if os.path.lexists(tmp):
        if not _discard_tmp(tmp, ident):
            return  # plus le même fichier : ni suppression ni consignation
    journal.append('tmp-gone', step, path=str(tmp), how=how)


def publish(dest, data, expected_before, plan_id, exclusive, journal, step, target):
    """Écrit data dans dest par temporaire voisin exclusif et consigné, puis remplacement atomique."""
    refuse_reparse_chain(dest.parent)
    tmp = dest.parent / f'{TMP_PREFIX}{plan_id}-{_token()}.tmp'
    ident = _journaled_tmp(tmp, data, journal, step, kind='target', target=target)
    how = 'abandoned'
    try:
        if file_sha_or_none(dest) != expected_before:
            raise UpdateError(f'Changement concurrent détecté, écriture annulée : {dest}')
        _swap(tmp, dest, exclusive)
        how = 'published'
    finally:
        _finish_tmp(tmp, ident, journal, step, how)


def write_backup(path, data, expected_sha, state, journal, step):
    """Sauvegarde exacte des octets antérieurs, sans jamais réutiliser un temporaire laissé."""
    refuse_reparse_chain(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    if single_link_or_none(path) is not None:
        if sha256(path.read_bytes()) != expected_sha:
            raise UpdateError(f'Sauvegarde existante incohérente : {path}')
        return False
    if sha256(data) != expected_sha:
        raise UpdateError(f'Octets à sauvegarder différents de l\'attendu : {path}')
    tmp_dir = Path(state) / 'tmp'
    refuse_reparse_chain(tmp_dir)
    tmp_dir.mkdir(exist_ok=True)
    tmp = tmp_dir / f'{_token()}.tmp'
    ident = _journaled_tmp(tmp, data, journal, step, kind='backup')
    how = 'abandoned'
    try:
        _swap(tmp, path, exclusive=True)
        how = 'published'
    finally:
        _finish_tmp(tmp, ident, journal, step, how)
    if single_link_or_none(path) is None or sha256(path.read_bytes()) != expected_sha:
        raise UpdateError(f'Sauvegarde relue différente : {path}')
    return True


def backup_path(state, action):
    return Path(state) / 'backups' / f"T{action['target']}" / Path(*action['path'].split('/'))


def ensure_parents(root, rel, journal, step):
    parts = rel.split('/')
    current = Path(root) / parts[0]
    for part in parts[1:-1]:
        current = current / part
        refuse_reparse_chain(current)
        if not current.exists():
            os.mkdir(current)
            journal.append('mkdir', step, dir=str(current))


def own_leftover_temps(plan, state, journal):
    """Temporaires consignés par ce plan et encore présents sous leur identité d'origine.

    Lecture seule. Rend (leftovers, ignore) où ignore[target_index] est l'ensemble des
    chemins relatifs à exclure du contrôle de conflits. Un chemin consigné occupé par un
    autre fichier (identité différente) n'est pas retenu : il reste visible et fait refuser.
    """
    leftovers, ignore, foreign = [], {}, []
    state = Path(os.path.abspath(state))
    for e in journal.pending_temps():
        path = Path(e['path'])
        if not os.path.lexists(path):
            leftovers.append({**e, 'present': False})
            continue
        if not _same_file(path, e['ident']):
            foreign.append(str(path))
            continue
        if e.get('kind') == 'target':
            root = Path(plan['targets'][e['target']]['root'])
            if not inside(path, root):
                raise UpdateError(f'Temporaire consigné hors de la cible : {path}')
            rel = path.relative_to(root).as_posix()
            if rel.split('/')[0] not in SKILLS or not path.name.startswith(f"{TMP_PREFIX}{plan['plan_id']}-"):
                raise UpdateError(f'Temporaire consigné hors des skills ciblés : {path}')
            ignore.setdefault(e['target'], set()).add(rel)
        elif e.get('kind') == 'backup':
            if not inside(path, state / 'tmp'):
                raise UpdateError(f'Temporaire de sauvegarde consigné hors de l\'état : {path}')
        else:
            raise UpdateError(f'Temporaire consigné de nature inconnue : {path}')
        leftovers.append({**e, 'present': True})
    if foreign:
        raise UpdateError(f'Chemin de temporaire consigné occupé par un autre fichier, aucune écriture : {foreign}')
    return leftovers, ignore


def check_state_outputs(state):
    """Avant toute écriture ou suppression : fichiers d'état ordinaires à lien unique."""
    refuse_reparse_chain(state)
    for name in ('journal.jsonl', 'status.json', 'rapport-apply.json', 'rapport-resume.json',
                 'rapport-rollback.json'):
        single_link_or_none(Path(state) / name)


def remove_own_temps(leftovers, journal, step):
    """À appeler seulement après le contrôle des conflits. Rend les chemins retirés."""
    removed = []
    for e in leftovers:
        if e['present']:
            if not _discard_tmp(Path(e['path']), e['ident']):
                raise UpdateError(f"Temporaire consigné modifié entre contrôle et retrait : {e['path']}")
            removed.append(e['path'])
        journal.append('tmp-gone', step, path=e['path'], how='cleanup' if e['present'] else 'absent')
    return removed


def check_progress(plan, allow_after=True, ignore=None):
    """Chaque chemin des trois skills doit être dans l'état observé du plan ou l'état cible."""
    problems = []
    ignore = ignore or {}
    for t in plan['targets']:
        if t['status'] != 'ok':
            continue
        now = scan_tree(t['root'], SKILLS)
        for rel in ignore.get(t['index'], ()):
            now.pop(rel, None)
        acts = {a['path']: a for a in plan['actions'] if a['target'] == t['index']}
        for rel in set(now) | set(t['observed']) | set(acts):
            cur = now[rel]['sha256'] if rel in now else None
            allowed = {t['observed'][rel]['sha256'] if rel in t['observed'] else None}
            if rel in acts and allow_after:
                allowed.add(acts[rel]['after'])
            if cur not in allowed:
                problems.append(f"T{t['index']}:{rel}")
    if problems:
        raise UpdateError(f'État inattendu, aucune écriture : {sorted(problems)}')


def run_steps(plan, state, journal):
    pkg = Path(plan['new_package'])
    verified = journal.verified_steps()
    for a in plan['actions']:
        root = plan['targets'][a['target']]['root']
        dest = dest_path(root, a['path'])
        cur = file_sha_or_none(dest)
        if a['id'] in verified:
            if cur != a['after']:
                raise UpdateError(f"Étape déjà vérifiée altérée depuis : {a['id']}")
            continue
        if cur == a['after']:
            journal.append('verified', a['id'], sha256=cur, note='constaté sans réécriture')
            continue
        if cur != a['before']:
            raise UpdateError(f"État inattendu avant l'étape {a['id']}")
        journal.append('start', a['id'], op=a['op'])
        if a['op'] in ('replace', 'remove'):
            created = write_backup(backup_path(state, a), dest.read_bytes(), a['before'], state, journal, a['id'])
            journal.append('backed-up', a['id'], sha256=a['before'], reused=not created)
        if a['op'] in ('create', 'replace'):
            data = (pkg / Path(*a['path'].split('/'))).read_bytes()
            if sha256(data) != a['after']:
                raise UpdateError(f"Source changée : {a['path']}")
            ensure_parents(root, a['path'], journal, a['id'])
            publish(dest, data, a['before'], plan['plan_id'], a['op'] == 'create', journal, a['id'], a['target'])
            journal.append('written', a['id'], sha256=a['after'])
        else:
            if file_sha_or_none(dest) != a['before']:
                raise UpdateError(f'Changement concurrent détecté : {dest}')
            os.remove(dest)
            journal.append('removed', a['id'])
        cur = file_sha_or_none(dest)
        if cur != a['after']:
            raise UpdateError(f"Relecture différente du manifeste : {a['id']}")
        journal.append('verified', a['id'], sha256=cur)


def verify_plan(plan, expect):
    """Relecture seule. expect='new' : octets publiés ; 'previous' : état antérieur restauré."""
    new = files_from_doc(plan['new_manifest'])
    prev = files_from_doc(plan['previous_manifest'])
    report = {'expect': expect, 'targets': [], 'ok': True}
    for t in plan['targets']:
        refuse_reparse_chain(t['root'])
        now = scan_tree(t['root'], SKILLS)
        mismatches, checked = [], 0
        for s in t['skills']:
            skill = s['name']
            if t['status'] == 'ok' and expect == 'new' and s['status'] in ('update', 'already-new'):
                expected = {r: v['sha256'] for r, v in new.items() if r.split('/')[0] == skill}
                absent = [r for r in prev if r.split('/')[0] == skill and r not in new]
            else:
                expected = {r: v['sha256'] for r, v in t['observed'].items()
                            if r.split('/')[0] == skill and r not in s['unknown']}
                absent = [r for r in set(prev) | set(new) if r.split('/')[0] == skill and r not in expected]
            for r in s['unknown']:
                expected[r] = t['observed'][r]['sha256']
            for r, sha in expected.items():
                checked += 1
                got = now.get(r, {}).get('sha256')
                if got != sha:
                    mismatches.append({'path': r, 'expected': sha, 'actual': got})
            for r in absent:
                if r in now:
                    mismatches.append({'path': r, 'expected': None, 'actual': now[r]['sha256']})
            extra = sorted(r for r in now if r.split('/')[0] == skill and r not in expected and r not in absent)
            mismatches += [{'path': r, 'expected': None, 'actual': now[r]['sha256']} for r in extra]
        report['targets'].append({'root': t['root'], 'status': t['status'], 'checked': checked,
                                  'mismatches': mismatches})
        report['ok'] = report['ok'] and not mismatches
    return report


# --------------------------------------------------------------------------- commandes

def cmd_manifest(args):
    doc = manifest_doc(compute_manifest(args.package))
    if args.out:
        write_json(Path(args.out), doc)
    return doc, 0


def cmd_preflight(args):
    prev = load_manifest(args.previous_manifest)
    new = load_manifest(args.new_manifest) if args.new_manifest else compute_manifest(args.new_package)
    check_layout(args.target, args.new_package, extra_paths=[args.plan_out])
    plan = build_plan(prev, new, args.new_package, args.target)
    plan['created_at'] = now_iso()
    write_json(Path(args.plan_out), plan)
    summary = {'plan': str(Path(args.plan_out)), 'plan_id': plan['plan_id'], 'fingerprint': plan['fingerprint'],
               'blocked': plan['blocked'], 'summary': plan['summary'], 'actions': len(plan['actions']),
               'targets': [{'root': t['root'], 'status': t['status'], 'reasons': t['reasons'],
                            'skills': {s['name']: s['status'] for s in t['skills']},
                            'conflicts': [c for s in t['skills'] for c in s['conflicts']],
                            'unknown': [u for s in t['skills'] for u in s['unknown']]}
                           for t in plan['targets']]}
    return summary, (2 if plan['blocked'] else 0)


def _final(plan, state, journal, label):
    report = verify_plan(plan, 'new')
    report['plan_id'] = plan['plan_id']
    write_json(Path(state) / f'rapport-{label}.json', report, replace=True)
    if not report['ok']:
        journal.append('final-mismatch')
        set_status(state, 'partial')
        raise UpdateError(f'Relecture finale différente : voir {Path(state) / f"rapport-{label}.json"}')
    journal.append('complete')
    set_status(state, 'complete')
    return report


def cmd_apply(args):
    plan = load_plan(args.plan)
    if plan['blocked'] and not args.allow_blocked:
        raise BlockedPlan('Plan bloqué (conflit ou profil refusé) ; relancer avec --allow-blocked '
                          'pour mettre à jour seulement les skills non bloqués')
    prev, new, package, targets = plan_inputs(plan)
    state = state_dir(args.state_dir, plan, targets, package)
    if state.exists():
        raise UpdateError(f'État déjà présent pour ce plan : {state} ; utiliser resume ou rollback '
                          '(après un rollback, refaire le préflight et choisir un nouveau --state-dir)')
    fresh = build_plan(prev, new, package, targets)
    if fresh['fingerprint'] != plan['fingerprint']:
        raise StalePlan('Plan périmé : l\'état observé ne correspond plus à l\'empreinte ; refaire le préflight')
    state.mkdir(parents=True)
    write_json(state / 'plan.json', plan)
    journal = Journal(state / 'journal.jsonl')
    with Lock(state):
        journal.append('apply-begin', fingerprint=plan['fingerprint'])
        set_status(state, 'in-progress')
        try:
            run_steps(plan, state, journal)
        except Exception as exc:
            journal.append('failed', error=f'{type(exc).__name__}: {exc}')
            set_status(state, 'partial', error=str(exc))
            raise
        report = _final(plan, state, journal, 'apply')
    return {'plan_id': plan['plan_id'], 'state': str(state), 'status': 'complete',
            'actions': len(plan['actions']), 'verify': report}, 0


def _open_state(args):
    plan = load_plan(args.plan)
    prev, new, package, targets = plan_inputs(plan)
    state = state_dir(args.state_dir, plan, targets, package)
    if not (state / 'journal.jsonl').exists():
        raise UpdateError(f'Aucun état d\'application pour ce plan : {state}')
    saved = load_plan(state / 'plan.json')
    if saved['fingerprint'] != plan['fingerprint']:
        raise UpdateError('Le plan fourni diffère du plan enregistré dans l\'état')
    return plan, new, package, state


def cmd_resume(args):
    plan, new, package, state = _open_state(args)
    status = read_status(state)
    if status == 'rolled-back':
        raise UpdateError('Plan déjà annulé par rollback ; refaire un préflight')
    journal = Journal(state / 'journal.jsonl')
    with Lock(state):
        # Contrôles complets d'abord ; aucun retrait avant qu'ils aient réussi (R2-06).
        check_state_outputs(state)
        leftovers, ignore = own_leftover_temps(plan, state, journal)
        check_package(package, new)
        check_progress(plan, ignore=ignore)
        removed = remove_own_temps(leftovers, journal, 'resume')
        journal.append('resume-begin', cleaned=removed)
        set_status(state, 'in-progress')
        try:
            run_steps(plan, state, journal)
        except Exception as exc:
            journal.append('failed', error=f'{type(exc).__name__}: {exc}')
            set_status(state, 'partial', error=str(exc))
            raise
        report = _final(plan, state, journal, 'resume')
    return {'plan_id': plan['plan_id'], 'state': str(state), 'status': 'complete',
            'cleaned_temps': removed, 'verify': report}, 0


def cmd_rollback(args):
    plan, _new, _package, state = _open_state(args)
    journal = Journal(state / 'journal.jsonl')
    with Lock(state):
        check_state_outputs(state)
        leftovers, ignore = own_leftover_temps(plan, state, journal)
        check_progress(plan, ignore=ignore)
        todo = []
        for a in reversed(plan['actions']):
            dest = dest_path(plan['targets'][a['target']]['root'], a['path'])
            cur = file_sha_or_none(dest)
            if cur == a['before']:
                continue
            data = None
            if a['op'] in ('replace', 'remove'):
                bp = backup_path(state, a)
                if not bp.exists() or sha256(bp.read_bytes()) != a['before']:
                    raise UpdateError(f"Sauvegarde absente ou altérée, aucune restauration : {bp}")
                data = bp.read_bytes()
            todo.append((a, dest, cur, data))
        # Retrait des seuls temporaires consignés, après tous les contrôles (R2-06).
        removed = remove_own_temps(leftovers, journal, 'rollback')
        journal.append('rollback-begin', steps=len(todo), cleaned=removed)
        set_status(state, 'rolling-back')
        for a, dest, cur, data in todo:
            if a['op'] == 'create':
                if file_sha_or_none(dest) != cur:
                    raise UpdateError(f'Changement concurrent détecté : {dest}')
                os.remove(dest)
            else:
                publish(dest, data, cur, plan['plan_id'], a['op'] == 'remove', journal, a['id'], a['target'])
            got = file_sha_or_none(dest)
            if got != a['before']:
                raise UpdateError(f"Restauration relue différente : {a['id']}")
            journal.append('rollback-verified', a['id'], sha256=got)
        for e in reversed(journal.created_dirs()):
            d = Path(e['dir'])
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                journal.append('rollback-rmdir', e['step'], dir=str(d))
        report = verify_plan(plan, 'previous')
        write_json(state / 'rapport-rollback.json', report, replace=True)
        if not report['ok']:
            set_status(state, 'rollback-mismatch')
            raise UpdateError('Relecture après restauration différente de l\'état antérieur')
        journal.append('rolled-back')
        set_status(state, 'rolled-back')
    return {'plan_id': plan['plan_id'], 'state': str(state), 'status': 'rolled-back',
            'restored': len(todo), 'cleaned_temps': removed, 'verify': report}, 0


def cmd_verify(args):
    report = verify_plan(load_plan(args.plan), args.expect)
    return report, (0 if report['ok'] else 1)


def parser():
    p = argparse.ArgumentParser(prog='rc_update', description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='command', required=True)
    m = sub.add_parser('manifest')
    m.add_argument('--package', required=True)
    m.add_argument('--out')
    f = sub.add_parser('preflight')
    f.add_argument('--previous-manifest', required=True)
    f.add_argument('--new-package', required=True)
    f.add_argument('--new-manifest', help='manifeste figé de la nouvelle version (sinon calculé)')
    f.add_argument('--target', action='append', required=True, help='racine skills d\'un profil (répétable)')
    f.add_argument('--plan-out', required=True)
    a = sub.add_parser('apply')
    a.add_argument('--plan', required=True)
    a.add_argument('--state-dir', required=True)
    a.add_argument('--allow-blocked', action='store_true')
    for name in ('resume', 'rollback'):
        r = sub.add_parser(name)
        r.add_argument('--plan', required=True)
        r.add_argument('--state-dir', required=True)
    v = sub.add_parser('verify')
    v.add_argument('--plan', required=True)
    v.add_argument('--expect', choices=('new', 'previous'), default='new')
    return p


COMMANDS = {'manifest': cmd_manifest, 'preflight': cmd_preflight, 'apply': cmd_apply,
            'resume': cmd_resume, 'rollback': cmd_rollback, 'verify': cmd_verify}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result, code = COMMANDS[args.command](args)
    except UpdateError as exc:
        print(json.dumps({'error': str(exc), 'code': exc.code}, ensure_ascii=False), file=sys.stderr)
        return exc.code
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': f'{type(exc).__name__}: {exc}', 'code': 1}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
