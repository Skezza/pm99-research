"""Archive recovery metadata for two exact, unused private kit SOURCE games.

The retained actual games supply the identical game bytes on restoration.
Never removes a preferred game, actual source parent, raw source or screenshot.
"""
import json
import shlex
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import archive_completed_arsenal_replays_20261016 as prior
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/cleanup-20261016/completed-italian-kit-replays'
REMOTE = '/srv/hdd/pm99-archive/packages/completed-source-replays/20261016/italian-kits'
REPLAY = 'replayed-italian-period-kits-20261010-r66d'
ACTUAL = 'sourced-italian-period-kits-20261010-r66c'
SEASONS = ('2005-06', '2006-07')


def safe_workspace(replay, season):
    path = registry.ROOT / '.local/season-visual-replays-v1' / season / REPLAY
    if path.resolve() != path or path.is_symlink() or replay.game_path != path / 'game':
        raise ValueError('unexpected private workspace target')
    if any(p.is_symlink() for p in path.rglob('*')) or prior.active(path):
        raise ValueError('symlink or active private workspace')
    return path


def main():
    if (ROOT / 'completed.json').exists():
        raise ValueError('completed archival must not repeat')
    if prior.ssh('findmnt -n -o UUID --target /srv/hdd').strip() != prior.UUID:
        raise ValueError('wrong or absent Pi archive volume')
    prior.ssh('mkdir -p ' + shlex.quote(REMOTE))
    ROOT.mkdir(parents=True, exist_ok=True)
    catalog = registry.sha256_file(registry.CATALOG_PATH)
    free = shutil.disk_usage(registry.ROOT).free
    rows = []
    for season in SEASONS:
        ledger = ROOT / (season + '.json')
        if ledger.exists():
            proof = pipeline.read_json_file(ledger)
            if (registry.ROOT / proof['removed_private_workspace']).exists() or registry.locator_path(season, REPLAY).exists():
                raise ValueError('inspect partially retired private replay')
            rows.append(dict(path=registry.relative_workspace_path(ledger), sha256=registry.sha256_file(ledger)))
            continue
        if registry.load_preferred_release(season).release_id in (REPLAY, ACTUAL):
            raise ValueError('target or recovery parent is current preferred; inspect first')
        base = registry.load_registered_release(season, ACTUAL)
        replay = registry.load_registered_release(season, REPLAY)
        workspace = safe_workspace(replay, season)
        locator = registry.locator_path(season, REPLAY)
        prior.no_dependants(REPLAY, locator)
        inventory = prior.assert_equal_games(base, replay)
        members = [(p, 'workspace/' + p.relative_to(workspace).as_posix())
                   for p in workspace.rglob('*') if p.is_file() and not p.is_relative_to(workspace / 'game')]
        members += [(p, 'registration/' + p.relative_to(locator.parent).as_posix())
                    for p in locator.parent.rglob('*') if p.is_file()]
        if any(p.is_symlink() for p, _ in members):
            raise ValueError('symlink recovery metadata')
        expected = {name: registry.sha256_file(path) for path, name in members}
        if len(expected) != len(members):
            raise ValueError('duplicate recovery names')
        destination = REMOTE + '/' + season + '-' + REPLAY + '.tar.gz'
        command = 'test ! -e {p} && test ! -e {p}.partial && cat > {p}.partial'.format(p=shlex.quote(destination))
        process = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', prior.HOST, command], stdin=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=process.stdin, mode='w|gz', dereference=True) as archive:
                for path, name in members:
                    archive.add(path, arcname=name, recursive=False)
            process.stdin.close()
            if process.wait() != 0:
                raise ValueError('metadata archive transport failed')
        finally:
            if process.poll() is None:
                process.terminate(); process.wait()
        code = '''import hashlib,json,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]); expected=json.load(sys.stdin)
with tarfile.open(str(p)+'.partial','r:gz') as archive:
 members=archive.getmembers()
 if len(members)!=len(expected) or {m.name for m in members}!=set(expected):raise ValueError('archive member set differs')
 for m in members:
  if not m.isfile() or hashlib.file_digest(archive.extractfile(m),'sha256').hexdigest()!=expected[m.name]:raise ValueError('archive member bytes differ')
if p.exists():raise ValueError('remote completed destination exists')
pathlib.Path(str(p)+'.partial').rename(p)
with p.open('rb') as f:print(hashlib.file_digest(f,'sha256').hexdigest())
'''
        digest = prior.ssh('python3 -c ' + shlex.quote(code) + ' ' + shlex.quote(destination), input=json.dumps(expected)).strip()
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('invalid remote SHA receipt')
        if registry.sha256_file(registry.CATALOG_PATH) != catalog or prior.ssh('findmnt -n -o UUID --target /srv/hdd').strip() != prior.UUID:
            raise ValueError('preferred catalog or Pi volume changed')
        safe_workspace(replay, season)
        prior.no_dependants(REPLAY, locator)
        prior.assert_equal_games(base, replay)
        if any(registry.sha256_file(p) != expected[n] for p, n in members):
            raise ValueError('local metadata changed')
        proof = dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
            source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', season=season,
            retired_private_replay=REPLAY, retained_exact_actual_release=ACTUAL,
            retained_actual_game=registry.relative_workspace_path(base.game_path),
            retained_actual_inventory=registry.relative_workspace_path(base.inventory_path),
            retained_actual_inventory_sha256=registry.sha256_file(base.inventory_path),
            exact_game_inventory=inventory, member_sha256=expected,
            removed_private_workspace=registry.relative_workspace_path(workspace),
            removed_private_registration=registry.relative_workspace_path(locator.parent),
            remote_host=prior.HOST, remote_archive=destination, remote_archive_sha256=digest,
            mounted_volume_uuid=prior.UUID, catalog_sha256=catalog,
            recovery='Restore workspace/ and registration/ metadata to recorded paths. Restore game from retained_exact_actual_release and verify exact_game_inventory; game bytes are not separately copied to Pi.')
        retained(ledger, proof)
        subprocess.run(['rsync', '-a', str(ledger), prior.HOST + ':' + REMOTE + '/'], check=True)
        shutil.rmtree(workspace)
        shutil.rmtree(locator.parent)
        rows.append(dict(path=registry.relative_workspace_path(ledger), sha256=registry.sha256_file(ledger)))
        print(dict(season=season, exact_private_replay_retired=True, retained_actual_game=ACTUAL), flush=True)
    retained(ROOT / 'completed.json', dict(utc=datetime.now(UTC).isoformat(), rows=rows,
        preferred_catalog_sha256=catalog, before_free_bytes=free,
        after_free_bytes=shutil.disk_usage(registry.ROOT).free, current26_unchanged=True))
    subprocess.run(['rsync', '-a', str(ROOT / 'completed.json'), prior.HOST + ':' + REMOTE + '/'], check=True)


if __name__ == '__main__':
    main()
