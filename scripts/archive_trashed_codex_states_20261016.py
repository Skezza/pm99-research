"""Move two already-trashed application states to verified private Pi backup.

Do not follow symlinks or touch the live Codex directory, other Trash members,
PM99 games, sources or active development caches.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from datetime import UTC,datetime

from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.archive_rejected_rating_recovery_to_pi_20261011 import ssh,HOST,UUID
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/cleanup-20261016/trashed-codex-states'
REMOTE='/srv/hdd/pm99-archive/workstation-recovery/20261016/trashed-codex-states'
SOURCES=(Path('/home/joe/.local/share/Trash/files/.codex-vostro2'),
         Path('/home/joe/.local/share/Trash/files/.codex-vostro3'))


def inventory(root):
    rows=[]
    for directory,dirs,files in os.walk(root,followlinks=False):
        for name in sorted(dirs+files):
            path=Path(directory)/name;relative=path.relative_to(root).as_posix()
            if path.is_symlink():row=dict(path=relative,type='symlink',target=os.readlink(path))
            elif path.is_dir():row=dict(path=relative,type='directory')
            elif path.is_file():
                with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                row=dict(path=relative,type='file',size=path.stat().st_size,sha256=digest)
            else:raise ValueError('special file prevents archive')
            rows.append(row)
    return sorted(rows,key=lambda row:row['path'])


def guard(path):
    if path not in SOURCES or path.is_symlink() or path.resolve()!=path or not path.is_dir():
        raise ValueError('exact already-trashed leaf required')
    if str(path) in subprocess.check_output(['ps','-eo','args'],text=True):
        raise ValueError('trashed application state appears active')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:cwd=(proc/'cwd').resolve(strict=True)
        except (OSError,RuntimeError):continue
        if cwd==path or path in cwd.parents:raise ValueError('process still uses trashed directory')
        try:descriptors=list((proc/'fd').iterdir())
        except OSError:continue
        for descriptor in descriptors:
            try:target=os.readlink(descriptor)
            except OSError:continue
            if target==str(path) or target.startswith(str(path)+'/'):
                raise ValueError('process still has an open trashed-state member')
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip()!=UUID:raise ValueError('wrong/unmounted Pi volume')


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    for path in SOURCES:
        label=path.name.lstrip('.');receipt=ROOT/(label+'-completed.json')
        if receipt.exists():
            if path.exists():raise ValueError('previously archived Trash state was recreated')
            print(dict(archive=label,already_complete=True),flush=True);continue
        guard(path);rows=inventory(path);retained(ROOT/(label+'-inventory.json'),rows)
        remote=REMOTE+'/'+label
        ssh('mkdir -p '+shlex.quote(REMOTE))
        subprocess.run(['rsync','-a','--checksum','--ignore-existing',str(path)+'/',HOST+':'+remote+'/'],check=True)
        code='import hashlib,json,os,sys\nfrom pathlib import Path\n'+inspect.getsource(inventory)+'''
expected=json.load(sys.stdin)
if inventory(Path(sys.argv[1]))!=expected:raise ValueError('remote member SHA/link inventory differs')
print(json.dumps(dict(all_members_verified=True,members=len(expected))))
'''
        checked=json.loads(ssh('python3 -c '+shlex.quote(code)+' '+shlex.quote(remote),input=json.dumps(rows)))
        if checked!=dict(all_members_verified=True,members=len(rows)):raise ValueError('remote archive proof missing')
        guard(path)
        if inventory(path)!=rows:raise ValueError('local Trash state changed during backup')
        proof=dict(utc=datetime.now(UTC).isoformat(),machine='joe-Vostro-3350',
            source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',source=str(path),
            remote_host=HOST,remote_path=remote,volume_uuid=UUID,
            inventory_path=registry.relative_workspace_path(ROOT/(label+'-inventory.json')),
            verified_members=len(rows),logical_file_bytes=sum(r.get('size',0) for r in rows),
            symlinks_preserved_not_followed=True,live_Codex_and_PM99_untouched=True,
            recovery='Restore this exact Trash leaf with rsync -a from remote_path; original Trash info retained locally.')
        retained(ROOT/(label+'-verified-before-removal.json'),proof)
        subprocess.run(['rsync','-a',str(ROOT)+'/',HOST+':'+REMOTE+'/receipts/'],check=True)
        shutil.rmtree(path)
        retained(receipt,proof)
        subprocess.run(['rsync','-a',str(receipt),HOST+':'+REMOTE+'/receipts/'],check=True)
        print(dict(archive=label,remote_member_SHA_verified=True,local_trashed_copy_removed=True,
            logical_file_bytes=proof['logical_file_bytes'],free_bytes=shutil.disk_usage(registry.ROOT).free),flush=True)


if __name__=='__main__':main()
