"""Offload one unused, regenerable browser cache; preserve current browsers."""
import hashlib
import json
import shlex
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.archive_rejected_rating_recovery_to_pi_20261011 import ssh, HOST, UUID
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

SOURCE = Path('/home/joe/.cache/ms-playwright/chromium_headless_shell-1228')
CURRENT = Path('/home/joe/.cache/ms-playwright/chromium_headless_shell-1234')
REMOTE = '/srv/hdd/pm99-archive/regenerable-tool-caches/20261016/chromium_headless_shell-1228'
ROOT = registry.ROOT / '.local/cleanup-20261016/old-playwright-cache'
SCOPE = 'Only regenerable headless-shell1228 cache; no games, source datasets, recipes or personal files.'


def guard():
    if (SOURCE.is_symlink() or SOURCE.resolve() != SOURCE or not SOURCE.is_dir()
            or not CURRENT.is_dir()):
        raise ValueError('exact old browser and retained current version required')
    commands = subprocess.check_output(['ps', '-eo', 'args'], text=True).splitlines()
    if any(str(SOURCE) in command for command in commands):
        raise ValueError('old browser appears active; do not retire its cache')
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip() != UUID:
        raise ValueError('Pi archive volume is absent or incorrect')


def main():
    receipt = ROOT / 'completed-transfer.json'
    if receipt.exists():
        if SOURCE.exists():
            raise ValueError('browser cache was recreated after its recorded retirement')
        print(pipeline.read_json_file(receipt), flush=True)
        return
    guard()
    catalog_sha = registry.sha256_file(registry.CATALOG_PATH)
    inventory = pipeline.build_tree_inventory(SOURCE)
    ROOT.mkdir(parents=True, exist_ok=True)
    retained(ROOT / 'source-inventory.json', inventory)
    remote_parent = REMOTE.rsplit('/', 1)[0]
    ssh('mkdir -p ' + shlex.quote(remote_parent))
    subprocess.run(['rsync', '-a', '--checksum', '--ignore-existing', str(SOURCE) + '/',
        HOST + ':' + REMOTE + '/'], check=True)
    code = '''import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);expected=json.load(sys.stdin)
actual=sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
if actual!=sorted(r['path'] for r in expected['files']):raise ValueError('remote cache member set differs')
for row in expected['files']:
 p=root/row['path']
 if p.is_symlink() or p.stat().st_size!=row['size']:raise ValueError('remote cache type/size differs')
 with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 if digest!=row['sha256']:raise ValueError('remote cache bytes differ')
print(json.dumps({'verified_files':len(actual),'all_SHA256_exact':True}))
'''
    verified = json.loads(ssh('python3 -c ' + shlex.quote(code) + ' ' + shlex.quote(REMOTE),
        input=json.dumps(inventory)))
    if verified != dict(verified_files=len(inventory['files']), all_SHA256_exact=True):
        raise ValueError('Pi browser-cache verification incomplete')
    pipeline.assert_tree_matches_inventory(SOURCE, inventory)
    guard()
    if registry.sha256_file(registry.CATALOG_PATH) != catalog_sha:
        raise ValueError('preferred games changed during cache archival')
    proof = dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', source=str(SOURCE),
        remote_host=HOST, remote_path=REMOTE, mounted_volume_uuid=UUID,
        inventory_path=registry.relative_workspace_path(ROOT / 'source-inventory.json'),
        inventory_sha256=registry.sha256_file(ROOT / 'source-inventory.json'),
        bytes_retired=sum(r['size'] for r in inventory['files']), remote_verification=verified,
        current_browser_retained=str(CURRENT), pm99_catalog_sha256=catalog_sha,
        recovery='Restore this directory with rsync from the recorded Pi path, or reinstall the matching Playwright browser revision.',
        scope=SCOPE)
    retained(ROOT / 'verified-before-removal.json', proof)
    subprocess.run(['rsync', '-a', str(ROOT) + '/', HOST + ':' + remote_parent + '/receipts/'], check=True)
    # Exact, literal and repeatedly checked leaf; never a cache/workspace root.
    shutil.rmtree(SOURCE)
    retained(receipt, proof)
    subprocess.run(['rsync', '-a', str(receipt), HOST + ':' + remote_parent + '/receipts/'], check=True)
    print(dict(bytes_retired=proof['bytes_retired'], cache_recoverable_from_Pi=True,
        free_bytes=shutil.disk_usage(registry.ROOT).free, all_current_games_untouched=True), flush=True)


if __name__ == '__main__':
    main()
