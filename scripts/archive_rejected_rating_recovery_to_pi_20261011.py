"""Offload only this turn's already-rejected, recoverable r100 trial archives."""
import hashlib
import json
import shlex
import subprocess
from datetime import UTC,datetime
from pathlib import Path
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/rating-calibration-v1'
RECOVERY=ROOT/'rejected-recovery'
LEDGER=ROOT.parent/'rating-calibration-v3/pi-rejected-trial-transfer-ledger.json'
HOST='joe@192.168.1.133'
REMOTE='/srv/hdd/pm99-archive/packages/rejected-rating-trials/20261011/r100-recovery'
UUID='1f364414-880d-4f96-8619-3bd8c9954cc0'

def ssh(command,**kw):
    return subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',HOST,command],
        check=True,text=True,capture_output=True,**kw).stdout

def run():
    if LEDGER.exists():raise ValueError('completed rejected-trial transfer must not repeat')
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip()!=UUID:raise ValueError('wrong or unmounted Pi archive drive')
    ssh('test ! -e '+shlex.quote(REMOTE)+' && mkdir -p '+shlex.quote(REMOTE))
    files=sorted(p for p in RECOVERY.iterdir() if p.is_file())
    archives=[p for p in files if p.name.endswith('.tar.gz')]
    if len(archives)!=20 or any(p.is_symlink() or p.parent.resolve()!=RECOVERY.resolve() for p in files):
        raise ValueError('unexpected rejected-trial archive scope')
    catalog_before=registry.sha256_file(registry.CATALOG_PATH)
    expected=[dict(name=p.name,sha256=registry.sha256_file(p),size=p.stat().st_size) for p in files]
    subprocess.run(['rsync','-a','--checksum','--ignore-existing',str(RECOVERY)+'/',HOST+':'+REMOTE+'/'],check=True)
    metadata=[ROOT/n for n in ('rejected-trial-retirement-ledger.json','rejected-source-plan-archive-ledger.json',
        'rejected-recovery-representation-index.json')]
    for p in metadata:
        subprocess.run(['rsync','-a','--checksum','--ignore-existing',str(p),HOST+':'+REMOTE+'/'],check=True)
    expected.extend(dict(name=p.name,sha256=registry.sha256_file(p),size=p.stat().st_size) for p in metadata)
    code='''import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);rows=json.load(sys.stdin)
for row in rows:
 p=root/row['name']
 if p.parent.resolve()!=root.resolve() or p.stat().st_size!=row['size']:raise ValueError('remote size/path differs')
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 if h.hexdigest()!=row['sha256']:raise ValueError('remote SHA differs')
print(json.dumps(dict(verified_files=len(rows),all_exact=True)))
'''
    verified=json.loads(ssh('python3 -c '+shlex.quote(code)+' '+shlex.quote(REMOTE),input=json.dumps(expected)))
    if verified!={'verified_files':len(expected),'all_exact':True}:raise ValueError('remote verification incomplete')
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip()!=UUID:raise ValueError('Pi volume changed during verification')
    if registry.sha256_file(registry.CATALOG_PATH)!=catalog_before:raise ValueError('preferred releases changed during archival')
    by_name={r['name']:r for r in expected};removed=[]
    for p in archives:
        row=by_name[p.name]
        if registry.sha256_file(p)!=row['sha256'] or p.stat().st_size!=row['size']:
            raise ValueError('local rejected archive changed before retirement')
    receipt=dict(utc=datetime.now(UTC).isoformat(),source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        machine='joe-Vostro-3350',host=HOST,remote_root=REMOTE,mounted_volume_uuid=UUID,
        files=expected,all_remote_bytes_SHA256_verified=True,preferred_catalog_sha256=catalog_before,
        local_archive_removals=[registry.relative_workspace_path(p) for p in archives],
        bytes_recovered=sum(p.stat().st_size for p in archives),
        recovery='Restore each moved archive by its recorded name from remote_root; original member recovery indices remain local and are copied remotely.')
    pipeline.write_canonical_json(LEDGER,receipt)
    for p in archives:p.unlink()
    subprocess.run(['rsync','-a','--checksum',str(LEDGER),HOST+':'+REMOTE+'/'],check=True)
    if registry.sha256_file(registry.CATALOG_PATH)!=catalog_before:raise ValueError('preferred catalogue unexpectedly changed')
    print(dict(archive_files_moved=len(archives),bytes_recovered=receipt['bytes_recovered'],remote=REMOTE,
        ledger=registry.relative_workspace_path(LEDGER),all_current_games_untouched=True),flush=True)

if __name__=='__main__':run()
