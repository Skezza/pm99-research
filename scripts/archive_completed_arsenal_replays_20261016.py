"""Retire three verified private SOURCE copies; retain exact baseline recovery.

No preferred game, source correction plan, screenshot or original2015 backup
is a target. Every archived replay game must equal its retained actual game.
Private replay metadata is member-SHA verified on the Pi before local removal.
"""
import hashlib
import json
import shlex
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.archive_rejected_rating_recovery_to_pi_20261011 import ssh, HOST, UUID
from scripts.archive_rejected_role_trials_20261016 import active
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/cleanup-20261016/completed-arsenal-source-replays'
REMOTE = '/srv/hdd/pm99-archive/packages/completed-source-replays/20261016'
TARGETS = (
    ('replayed-arsenal-owned-opening-20261016-r111b', 'sourced-arsenal-owned-opening-20261016-r111a', '.local/historical-role-deltas-v1'),
    ('replayed-arsenal-shirt-numbers-20261016-r112b', 'sourced-arsenal-shirt-numbers-20261016-r112a', '.local/historical-role-deltas-v1'),
    ('replayed-genoa-period-kit-20261016-r113b', 'sourced-genoa-period-kit-20261016-r113a', '.local/season-visual-replays-v1'),
)


def assert_equal_games(base, replay):
    original = pipeline.read_json_file(base.inventory_path)
    expected = pipeline.read_json_file(replay.inventory_path)
    if expected != original:
        raise ValueError('completed replay inventory differs from retained actual game')
    pipeline.assert_tree_matches_inventory(base.game_path, original)
    pipeline.assert_tree_matches_inventory(replay.game_path, expected)
    if base.package_path.read_bytes() != replay.package_path.read_bytes():
        raise ValueError('completed replay recipe differs from retained actual game')
    return original


def no_dependants(replay_id, own_locator):
    for path in registry.CATALOG_PATH.parent.rglob('locator.json'):
        if path == own_locator:
            continue
        doc = pipeline.read_json_file(path)
        if replay_id in json.dumps(doc, sort_keys=True):
            raise ValueError('another registered release depends on this private replay: ' + str(path))


def main():
    if (ROOT / 'completed.json').exists():
        raise ValueError('completed SOURCE retirement must not repeat')
    if ssh('findmnt -n -o UUID --target /srv/hdd').strip() != UUID:
        raise ValueError('Pi volume absent or changed')
    ROOT.mkdir(parents=True, exist_ok=True)
    ssh('mkdir -p ' + shlex.quote(REMOTE))
    catalog_sha = registry.sha256_file(registry.CATALOG_PATH)
    before_free = shutil.disk_usage(registry.ROOT).free
    rows = []
    for rid, baseline, prefix in TARGETS:
        ledger = ROOT / (rid + '.json')
        if ledger.exists():
            proof = pipeline.read_json_file(ledger)
            workspace = registry.ROOT / proof['removed_private_workspace']
            if workspace.exists() or registry.locator_path('2021-22', rid).parent.exists():
                raise ValueError('partially retired SOURCE replay; inspect recorded archive')
            rows.append(dict(path=registry.relative_workspace_path(ledger), sha256=registry.sha256_file(ledger)))
            continue
        if any(registry.load_preferred_release(s).release_id == rid for s in registry.supported_seasons()):
            raise ValueError('a SOURCE replay became preferred')
        base = registry.load_registered_release('2021-22', baseline)
        replay = registry.load_registered_release('2021-22', rid)
        workspace = registry.ROOT / prefix / '2021-22' / rid
        locator = registry.locator_path('2021-22', rid)
        if (workspace.resolve() != workspace or workspace.is_symlink()
                or replay.game_path != workspace / 'game' or active(workspace)):
            raise ValueError('unsafe or active private replay workspace')
        no_dependants(rid, locator)
        inventory = assert_equal_games(base, replay)
        members = [(p, 'workspace/' + p.relative_to(workspace).as_posix())
                   for p in workspace.rglob('*') if p.is_file() and not p.is_relative_to(workspace / 'game')]
        members += [(p, 'registration/' + p.relative_to(locator.parent).as_posix())
                    for p in locator.parent.rglob('*') if p.is_file()]
        if any(p.is_symlink() for p in workspace.rglob('*')) or any(p.is_symlink() for p, _ in members):
            raise ValueError('symlink in replay recovery scope')
        expected = {name: registry.sha256_file(path) for path, name in members}
        if len(expected) != len(members):
            raise ValueError('duplicate recovery member names')
        destination = REMOTE + '/' + rid + '.tar.gz'
        command = 'test ! -e {p} && test ! -e {p}.partial && cat > {p}.partial'.format(p=shlex.quote(destination))
        process = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', HOST, command], stdin=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=process.stdin, mode='w|gz', dereference=True) as archive:
                for path, name in members:
                    archive.add(path, arcname=name, recursive=False)
            process.stdin.close()
            if process.wait() != 0:
                raise ValueError('SOURCE recovery archive transport failed')
        finally:
            if process.poll() is None:
                process.terminate(); process.wait()
        code = '''import hashlib,json,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]); expected=json.load(sys.stdin)
with tarfile.open(str(p)+'.partial','r:gz') as archive:
 members=archive.getmembers()
 if len(members)!=len(expected) or {m.name for m in members}!=set(expected):raise ValueError('recovery member set differs')
 for member in members:
  if not member.isfile():raise ValueError('unexpected recovery member type')
  if hashlib.file_digest(archive.extractfile(member),'sha256').hexdigest()!=expected[member.name]:raise ValueError('recovery member SHA differs')
if p.exists():raise ValueError('completed remote archive already exists')
pathlib.Path(str(p)+'.partial').rename(p)
with p.open('rb') as f:print(hashlib.file_digest(f,'sha256').hexdigest())
'''
        digest = ssh('python3 -c ' + shlex.quote(code) + ' ' + shlex.quote(destination), input=json.dumps(expected)).strip()
        if len(digest) != 64:
            raise ValueError('missing verified remote archive digest')
        if (active(workspace) or registry.sha256_file(registry.CATALOG_PATH) != catalog_sha
                or ssh('findmnt -n -o UUID --target /srv/hdd').strip() != UUID):
            raise ValueError('state changed before private replay removal')
        no_dependants(rid, locator)
        assert_equal_games(base, replay)
        if any(registry.sha256_file(p) != expected[n] for p, n in members):
            raise ValueError('local recovery metadata changed during transfer')
        proof = dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
            source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', season='2021-22',
            retired_private_replay=rid, retained_exact_actual_release=baseline,
            retained_actual_game=registry.relative_workspace_path(base.game_path),
            retained_actual_inventory=registry.relative_workspace_path(base.inventory_path),
            retained_actual_inventory_sha256=registry.sha256_file(base.inventory_path),
            exact_game_inventory=inventory, member_sha256=expected,
            removed_private_workspace=registry.relative_workspace_path(workspace),
            removed_private_registration=registry.relative_workspace_path(locator.parent),
            remote_host=HOST, remote_archive=destination, remote_archive_sha256=digest,
            mounted_volume_uuid=UUID, catalog_sha256=catalog_sha,
            recovery='Extract workspace/ to removed_private_workspace and registration/ to removed_private_registration. Copy the recorded retained exact actual game to workspace/game and verify exact_game_inventory. These are completed duplicate SOURCE verification copies, not current games or source parents.')
        retained(ledger, proof)
        subprocess.run(['rsync', '-a', str(ledger), HOST + ':' + REMOTE + '/'], check=True)
        shutil.rmtree(workspace)
        shutil.rmtree(locator.parent)
        rows.append(dict(path=registry.relative_workspace_path(ledger), sha256=registry.sha256_file(ledger)))
        print(dict(retired_private_SOURCE=rid, exact_actual_game_retained=baseline, metadata_verified_on_Pi=True), flush=True)
    retained(ROOT / 'completed.json', dict(utc=datetime.now(UTC).isoformat(), rows=rows,
        preferred_catalog_sha256=catalog_sha, before_free_bytes=before_free,
        after_free_bytes=shutil.disk_usage(registry.ROOT).free, current26_unchanged=True))
    subprocess.run(['rsync', '-a', str(ROOT / 'completed.json'), HOST + ':' + REMOTE + '/'], check=True)


if __name__ == '__main__':
    main()
