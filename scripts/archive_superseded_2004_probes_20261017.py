"""Archive unregistered old probes to the verified Pi volume before retirement.

Exact member-SHA verification on the Pi and a second local source check are
required before removing these ten explicit experimental directories. No game,
recipe or source referenced by any registered release may be a target.
"""
from collections import Counter
from datetime import UTC,datetime
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile

from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.archive_rejected_rating_recovery_to_pi_20261011 import HOST,UUID,ssh
from scripts.archive_rejected_role_trials_20261016 import active
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/cleanup-20261017/superseded-2004-probes-to-pi'
SOURCE=registry.ROOT/'.local/probes'
NAMES=('2004-05-english-only','2004-05-futurefix','2004-05-futurefix-receipts',
    '2004-05-stoke-coherent','2004-05-stoke-g1','2004-05-stoke-g2','2004-05-stoke-g3',
    '2004-05-stoke-g4','2004-05-stoke-minimal','2004-05-stoke-only')
REMOTE='/srv/hdd/pm99-archive/research/probes/20261017/2004-05-unregistered-probes.tar.gz'


def no_registered_references(*,extra_roots=()):
    relative=[registry.relative_workspace_path(SOURCE/name) for name in NAMES]
    absolute=[str(SOURCE/name) for name in NAMES]
    needles=relative+absolute
    prefixes=(os.path.commonprefix(relative),os.path.commonprefix(absolute))
    roots=(registry.CATALOG_PATH.parent,registry.LOCAL_ROOT,
        registry.ROOT/'.local/historical-role-deltas-v1',*extra_roots)
    seen=set()
    for root in roots:
        for directory,folders,files in os.walk(root):
            path_root=type(root)(directory)
            # Native game trees contain millions of bitmap assets, not build
            # descriptors. SOURCE inputs live beside game/, and registered
            # inventory/locator/manifest JSON remains fully checked above.
            if root==roots[2] and len(path_root.relative_to(root).parts)==2 and 'game' in folders:
                folders.remove('game')
            elif root in extra_roots and 'game' in folders:
                native=path_root/'game'
                if (native/'DBDAT').is_dir() and (native/'MANAGPRE.EXE').is_file():
                    folders.remove('game')
            for name in files:
                if not name.endswith('.json'):continue
                path=path_root/name;info=path.stat()
                key=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
                # Immutable SOURCE artifacts are hardlinked across hundreds
                # of releases. Inspect the same unchanged bytes once, without
                # dropping any metadata path or source directory from scope.
                if key in seen:continue
                seen.add(key)
                text=path.read_text()
                if any(prefix in text for prefix in prefixes) and any(needle in text for needle in needles):
                    raise ValueError('registered release or retained SOURCE metadata references a probe: '+str(path))


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if (ROOT/'members.json').exists():
        raise ValueError('existing probe archive ledger requires inspection, not blind repetition')
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip()!=UUID:
        raise ValueError('Pi archive volume missing or changed')
    no_registered_references()
    targets=[SOURCE/name for name in NAMES]
    for path in targets:
        if (path.parent!=SOURCE or path.resolve()!=path or path.is_symlink()
                or not path.is_dir() or active(path)):
            raise ValueError('unexpected or active exact probe target')
    members=[]
    for target in targets:
        for path in sorted(target.rglob('*')):
            if path.is_symlink():
                raise ValueError('probe archive refuses symlinks')
            if path.is_file():
                members.append((path,path.relative_to(SOURCE).as_posix()))
            elif not path.is_dir():
                raise ValueError('probe archive refuses special non-directory files')
    if not members:
        raise ValueError('no original probe files to archive')
    expected={name:dict(sha256=registry.sha256_file(path),size=path.stat().st_size) for path,name in members}
    links=Counter((p.stat().st_dev,p.stat().st_ino) for p,_ in members)
    allocated={}
    for path,_ in members:
        stat=path.stat();key=(stat.st_dev,stat.st_ino)
        if links[key]==stat.st_nlink:
            allocated[key]=stat.st_blocks*512
    retained(ROOT/'members.json',dict(utc=datetime.now(UTC).isoformat(),remote_archive=REMOTE,
        targets=[registry.relative_workspace_path(p) for p in targets],members=expected,
        all_registered_releases_reference_checked=True,recoverable_allocated_bytes=sum(allocated.values())))
    catalog=registry.sha256_file(registry.CATALOG_PATH)
    before_free=shutil.disk_usage(registry.ROOT).free
    folder=REMOTE.rsplit('/',1)[0]
    command='mkdir -p {d} && test ! -e {p} && test ! -e {p}.partial && cat > {p}.partial'.format(
        d=shlex.quote(folder),p=shlex.quote(REMOTE))
    print(dict(uploading_probe_files=len(members),removed_paths=0),flush=True)
    process=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',HOST,command],stdin=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdin,mode='w|gz',compresslevel=1,dereference=False) as archive:
            for path,name in members:
                archive.add(path,arcname=name,recursive=False)
        process.stdin.close()
        if process.wait()!=0:
            raise ValueError('Pi probe archive upload failed; local originals retained')
    finally:
        if process.poll() is None:
            process.terminate();process.wait()
    code='''import hashlib,json,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]);expected=json.load(sys.stdin)
with tarfile.open(str(p)+'.partial','r:gz') as archive:
 members=archive.getmembers()
 if len(members)!=len(expected) or {m.name for m in members}!=set(expected):raise ValueError('archive member set differs')
 for m in members:
  if not m.isfile() or m.size!=expected[m.name]['size']:raise ValueError('archive member type/size differs')
  if hashlib.file_digest(archive.extractfile(m),'sha256').hexdigest()!=expected[m.name]['sha256']:raise ValueError('archive member SHA differs')
if p.exists():raise ValueError('archive destination already exists')
pathlib.Path(str(p)+'.partial').rename(p)
print(json.dumps(dict(archive_sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),members_verified=len(expected),member_hashes_verified=True)))
'''
    checked=json.loads(ssh('python3 -c '+shlex.quote(code)+' '+shlex.quote(REMOTE),input=json.dumps(expected)))
    retained(ROOT/'pi-member-verification.json',dict(checked,host=HOST,volume_uuid=UUID,archive_path=REMOTE))
    for path,name in members:
        if path.stat().st_size!=expected[name]['size'] or registry.sha256_file(path)!=expected[name]['sha256']:
            raise ValueError('probe source changed during transfer; do not remove it')
    no_registered_references()
    if registry.sha256_file(registry.CATALOG_PATH)!=catalog:
        raise ValueError('preferred catalogue changed during archive; preserve originals and inspect')
    for target in targets:
        if target.resolve()!=target or active(target):
            raise ValueError('probe became active; originals retained')
    retained(ROOT/'pre-removal-proof.json',dict(local_sources_unchanged=True,pi_all_member_hashes_verified=True,
        catalogue_sha256=catalog,removed_paths=[]))
    for target in targets:
        shutil.rmtree(target)
    retained(ROOT/'completed.json',dict(utc=datetime.now(UTC).isoformat(),
        removed_local_paths=[registry.relative_workspace_path(p) for p in targets],
        remote_archive=REMOTE,remote_member_verification=checked,
        recoverable_allocated_bytes=sum(allocated.values()),before_free_bytes=before_free,
        after_free_bytes=shutil.disk_usage(registry.ROOT).free,current26_and_original2015_untouched=True,
        recovery='Restore the named experimental directories from the verified Pi tar archive under '+registry.relative_workspace_path(SOURCE)+'; no registered release uses these paths.',
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))
    print(dict(probe_directories_moved=len(targets),all_files_recoverable_on_pi=True,
        allocated_bytes_recovered=sum(allocated.values())),flush=True)


if __name__=='__main__':
    main()
