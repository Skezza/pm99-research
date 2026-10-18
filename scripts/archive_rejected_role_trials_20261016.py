"""Retire only the nine private r103 trial buffers, with Pi/base recovery."""
import hashlib
import json
import shlex
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.archive_rejected_rating_recovery_to_pi_20261011 import ssh, HOST, UUID
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/cleanup-20261016/rejected-role-trials'
BASELINES = registry.ROOT / '.local/consolidated-audit-20261009/exact-fifa-roles-20261015/baseline.json'
REMOTE = '/srv/hdd/pm99-archive/packages/rejected-role-trials/20261016'
RELEASES = ('sourced-exact-fifa-roles-20261015-r103a', 'replayed-exact-fifa-roles-20261015-r103b')
DELTA = 'DBDAT/JUG98030.FDI'
REASON = 'Private/unpromoted r103 fine-role trial rejected for erasing an existing right-only centre-back side; corrected r104/r105 preferred releases remain local.'


def active(workspace):
    return any(str(workspace) in line for line in subprocess.check_output(['ps', '-eo', 'args'], text=True).splitlines())


def run(*, baselines=None, skip_seasons=()):
    if (ROOT / 'completed.json').exists():
        raise ValueError('completed retirement must not repeat')
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip() != UUID:
        raise ValueError('Pi archive volume is absent or incorrect')
    ROOT.mkdir(parents=True, exist_ok=True)
    ssh('mkdir -p ' + shlex.quote(REMOTE))
    catalog_sha = registry.sha256_file(registry.CATALOG_PATH)
    preferred = {s: registry.load_preferred_release(s).release_id for s in registry.supported_seasons()}
    if any(r in RELEASES for r in preferred.values()):
        raise ValueError('a rejected trial is preferred; no retirement')
    rows, checked = [], {}
    for baseline in pipeline.read_json_file(BASELINES) if baselines is None else baselines:
        if baseline['season'] in skip_seasons:
            continue
        base = registry.load_registered_release(baseline['season'], baseline['release_id'])
        for rid in RELEASES:
            workspace = registry.ROOT / '.local/historical-role-deltas-v1' / baseline['season'] / rid
            if not workspace.exists():
                continue
            if workspace.is_symlink() or workspace.resolve() != workspace or active(workspace):
                raise ValueError('rejected role workspace is unsafe or active')
            receipt = ROOT / (baseline['season'] + '-' + rid[-5:] + '.json')
            if receipt.exists():
                raise ValueError('partially completed retirement requires receipt inspection')
            original = pipeline.read_json_file(base.inventory_path)
            trial_names = {p.relative_to(workspace / 'game').as_posix()
                for p in (workspace / 'game').rglob('*') if p.is_file()}
            if trial_names != {r['path'] for r in original['files']}:
                raise ValueError('rejected trial contains additional or missing game files')
            for item in original['files']:
                if item['path'] == DELTA:
                    continue
                path = workspace / 'game' / item['path']
                if path.is_symlink():
                    raise ValueError('symlink in private trial game')
                st = path.stat(); key = st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns
                if key not in checked:
                    checked[key] = registry.sha256_file(path)
                if checked[key] != item['sha256']:
                    raise ValueError('rejected role trial has unique non-role game changes')
            files = [p for p in workspace.rglob('*') if p.is_file() and not p.is_relative_to(workspace / 'game')]
            files.append(workspace / 'game' / DELTA)
            items = [(p, p.relative_to(workspace).as_posix()) for p in files]
            locator = registry.locator_path(baseline['season'], rid)
            if locator.exists():
                items.append((locator, 'registered-locator.json'))
            if any(p.is_symlink() for p, _ in items):
                raise ValueError('symlink in rejected role recovery inputs')
            expected = {name: registry.sha256_file(path) for path, name in items}
            destination = REMOTE + '/' + baseline['season'] + '-' + rid[-5:] + '.tar.gz'
            command = 'test ! -e {p} && test ! -e {p}.partial && cat > {p}.partial'.format(p=shlex.quote(destination))
            process = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', HOST, command], stdin=subprocess.PIPE)
            try:
                with tarfile.open(fileobj=process.stdin, mode='w|gz', dereference=True) as archive:
                    for path, name in items:
                        archive.add(path, arcname=name, recursive=False)
                process.stdin.close()
                if process.wait() != 0:
                    raise ValueError('Pi role-trial archive transport failed')
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait()
            code = '''import hashlib,json,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]);expected=json.load(sys.stdin)
with tarfile.open(str(p)+'.partial','r:gz') as archive:
 members=archive.getmembers()
 if len(members)!=len(expected) or {m.name for m in members}!=set(expected):raise ValueError('Pi recovery member set differs')
 for member in members:
  if not member.isfile():raise ValueError('unexpected archive member type')
  if hashlib.file_digest(archive.extractfile(member),'sha256').hexdigest()!=expected[member.name]:raise ValueError('Pi recovery member SHA differs')
if p.exists():raise ValueError('Pi recovery destination already exists')
pathlib.Path(str(p)+'.partial').rename(p)
with p.open('rb') as f:print(hashlib.file_digest(f,'sha256').hexdigest())
'''
            remote_sha = ssh('python3 -c ' + shlex.quote(code) + ' ' + shlex.quote(destination), input=json.dumps(expected)).strip()
            if len(remote_sha) != 64:
                raise ValueError('missing Pi recovery archive SHA')
            if (active(workspace) or registry.sha256_file(registry.CATALOG_PATH) != catalog_sha
                    or ssh('findmnt -n -o UUID --target /srv/hdd').strip() != UUID):
                raise ValueError('state changed before retirement')
            if any(registry.sha256_file(path) != expected[name] for path, name in items):
                raise ValueError('local rejected inputs changed during archival')
            proof = dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
                source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', season=baseline['season'],
                rejected_release=rid, baseline_release=base.release_id,
                baseline_inventory_path=registry.relative_workspace_path(base.inventory_path),
                baseline_inventory_sha256=registry.sha256_file(base.inventory_path),
                retired_workspace=registry.relative_workspace_path(workspace),
                remote_host=HOST, remote_archive=destination, remote_archive_sha256=remote_sha,
                member_sha256=expected, mounted_volume_uuid=UUID, catalog_sha256=catalog_sha,
                recovery='Restore metadata and '+DELTA+' from the Pi archive. Recreate all other game files from the recorded unchanged baseline inventory. Restore registered-locator.json only when restoring the rejected private release.',
                reason=REASON)
            retained(receipt, proof)
            subprocess.run(['rsync', '-a', str(receipt), HOST + ':' + REMOTE + '/'], check=True)
            if locator.exists():
                locator.unlink()
            shutil.rmtree(workspace)
            rows.append(dict(receipt=registry.relative_workspace_path(receipt), sha256=registry.sha256_file(receipt)))
            print(dict(retired=rid, season=baseline['season'], recoverable=True), flush=True)
    retained(ROOT / 'completed.json', dict(rows=rows, current26_unchanged=True,
        catalog_sha256=catalog_sha, free_bytes=shutil.disk_usage(registry.ROOT).free))
    subprocess.run(['rsync', '-a', str(ROOT / 'completed.json'), HOST + ':' + REMOTE + '/'], check=True)


if __name__ == '__main__':
    run()
