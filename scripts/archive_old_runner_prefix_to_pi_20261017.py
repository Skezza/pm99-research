"""Recover runner headroom by archiving ONE exact inactive old Wine prefix.

No local staging of a GiB archive, no safety-limit override, no artifact removal,
no broad runner cleanup. Every file/link is verified on Pi and rehashed at the
source before the old owned test container/prefix can be retired.
"""
from datetime import UTC, datetime
import json
import shlex
import subprocess

from scripts import archive_rejected_rating_recovery_to_pi_20261011 as pi
from scripts import season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

HOST = 'joe@192.168.1.175'
TAG = 'registered_2010_11_stoke_lineup_20261005t214939z'
PREFIX = '/home/joe/pm99-runner/workspace/runs/' + TAG + '/wine-prefix'
ARCHIVE = '/srv/hdd/pm99-archive/runner/retired-prefixes/20261017/' + TAG + '-wine-prefix.tar.gz'
ROOT = registry.ROOT / '.local/cleanup-20261017/runner-prefix-to-pi'


def ssh(command, **kwargs):
    return subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',HOST,command],
        check=True, text=True, capture_output=True, **kwargs).stdout


INVENTORY = '''import hashlib,json,os,pathlib,stat,subprocess,sys
p=pathlib.Path(sys.argv[1]);tag=sys.argv[2]
if p.name!='wine-prefix' or p.parent.name!=tag or p.resolve()!=p or not p.is_dir():raise ValueError('unexpected exact prefix')
containers=json.loads(subprocess.check_output(['docker','inspect','pm99-agent-'+tag]))
if len(containers)!=1 or containers[0]['State']['Running']:raise ValueError('old test container active or ambiguous')
labels=containers[0]['Config']['Labels']
if labels.get('pm99.run_tag')!=tag or labels.get('pm99.worker')!='tiny-m73' or labels.get('pm99.lane')!='lane-02':raise ValueError('old container ownership differs')
rows={}
for folder,dirs,files in os.walk(p,followlinks=False):
 for name in dirs+files:
  item=pathlib.Path(folder)/name;info=item.lstat();key=item.relative_to(p.parent).as_posix()
  if item.is_symlink():rows[key]=dict(kind='symlink',target=os.readlink(item))
  elif stat.S_ISREG(info.st_mode):
   with item.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
   rows[key]=dict(kind='file',size=info.st_size,sha256=sha)
  elif not stat.S_ISDIR(info.st_mode):raise ValueError('special prefix file')
print(json.dumps(dict(members=rows,free_bytes=os.statvfs(p).f_bavail*os.statvfs(p).f_frsize,container=containers[0]['Name'],labels=labels)))
'''


def inventory():
    return json.loads(ssh('python3 -c '+shlex.quote(INVENTORY)+' '+shlex.quote(PREFIX)+' '+shlex.quote(TAG)))


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if (ROOT/'members.json').exists():
        raise ValueError('existing runner prefix archive needs inspection, never blind rerun')
    if pi.ssh('findmnt -n -o UUID --target /srv/hdd').strip()!=pi.UUID:
        raise ValueError('Pi archive volume missing or changed')
    before=inventory()
    retained(ROOT/'members.json',dict(utc=datetime.now(UTC).isoformat(),source_host=HOST,
        source_prefix=PREFIX,archive_host=pi.HOST,archive_path=ARCHIVE,**before))
    catalog_sha=registry.sha256_file(registry.CATALOG_PATH)
    folder=ARCHIVE.rsplit('/',1)[0]
    destination='mkdir -p {d} && test ! -e {p} && test ! -e {p}.partial && cat > {p}.partial'.format(
        d=shlex.quote(folder),p=shlex.quote(ARCHIVE))
    command='tar --hard-dereference -czf - -C '+shlex.quote(PREFIX.rsplit('/',1)[0])+' wine-prefix'
    source=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',HOST,command],stdout=subprocess.PIPE)
    target=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',pi.HOST,destination],stdin=source.stdout)
    source.stdout.close()
    target_rc=target.wait();source_rc=source.wait()
    if target_rc or source_rc:
        raise ValueError('runner-to-Pi stream failed; original prefix retained')
    verify='''import hashlib,json,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]);expected=json.load(sys.stdin)
with tarfile.open(str(p)+'.partial','r:gz') as archive:
 members=[m for m in archive.getmembers() if not m.isdir()]
 if len(members)!=len(expected) or {m.name for m in members}!=set(expected):raise ValueError('archived member set differs')
 for m in members:
  row=expected[m.name]
  if row['kind']=='symlink':
   if not m.issym() or m.linkname!=row['target']:raise ValueError('archived link differs')
  else:
   if not m.isfile() or m.size!=row['size']:raise ValueError('archived file type/size differs')
   if hashlib.file_digest(archive.extractfile(m),'sha256').hexdigest()!=row['sha256']:raise ValueError('archived file SHA differs')
if p.exists():raise ValueError('archive destination already exists')
pathlib.Path(str(p)+'.partial').rename(p)
with p.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
print(json.dumps(dict(archive_sha256=sha,members_verified=len(expected),member_hashes_and_links_verified=True)))
'''
    verified=json.loads(pi.ssh('python3 -c '+shlex.quote(verify)+' '+shlex.quote(ARCHIVE),input=json.dumps(before['members'])))
    retained(ROOT/'pi-member-verification.json',dict(verified,volume_uuid=pi.UUID,archive_path=ARCHIVE))
    after=inventory()
    if before['members']!=after['members'] or before['labels']!=after['labels']:
        raise ValueError('old prefix/container changed during backup; retain source')
    if registry.sha256_file(registry.CATALOG_PATH)!=catalog_sha:
        raise ValueError('preferred catalogue changed during archive; retain source')
    if pi.ssh('findmnt -n -o UUID --target /srv/hdd').strip()!=pi.UUID:
        raise ValueError('Pi volume changed before source retirement')
    # The old worker/lane must have no lease before the canonical launcher is
    # allowed to remove its exact exited container. Never clear another lease.
    lease_root='/home/joe/pm99-runner/shared/workers/tiny-m73'
    check="test -z \"$(find "+shlex.quote(lease_root)+" -type f -name '*.json' -print 2>/dev/null)\""
    ssh(check)
    launcher='/home/joe/pm99-runner/workspace/repo/scripts/pm99_runner/remote_runner_entrypoint.sh'
    args=[launcher,'cleanup','--run-tag',TAG,'--worker','tiny-m73','--lane','lane-02',
        '--launcher','run_stoke_route_capture.sh','--owner',before['labels']['pm99.owner'],
        '--container-name','pm99-agent-'+TAG,'--artifacts-dir','/home/joe/pm99-runner/artifacts/'+TAG,
        '--lease-root',lease_root]
    ssh(shlex.join(args))
    remove='''import json,pathlib,shutil,subprocess,sys
p=pathlib.Path(sys.argv[1]);tag=sys.argv[2]
if str(p)!='/home/joe/pm99-runner/workspace/runs/'+tag+'/wine-prefix' or p.resolve()!=p or p.is_symlink():raise ValueError('retirement exact path differs')
result=subprocess.run(['docker','inspect','pm99-agent-'+tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if result.returncode==0:raise ValueError('old test container still exists')
for proc in pathlib.Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  cwd=(proc/'cwd').resolve()
  if cwd==p or p in cwd.parents:raise ValueError('prefix became an active working directory')
 except (FileNotFoundError,PermissionError):pass
shutil.rmtree(p)
print(json.dumps(dict(removed_prefix=str(p),archive_required_for_restoration=True)))
'''
    removed=json.loads(ssh('python3 -c '+shlex.quote(remove)+' '+shlex.quote(PREFIX)+' '+shlex.quote(TAG)))
    retained(ROOT/'completed.json',dict(utc=datetime.now(UTC).isoformat(),source_host=HOST,
        archive_host=pi.HOST,archive_path=ARCHIVE,verification=verified,**removed,
        old_exited_container_removed_by_canonical_launcher=True,all_artifacts_and_other_run_directories_retained=True,
        current26_and_original2015_untouched=True,preferred_catalog_sha256=catalog_sha,
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))
    print(dict(old_runner_prefix_archived_and_removed=True,all_artifacts_retained=True),flush=True)


if __name__=='__main__':main()
