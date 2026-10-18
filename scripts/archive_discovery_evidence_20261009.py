"""Verify Pi backups of audit evidence and optionally retire old CSV exports.

No game, recipe, source, JSON report or recovery input may be removed. Only
explicit old presentation CSVs are deletable, after current-reference checks,
two source inventories and independent remote SHA256 readback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import consolidated_season_discovery_v1 as discovery

HOST='joe@192.168.1.133'
UUID='1f364414-880d-4f96-8619-3bd8c9954cc0'
REMOTE='/srv/hdd/pm99-archive/evidence/consolidated-audit/20261009'
RAM=Path('/run/user/1000/pm99-consolidated-audit-20261009')
OLD=ROOT/'.local/historical-authored-clubs-review-20261005-r1'
OUT=ROOT/'.local/consolidated-audit-20261009'


def cmd(args,stdin=None):
    return subprocess.run(args,input=stdin,text=True,check=True,capture_output=True).stdout


def ssh(command,stdin=None):
    return cmd(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',HOST,command],stdin)


def mount_guard():
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip()!=UUID:
        raise ValueError('Pi archive disk UUID mismatch')


def inventory(root,paths):
    result=[]
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Archive input is missing or symlinked')
        relative=path.relative_to(root).as_posix()
        result.append({'path':relative,'size':path.stat().st_size,
                       'sha256':registry.sha256_file(path)})
    return result


def transfer(root,paths,label):
    before=inventory(root,paths)
    mount_guard()
    destination=REMOTE+'/'+label
    ssh('mkdir -p '+shlex.quote(destination))
    # Explicit list, no broad directory copy and no overwrite of existing files.
    cmd(['rsync','-rlt','--ignore-existing','--files-from=-',str(root)+'/',
         HOST+':'+destination+'/'], ''.join(r['path']+'\n' for r in before))
    verifier=('import hashlib,json,sys;from pathlib import Path;'
              'root=Path(sys.argv[1]);rows=json.load(sys.stdin);'
              'actual=[dict(path=r["path"],size=(root/r["path"]).stat().st_size,'
              'sha256=hashlib.sha256((root/r["path"]).read_bytes()).hexdigest()) for r in rows];'
              'assert actual==rows,"remote hash mismatch";print(json.dumps({"verified":len(rows)}))')
    checked=json.loads(ssh('python3 -c '+shlex.quote(verifier)+' '+shlex.quote(destination),json.dumps(before)))
    mount_guard()
    if inventory(root,paths)!=before:
        raise ValueError('Local archive inputs changed during transfer')
    return {'root':str(root),'remote':destination,'files':before,'remote_verification':checked,
            'logical_bytes':sum(r['size'] for r in before),'verified':True}


def referenced_csvs(paths):
    for season in registry.supported_seasons():
        release=registry.load_preferred_release(season)
        texts=[json.dumps(release.locator)]
        texts += [path.read_text() for path in (release.package_path,release.release_manifest_path,
                  release.compiler_receipt_path,release.build_chain_path)]
        for path in paths:
            relative=registry.relative_workspace_path(path)
            if any(relative in text or str(path) in text for text in texts):
                raise ValueError('Current release references an old CSV')


def run(retire_csv=False):
    pinned=discovery.bindings()
    rows=[]
    ram_paths=[p for p in RAM.rglob('*') if p.is_file()]
    if not ram_paths:
        raise ValueError('Expected RAM evidence missing')
    rows.append(transfer(RAM,ram_paths,'detailed-rosters'))
    paths=[p for p in OLD.rglob('*.csv') if p.is_file()]
    if paths:
        referenced_csvs(paths)
        row=transfer(OLD,paths,'retired-presentation-csv')
        discovery.write_new(OUT/'csv-archive-before-removal.json',row)
        if retire_csv:
            referenced_csvs(paths)
            if discovery.bindings()!=pinned:
                raise ValueError('Current releases changed before retirement')
            assert inventory(OLD,paths)==row['files']
            for path in paths:
                # The exact independently verified CSV file, not a directory.
                if path.suffix!='.csv' or not path.is_relative_to(OLD) or path.is_symlink():
                    raise ValueError('Non-CSV removal refused')
                path.unlink()
            row['local_removed']=True
        rows.append(row)
    assert discovery.bindings()==pinned
    receipt={'utc':datetime.now(timezone.utc).isoformat(),'rows':rows,
             'current_bindings_unchanged':True,'source_session':'01a0592d-fcd5-7262-a637-743a8253d9b4',
             'scope':'RAM audit secured; old regenerable CSV presentations only. JSON/source/game inputs retained.'}
    discovery.write_new(OUT/'pi-archive-receipt.json',receipt)
    print(json.dumps({'archived_bytes':sum(r['logical_bytes'] for r in rows),
          'csv_removed_bytes':sum(r['logical_bytes'] for r in rows if r.get('local_removed'))}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--retire-old-csv',action='store_true')
    run(p.parse_args().retire_old_csv)
