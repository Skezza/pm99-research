"""Retire exactly two inactive disposable Wine prefixes, not games or evidence."""
import json
import subprocess
from pathlib import Path
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

REMOTE = r'''
import json,os,shutil,subprocess,time
from pathlib import Path
root=Path('/home/joe/pm99-runner/namespaces/pm99-research-main/workspace/runs')
tags=['venezia_r62a_actual_xi_20261010','venezia_r62a_actual_xi_r2_20261010']
if subprocess.check_output(['docker','ps','-q'],text=True).strip():
    raise ValueError('live containers; refuse prefix cleanup')
mounts=subprocess.check_output(['findmnt','-rn','-o','TARGET'],text=True).splitlines()
targets=[root/tag/'wine-prefix' for tag in tags]
for path in targets:
    if not path.is_dir() or path.is_symlink() or path.resolve()!=path:
        raise ValueError('exact disposable prefix missing or symlinked')
    if time.time()-path.stat().st_mtime<86400:raise ValueError('prefix too recent')
    if any(Path(m)==path or path in Path(m).parents for m in mounts):
        raise ValueError('prefix has active mount')
    users=subprocess.run(['fuser','-m',str(path)],capture_output=True,text=True)
    # -m checks the whole filesystem; use exact open-path process scan instead.
    for fd in Path('/proc').glob('[0-9]*/fd/*'):
        try: opened=Path(os.readlink(fd))
        except (FileNotFoundError,PermissionError,OSError):continue
        if opened==path or path in opened.parents:raise ValueError('prefix open by process')
before=shutil.disk_usage(root).free
for path in targets:shutil.rmtree(path)
print(json.dumps(dict(removed=[str(p) for p in targets],before_free_bytes=before,
    after_free_bytes=shutil.disk_usage(root).free,games_and_screenshots_preserved=True,
    recreation='Runner recreates Wine prefixes from its standard baseline.')))
'''


if __name__=='__main__':
    output=Path('.local/cleanup-20261017/two-remote-wine-prefixes.json')
    if output.exists():raise ValueError('completed cleanup must not repeat')
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',
        'joe@192.168.1.175','python3','-'],input=REMOTE,text=True,capture_output=True,check=True)
    receipt=json.loads(result.stdout);retained(output,receipt);print(receipt,flush=True)
