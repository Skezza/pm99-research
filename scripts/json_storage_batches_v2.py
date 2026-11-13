"""Inventoried, journalled JSON inode-group conversion; no recursive deletion.

Inventory is a dry run. Conversion takes explicit manifest groups, preserves
all aliases, checks original byte hashes under locks, and retains recoverable
representations after interruption. Recovery deterministically completes the
journal's requested representation, or restores plain files when requested.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import json_storage_v1 as storage

MIN_RESERVE = 6 * 1024**3
BATCH_LIMIT = 1024**3
from scripts.json_storage_policy_v2 import SKIP_DIRS, EXCLUDED_ROOTS, excluded
_PIN_CACHE = {}


PROGRESS = None


def inbound_json_symlinks(root):
    targets=set();pending=[str(root)]
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_symlink():
                    resolved=storage.logical_path(Path(entry.path).resolve())
                    if resolved.is_relative_to(root) and (resolved.suffix=='.json' or resolved.is_dir()):
                        targets.add(resolved)
                elif entry.is_dir(follow_symlinks=False) and entry.name not in SKIP_DIRS and entry.name!='upstream':
                    pending.append(entry.path)
    return targets


def open_inode_set():
    identities=set()
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:
            for descriptor in (process/'fd').iterdir():
                try:s=descriptor.stat()
                except OSError:continue
                if stat.S_ISREG(s.st_mode):identities.add((s.st_dev,s.st_ino))
        except OSError:continue
    return identities


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def catalog_hash(root):
    return digest(root / 'data/preferred-season-releases-v1.json')


def _occurrences(text, needle):
    offset=0
    while True:
        index=text.find(needle,offset)
        if index<0:return
        yield index
        offset=index+len(needle)


def _path_strings(text, root):
    # Search rare complete literals in C rather than testing a regex at every
    # quote in millions of player fields. Decode only the matching JSON token.
    files=set();locals_=set()
    for suffix in ('.json"','.json.zst"'):
        for index in _occurrences(text,suffix):
            start=text.rfind('"',0,index)
            while start>=0:
                back=start-1
                while back>=0 and text[back]=='\\':back-=1
                if (start-back-1)%2==0:break
                start=text.rfind('"',0,start)
            if start<0:raise storage.StorageError('unterminated path-bearing JSON string')
            files.add(json.loads(text[start:index+len(suffix)]))
    decoder=json.JSONDecoder()
    for prefix in ('".local/','"'+str(root)+'/.local/'):
        for index in _occurrences(text,prefix):
            value,_=decoder.raw_decode(text,index);locals_.add(value)
    return tuple(files),tuple(locals_)


def _parent_strings(text):
    result=set();decoder=json.JSONDecoder()
    for key in ('release_id','parent_release_id','source_release_id'):
        needle='"'+key+'"'
        for index in _occurrences(text,needle):
            offset=index+len(needle)
            while offset<len(text) and text[offset].isspace():offset+=1
            if offset==len(text) or text[offset]!=':':continue
            offset+=1
            while offset<len(text) and text[offset].isspace():offset+=1
            if offset<len(text) and text[offset]=='"':
                value,_=decoder.raw_decode(text,offset);result.add(value)
    return result


def protected_paths(root):
    catalog = json.loads((root / 'data/preferred-season-releases-v1.json').read_text())
    pins, registered = set(), set()
    selected = {(r['season'], r['release_id']) for r in catalog['seasons']}
    selected.add(('2015-16', 'legacy-world-2015-16'))
    locators=list((root / '.local/season-release-registry-v1/releases').glob('*/*/locator.json'))
    locations={}
    for p in locators:locations.setdefault(p.parent.name,set()).add(p)
    initial=[]
    for p in locators:
        d = json.loads(p.read_text())
        refs = {storage.logical_path(root / v) for v in d.values() if isinstance(v, str) and v.startswith('.local/')}
        registered.update(refs)
        if (p.parent.parent.name, p.parent.name) in selected:
            pins.update(refs)
            initial.append(p)
            initial.extend(x for x in refs if x.suffix=='.json')
    key=(str(root),catalog_hash(root),tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size)
                                         for p in initial if p.name=='locator.json'))
    if key in _PIN_CACHE:
        return set(_PIN_CACHE[key]),registered
    # Traverse path-bearing JSON strings and release-parent descriptors, including
    # relative artifacts. Do not deserialize hundreds of thousands of player rows.
    queue=[];queued=set();seen=set();references={};last_progress=time.monotonic();read_bytes=0
    def enqueue(path):
        path=path.absolute()
        if path not in queued:
            queued.add(path);queue.append(path)
    for p in initial:enqueue(p)
    while queue:
        p=queue.pop()
        p=p.absolute()
        if p in seen:continue
        seen.add(p);pins.add(p)
        if len(seen)>100000:raise storage.StorageError('protected dependency graph exceeded audit bound')
        if p.suffix!='.json' or not storage.is_file(p):continue
        meta=storage.physical_path(p).stat()
        identity=(meta.st_dev,meta.st_ino,meta.st_size,meta.st_mtime_ns,meta.st_ctime_ns)
        if identity not in references:
            raw=storage.read_bytes(p);read_bytes+=len(raw);text=raw.decode('utf8');del raw
            files,locals_=_path_strings(text,root)
            releases=_parent_strings(text)
            references[identity]=(files,locals_,releases)
        files,locals_,releases=references[identity]
        if PROGRESS and time.monotonic()-last_progress>10:
            PROGRESS(dict(stage='dependency-closure',seen=len(seen),queued=len(queue),read_bytes=read_bytes,path=str(p.relative_to(root))))
            last_progress=time.monotonic()
        season_match=re.search(r'(?:19|20)\d{2}-\d{2}',str(p))
        for value in files:
            if '://' in value:continue
            candidate=(root/value) if value.startswith('.local/') else (Path(value) if Path(value).is_absolute() else p.parent/value)
            candidate=storage.logical_path(candidate.resolve())
            if candidate.is_relative_to(root/'.local') and storage.is_file(candidate):enqueue(candidate)
        for value in locals_:
            candidate=storage.logical_path((root/value if value.startswith('.local/') else Path(value)).resolve())
            if candidate.is_relative_to(root/'.local'):
                pins.add(candidate)
                if candidate.suffix=='.json' and storage.is_file(candidate):enqueue(candidate)
        if season_match:
            for release in releases:
                for parent in locations.get(release,()):enqueue(parent)
    if PROGRESS:PROGRESS(dict(stage='dependency-closure-complete',seen=len(seen),read_bytes=read_bytes,pins=len(pins)))
    _PIN_CACHE[key]=frozenset(pins)
    return pins, registered


def inventory(root=ROOT):
    root = root.resolve()
    pins, registered = protected_paths(root)
    inbound=inbound_json_symlinks(root)
    opened=open_inode_set()
    nodes = {}
    for directory, dirs, files in os.walk(root / '.local'):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not Path(directory, d).is_symlink()]
        for name in files:
            if not name.endswith('.json'):
                continue
            p = Path(directory, name)
            s = p.lstat()
            if not stat.S_ISREG(s.st_mode) or s.st_size < storage.AUTO_MIN_BYTES:
                continue
            key = (s.st_dev, s.st_ino)
            row = nodes.setdefault(key, {'paths': [], 'logical_bytes': s.st_size,
                                        'allocated_bytes': s.st_blocks * 512, 'links': s.st_nlink,
                                        'uid': s.st_uid, 'gid': s.st_gid, 'mode': stat.S_IMODE(s.st_mode),
                                        'mtime_ns': s.st_mtime_ns})
            row['paths'].append(str(p.relative_to(root)))
    groups, exclusions = [], []
    for row in nodes.values():
        paths = [root / p for p in row['paths']]
        roots = {Path(p).parts[1] for p in row['paths']}
        reason = None
        if len(paths) != row['links']:
            reason = 'incomplete-or-external-inode-aliases'
        elif any(p in inbound or any(parent in inbound for parent in p.parents) for p in paths):
            reason = 'inbound-file-symlink'
        elif (paths[0].stat().st_dev,paths[0].stat().st_ino) in opened:
            reason = 'open-file-handle'
        elif row['mtime_ns'] > (time.time()-3600)*10**9:
            reason = 'recent-active-output'
        elif any(p in pins or any(parent in pins for parent in p.parents) for p in paths):
            reason = 'preferred-or-original-input'
        elif any(excluded(p) for p in row['paths']):
            reason = 'control-working-or-evidence-data'
        elif row['logical_bytes'] > storage.MAX_DECODED_BYTES:
            reason = 'over-decoder-limit'
        elif row['uid'] != os.geteuid():
            reason = 'different-owner'
        row['registered'] = any(p in registered for p in paths)
        if reason:
            exclusions.append(dict(row, reason=reason))
        else:
            groups.append(row)
    return {'schema': 'pm99-json-storage-inventory-v2', 'utc': datetime.now(timezone.utc).isoformat(),
            'catalog_sha256': catalog_hash(root), 'groups': groups, 'exclusions': exclusions}


def make_manifest(inv, *, root=ROOT, roots, registered=False, limit=BATCH_LIMIT):
    selected, total = [], 0
    for group in inv['groups']:
        if group['registered'] and not registered:
            continue
        if any(Path(p).parts[1] not in roots for p in group['paths']):
            continue
        if total + group['allocated_bytes'] > limit:
            continue
        paths = [root / p for p in group['paths']]
        expected = digest(paths[0])
        json.loads(paths[0].read_bytes().decode('utf-8'))
        selected.append(dict(group, sha256=expected))
        total += group['allocated_bytes']
    return {'schema': 'pm99-json-storage-batch-v2', 'catalog_sha256': inv['catalog_sha256'],
            'scope': 'historical-registered' if registered else 'inactive',
            'allocated_bytes': total, 'groups': selected}


def _event(handle, **data):
    handle.write(json.dumps(data) + '\n')
    handle.flush()
    os.fsync(handle.fileno())


def _validate_paths(group, root):
    paths = []
    for rel in group['paths']:
        p = root / rel
        if (Path(rel).is_absolute() or '..' in Path(rel).parts or not rel.startswith('.local/')
                or p.suffix != '.json' or p.resolve() != p or SKIP_DIRS.intersection(Path(rel).parts)):
            raise storage.StorageError('unsafe group path: ' + rel)
        if excluded(rel):
            raise storage.StorageError('control/working root excluded at apply time: '+rel)
        paths.append(p)
    if not paths or len(set(paths)) != len(paths):
        raise storage.StorageError('empty or repeated alias group')
    return paths


def convert_group(group, journal, *, root=ROOT, restore=False, recover=False):
    """Every published representation is verified before its counterpart retires."""
    paths = _validate_paths(group, root)
    with ExitStack() as stack:
        for parent in sorted({p.parent for p in paths}):
            stack.enter_context(storage._directory_lock(parent / 'group.json', exclusive=True))
        sources = [storage.compressed_path(p) if restore else p for p in paths]
        destinations = [p if restore else storage.compressed_path(p) for p in paths]
        available = [p for p in sources + destinations if p.exists()]
        if not available:
            raise storage.StorageError('all group representations are missing')
        raw_source = next((p for p in paths if p.exists()), None)
        frame_source = next((storage.compressed_path(p) for p in paths if storage.compressed_path(p).exists()), None)
        source = raw_source or frame_source
        s = source.lstat()
        snapshots={p:(p.stat().st_dev,p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns)
                   for p in sources if p.exists()}
        if source.is_symlink() or not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid():
            raise storage.StorageError('unsafe group source')
        if not 0 < group['logical_bytes'] <= storage.MAX_DECODED_BYTES:
            raise storage.StorageError('document exceeds decoder limit')
        if raw_source and raw_source.stat().st_size > storage.MAX_DECODED_BYTES:
            raise storage.StorageError('raw source exceeds decoder limit before buffering')
        data = raw_source.read_bytes() if raw_source else b''.join(storage._decoded_chunks(frame_source))
        if len(data) != group['logical_bytes'] or hashlib.sha256(data).hexdigest() != group['sha256']:
            raise storage.StorageError('locked original bytes differ before group conversion')
        json.loads(data.decode('utf8'))
        if not recover:
            identity = (s.st_dev, s.st_ino)
            for p in sources:
                t = p.lstat()
                if p.is_symlink() or (t.st_dev, t.st_ino) != identity or t.st_nlink != len(paths):
                    raise storage.StorageError('alias inventory changed or has external links')
            if any(p.exists() or p.is_symlink() for p in destinations):
                raise storage.StorageError('destination exists before group conversion')
        # Recovery verifies every surviving alias before choosing the journal's target state.
        verified = set()
        for p in available:
            if p.is_symlink():
                raise storage.StorageError('symlink appeared in group')
            meta = p.stat()
            if (stat.S_IMODE(meta.st_mode) != group['mode'] or meta.st_uid != group['uid']
                    or meta.st_gid != group['gid']):
                raise storage.StorageError('alias access metadata changed')
            key = (meta.st_dev, meta.st_ino)
            if key in verified:
                continue
            value = b''.join(storage._decoded_chunks(p)) if p.name.endswith('.json.zst') else p.read_bytes()
            if hashlib.sha256(value).hexdigest() != group['sha256']:
                raise storage.StorageError('a surviving alias has different bytes; manual review required')
            verified.add(key)
        # Recovery may see partially retired aliases. Every inode must still have
        # exactly the aliases present in this manifest; otherwise stop without unlink.
        if recover:
            for identity in verified:
                aliases=[p for p in available if (p.stat().st_dev,p.stat().st_ino)==identity]
                if aliases[0].stat().st_nlink != len(aliases):
                    # SIGKILL can leave our staged publication anchor. Only remove
                    # reserved temporary names linked to this verified group inode.
                    for parent in {p.parent for p in paths}:
                        for candidate in parent.glob('.json-storage-*'):
                            if candidate.is_symlink() or not candidate.is_file():continue
                            t=candidate.stat()
                            if (t.st_dev,t.st_ino)==identity:
                                _event(journal,event='recovery-staging-cleanup',path=str(candidate.relative_to(root)))
                                candidate.unlink();storage._fsync_directory(parent)
                    if aliases[0].stat().st_nlink != len(aliases):
                        raise storage.StorageError('recovery has external aliases; refresh the reviewed manifest')
        anchor = next((p for p in destinations if p.exists()), None)
        planned = 0 if anchor else (group['logical_bytes'] if restore else int(group['logical_bytes'] * 1.01) + storage.CHUNK)
        if shutil.disk_usage(paths[0].parent).free - planned < MIN_RESERVE:
            raise storage.StorageError('group staging would breach the six GiB hard reserve')
        temporary = None if anchor else storage._stage(destinations[0], data, compressed=not restore, mode=group['mode'])
        try:
            if temporary is not None and temporary.stat().st_gid != group['gid']:
                os.chown(temporary, -1, group['gid'])
            if temporary is not None: os.utime(temporary, ns=(s.st_atime_ns, group['mtime_ns']))
            if not restore and temporary is not None and temporary.stat().st_blocks * 512 >= s.st_blocks * 512 * .9:
                raise storage.StorageError('group compression saves less than ten percent')
            _event(journal, event='group-prepared', restore=restore, group=group)
            anchor = anchor or temporary
            for p in destinations:
                if p.exists() and os.path.samefile(p, anchor):
                    continue
                if p.exists():
                    replacement = p.with_name('.json-storage-recover-' + p.name)
                    try:
                        os.link(anchor, replacement)
                        os.replace(replacement, p)
                    finally:
                        replacement.unlink(missing_ok=True)
                else:
                    os.link(anchor, p)
                storage._fsync_directory(p.parent)
                _event(journal, event='target-published', path=str(p.relative_to(root)))
            # Recheck original bytes after compression, before any unlink.
            if raw_source is not None and raw_source.exists() and digest(raw_source) != group['sha256']:
                raise storage.StorageError('source changed before group retirement')
            if not recover:
                for p in sources:
                    current = p.stat()
                    stamp=(current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns)
                    if stamp != snapshots[p]:
                        raise storage.StorageError('source alias replaced before retirement')
            for p in sources:
                if p.exists():
                    p.unlink()
                    storage._fsync_directory(p.parent)
                    _event(journal, event='source-retired', path=str(p.relative_to(root)))
            after = {}
            for p in destinations:
                t = p.stat();after[(t.st_dev,t.st_ino)] = t.st_blocks * 512
            _event(journal, event='group-complete', restore=restore, paths=group['paths'],
                   allocated_after=sum(after.values()), original_sha256=group['sha256'])
            return sum(after.values())
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)


def apply(manifest, receipt, *, root=ROOT, restore=False, recover=False):
    if manifest['schema'] != 'pm99-json-storage-batch-v2' or manifest['allocated_bytes'] > BATCH_LIMIT:
        raise ValueError('invalid or oversized batch')
    if catalog_hash(root) != manifest['catalog_sha256']:
        raise ValueError('catalogue changed; re-audit the batch')
    pins, registered = protected_paths(root)
    inbound=inbound_json_symlinks(root)
    opened=open_inode_set()
    actual_before={}
    for group in manifest['groups']:
        paths = _validate_paths(group, root)
        if any(p in pins or any(parent in pins for parent in p.parents) for p in paths):
            raise ValueError('batch contains preferred/original inputs')
        if manifest['scope'] != 'historical-registered' and any(p in registered for p in paths):
            raise ValueError('registered input requires its audited migration scope')
        if any(p in inbound or any(parent in inbound for parent in p.parents) for p in paths):raise ValueError('inbound JSON symlink requires a separate migration')
        for p in paths:
            physical=storage.compressed_path(p) if restore else p
            if physical.exists():
                s=physical.stat()
                if (s.st_dev,s.st_ino) in opened:raise ValueError('batch input has an open file handle')
                actual_before[(s.st_dev,s.st_ino)]=s.st_blocks*512
                if not restore and not recover and s.st_mtime>time.time()-3600:
                    raise ValueError('batch input is a recent active output')
        if not 0<group['logical_bytes']<=storage.MAX_DECODED_BYTES:
            raise ValueError('batch document exceeds its decoded-size limit')
    if not restore and sum(actual_before.values())>BATCH_LIMIT:
        raise ValueError('actual allocation exceeds the one GiB batch cap')
    with Path(receipt).open('x') as handle:
        _event(handle, event='batch-prepared', manifest=manifest, restore=restore,
               utc=datetime.now(timezone.utc).isoformat())
        after = 0
        for group in manifest['groups']:
            if catalog_hash(root) != manifest['catalog_sha256']:
                raise ValueError('catalogue changed during batch')
            after += convert_group(group, handle, root=root, restore=restore, recover=recover)
        _event(handle, event='batch-complete', groups=len(manifest['groups']), allocated_after=after,
               original_allocated=manifest['allocated_bytes'], restore=restore)
    return after


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['inventory', 'apply', 'restore', 'recover'])
    p.add_argument('input', type=Path, nargs='?')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.operation == 'inventory':
        with a.output.open('x') as handle:
            json.dump(inventory(), handle, indent=2)
    else:
        text=a.input.read_text();direction=a.operation=='restore'
        if a.operation=='recover':
            header=json.loads(text.splitlines()[0])
            if header.get('event')!='batch-prepared':raise ValueError('recovery requires the original batch journal')
            value=header['manifest'];direction=bool(header['restore'])
        else:value=json.loads(text)
        apply(value, a.output, restore=direction, recover=a.operation == 'recover')


if __name__ == '__main__':
    main()
