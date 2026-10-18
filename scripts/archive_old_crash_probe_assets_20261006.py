#!/usr/bin/env python3
"""Archive only SFX/SIMULDAT assets from allowlisted obsolete unregistered probes.

Keep DBDAT, executables and metadata local. All-file remote SHA256, an empty
checksum rsync and a fresh local inventory gate each removal. Read-only default.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import archive_retired_season_tests_20261004 as archive
from scripts import season_release_registry_v1 as registry

PROBES = ROOT / '.local/probes'
NAMES = tuple(f'2004-05-stoke-xi{i:02d}' for i in range(1, 12)) + (
    '2004-05-stoke-only', '2004-05-english-only',
)
ASSETS = ('SFX', 'SIMULDAT')
NESTED_GAMES = frozenset(('2004-05-stoke-only', '2004-05-english-only'))
RECEIPTS = ROOT / '.local/duplicate-ownership-v3/space-recovery/old-crash-probe-assets'
REMOTE = '/srv/hdd/pm99-archive/packages/old-crash-probe-assets/20261006'
REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/old-crash-probe-assets-20261006'


def guard_probe(name):
    source = PROBES / name
    if name not in NAMES or source.is_symlink() or source.resolve().parent != PROBES.resolve():
        raise ValueError('not an exact old crash-probe installation')
    game_source = source / 'ingress/game' if name in NESTED_GAMES else source
    if name in NESTED_GAMES and (
            (source / 'ingress').is_symlink() or game_source.is_symlink()
            or not game_source.is_dir()
            or game_source.resolve() != source.resolve() / 'ingress/game'):
        raise ValueError('nested probe game must be an exact non-symlink directory')
    if archive._active_game(source) or (game_source != source and archive._active_game(game_source)):
        raise ValueError('old probe is currently running')
    for path in (registry.LOCAL_ROOT / 'releases').glob('*/*/locator.json'):
        value = json.loads(path.read_text()).get('game_path')
        if value:
            game = (ROOT / value).resolve()
            if game == source.resolve() or game.is_relative_to(source.resolve()):
                raise ValueError('registered historical game must not lose its assets')
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        if release.game_path.resolve().is_relative_to(source.resolve()):
            raise ValueError('probe contains a current game')
        for path in (release.package_path, release.release_manifest_path,
                     release.compiler_receipt_path, release.build_chain_path):
            text = path.read_text()
            if any(str((game_source / asset).relative_to(ROOT)) in text for asset in ASSETS):
                raise ValueError('current recipe or build chain directly depends on old probe assets')
    return game_source


def run(delete=False):
    rows = []
    for name in NAMES:
        source = guard_probe(name)
        archive.WORKSPACE = source
        archive.RECEIPTS = RECEIPTS / name
        archive.REMOTE = REMOTE + '/' + name
        archive.REMOTE_RECEIPTS = REMOTE_RECEIPTS + '/' + name
        archive.TARGETS = ASSETS
        for asset in ASSETS:
            if delete and name != NAMES[0] and (source / asset).is_dir():
                first_receipt = RECEIPTS / NAMES[0] / asset / 'receipt.json'
                first = json.loads(first_receipt.read_text())
                if not first.get('archive_verified') or not first.get('local_removed'):
                    raise ValueError('verified immutable common-asset archive is missing')
                if archive.remote('findmnt -n -o UUID --target /srv/hdd').strip() != archive.DISK_UUID:
                    raise ValueError('Pi archive disk is not mounted')
                target = archive.REMOTE + '/' + asset
                # Remote immutable hardlinks save bandwidth and Pi space.
                # The archive helper never writes in place, and verifies every
                # target against its own local source before removing anything.
                archive.remote('mkdir -p ' + shlex.quote(archive.REMOTE) +
                    '; if test ! -e ' + shlex.quote(target) + '; then cp -al ' +
                    shlex.quote(first['remote']) + ' ' + shlex.quote(target) + '; fi')
            print(json.dumps({'probe': name, 'asset': asset, 'stage': 'verify-and-archive' if delete else 'read-only'}), flush=True)
            row = archive.archive(asset, delete)
            rows.append(dict(row, probe=name, asset=asset))
            print(json.dumps(rows[-1]), flush=True)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-and-remove', action='store_true')
    args = parser.parse_args()
    run(args.archive_and_remove)
