"""Archive one idle, downloadable browser build; never touch user profiles."""
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile

from scripts import season_release_registry_v1 as registry
from scripts.archive_rejected_rating_recovery_to_pi_20261011 import HOST, UUID, ssh
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

TARGET = Path('/home/joe/.cache/ms-playwright/chromium_headless_shell-1234')
ROOT = registry.ROOT / '.local/cleanup-20261017/idle-playwright-browser-to-pi'
REMOTE = '/srv/hdd/pm99-archive/tools/playwright/20261017/chromium_headless_shell-1234.tar.gz'


def idle():
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if (process / 'exe').resolve().is_relative_to(TARGET):
                raise ValueError('browser build is running')
            for fd in (process / 'fd').iterdir():
                if fd.resolve().is_relative_to(TARGET):
                    raise ValueError('browser build has an open file')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue


def manifest():
    if TARGET.resolve() != TARGET or TARGET.is_symlink() or not TARGET.is_dir():
        raise ValueError('exact browser build must be an ordinary directory')
    rows = {}
    for path in sorted(TARGET.rglob('*')):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('unexpected browser-cache member')
        if path.is_file():
            rows[path.relative_to(TARGET.parent).as_posix()] = dict(
                size=path.stat().st_size, sha256=registry.sha256_file(path))
    if not rows:
        raise ValueError('browser package has no files')
    return rows


def main():
    if ROOT.exists():
        raise ValueError('inspect existing archive attempt; never overwrite')
    idle()
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip() != UUID:
        raise ValueError('Pi volume unavailable or changed')
    members = manifest()
    catalog = registry.sha256_file(registry.CATALOG_PATH)
    before = shutil.disk_usage(registry.ROOT).free
    ROOT.mkdir(parents=True)
    retained(ROOT / 'members.json', dict(utc=datetime.now(UTC).isoformat(),
        source=str(TARGET), destination_host=HOST, remote_archive=REMOTE, members=members,
        scope='Downloadable Playwright browser executable/resources only; no user profiles or PM99 data.'))
    folder = REMOTE.rsplit('/', 1)[0]
    command = 'mkdir -p {d} && test ! -e {p} && test ! -e {p}.partial && cat > {p}.partial'.format(
        d=shlex.quote(folder), p=shlex.quote(REMOTE))
    child = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', HOST, command], stdin=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=child.stdin, mode='w|gz', compresslevel=1) as archive:
            for name in members:
                archive.add(TARGET.parent / name, arcname=name, recursive=False)
        child.stdin.close()
        if child.wait() != 0:
            raise ValueError('Pi upload failed; local browser retained')
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait()
    verify = '''import hashlib,json,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]);expected=json.load(sys.stdin)
with tarfile.open(str(p)+'.partial','r:gz') as archive:
 items=archive.getmembers()
 if len(items)!=len(expected) or {i.name for i in items}!=set(expected):raise ValueError('member set differs')
 for item in items:
  row=expected[item.name]
  if not item.isfile() or item.size!=row['size'] or hashlib.file_digest(archive.extractfile(item),'sha256').hexdigest()!=row['sha256']:raise ValueError('archived bytes differ')
if p.exists():raise ValueError('archive already exists')
pathlib.Path(str(p)+'.partial').rename(p)
with p.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
print(json.dumps(dict(archive_sha256=sha,verified_files=len(expected))))
'''
    verified = json.loads(ssh('python3 -c ' + shlex.quote(verify) + ' ' + shlex.quote(REMOTE), input=json.dumps(members)))
    retained(ROOT / 'pi-verification.json', dict(verified, volume_uuid=UUID))
    if manifest() != members or registry.sha256_file(registry.CATALOG_PATH) != catalog:
        raise ValueError('local files or preferred releases changed; retain local browser')
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip() != UUID:
        raise ValueError('Pi volume changed; retain local browser')
    idle()
    shutil.rmtree(TARGET)
    retained(ROOT / 'completed.json', dict(utc=datetime.now(UTC).isoformat(),
        machine='joe-Vostro-3350', source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        removed_path=str(TARGET), remote_archive=REMOTE, **verified,
        before_free_bytes=before, after_free_bytes=shutil.disk_usage(registry.ROOT).free,
        current_games_sources_original2015_unchanged=True,
        recovery='Extract the recorded directory beneath /home/joe/.cache/ms-playwright, or reinstall the matching Playwright Chromium headless-shell package.'))
    print(dict(archived_idle_browser=True, verified_files=len(members),
        recovered_free_bytes=shutil.disk_usage(registry.ROOT).free-before), flush=True)


if __name__ == '__main__':
    main()
