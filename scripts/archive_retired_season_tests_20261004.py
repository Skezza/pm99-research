#!/usr/bin/env python3
"""Archive an exact list of retired test games on the verified Pi before removal.

Read-only by default. No current season, source cache or recovery base is in
the allowlist. Receipts preserve every original file hash, mode and timestamp.
"""
import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import compact_superseded_kit_experiments_v1 as compact
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import _active_game, atomic_bytes

WORKSPACE = ROOT / '.local/season-workspace-v1'
RECEIPTS = ROOT / '.local/cleanup-20261004/retired-season-tests'
HOST = 'joe@192.168.1.133'
REMOTE = '/srv/hdd/pm99-archive/packages/retired-season-tests/20261004'
REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/retired-season-tests-20261004'
DISK_UUID = '1f364414-880d-4f96-8619-3bd8c9954cc0'
TARGETS = (
    '2000-01-calle-elkin-20260909-r1-game',
    '2000-01-calle-elkin-20260909-r2-game',
    '2000-01-calle-elkin-alias-20260909-r3-game',
    '2000-01-calle-elkin-alias-roster-20260910-r1-game',
    '2000-01-calle-elkin-alias-roster-carrier1001-20260910-r3-game',
    '2000-01-calle-elkin-alias-roster-carrier1001-20260910-r4-game',
    '2000-01-calle-elkin-alias-roster-carrier10-20260910-r2-game',
    '2000-01-calle-elkin-alias-roster-carrier11-20260910-r2-game',
    '2000-01-calle-elkin-alias-roster-carrier11-20260910-r3-game',
    '2000-01-calle-elkin-alias-roster-carrier12-20260910-r4-game',
    '2000-01-calle-elkin-alias-roster-carrier12-20260910-r5-game',
    '2000-01-calle-elkin-alias-roster-carrier1251-20260910-r6-game',
    '2000-01-calle-elkin-alias-roster-carrier1252-20260910-r7-game',
    '2000-01-calle-elkin-alias-roster-carrier1256-20260910-r8-game',
    '2000-01-calle-elkin-alias-roster-carrier1260-20260911-r9-game',
    '2015-16-kit-runtime-palette-v4-game',
)


def command(args, *, stdin=None):
    return subprocess.run(args, input=stdin, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def remote(shell, *, stdin=None):
    return command(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                    HOST, shell], stdin=stdin)


def save(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def guard(source):
    if source.name not in TARGETS or source.is_symlink() or source.resolve().parent != WORKSPACE.resolve():
        raise ValueError('not an exact allowlisted test installation')
    preferred = {registry.load_preferred_release(s).game_path.resolve()
                 for s in registry.supported_seasons()}
    if source.resolve() in preferred or _active_game(source):
        raise ValueError('test installation is current or running')
    # None of these experimental trees should be a registered playable release.
    for path in (registry.LOCAL_ROOT / 'releases').glob('*/*/locator.json'):
        value = json.loads(path.read_text()).get('game_path')
        if value and (ROOT / value).resolve() == source.resolve():
            raise ValueError('registered historical release needs separate archival handling')


def seed_common_archive_files():
    """Reuse only verified immutable archive bytes, never local writable games.

    rsync uses new temporary files and rename (not --inplace) for changes, so
    source archive hardlinks remain byte-identical. Final per-file SHA checks
    and dry-run checks still gate every local deletion.
    """
    receipt = RECEIPTS / TARGETS[0] / 'receipt.json'
    row = json.loads(receipt.read_text())
    base = REMOTE + '/' + TARGETS[0]
    if not row.get('archive_verified') or not row.get('local_removed') or row['remote'] != base:
        raise ValueError('first archive is not complete and verified')
    if remote('findmnt -n -o UUID --target /srv/hdd').strip() != DISK_UUID:
        raise ValueError('Pi archive is not on the expected mounted disk')
    for name in TARGETS[1:-1]:
        destination = REMOTE + '/' + name
        remote('if test ! -e ' + shlex.quote(destination) + '; then cp -al ' +
               shlex.quote(base) + ' ' + shlex.quote(destination) + '; fi')
    print(json.dumps({'seeded_archive_candidates': len(TARGETS) - 2,
                      'scope': 'remote immutable common bytes; each target still requires verification'}))


def verify_archives():
    if remote('findmnt -n -o UUID --target /srv/hdd').strip() != DISK_UUID:
        raise ValueError('Pi archive is not on the expected mounted disk')
    checked = 0
    for name in TARGETS:
        row = json.loads((RECEIPTS / name / 'receipt.json').read_text())
        if not row.get('archive_verified') or not row.get('local_removed'):
            raise ValueError('archive has not completed: ' + name)
        if row['remote'] != REMOTE + '/' + name:
            raise ValueError('unexpected archive location')
        checks = ''.join(value['sha256'] + '  ' + key + '\n'
                         for key, value in row['files'].items())
        remote('cd ' + shlex.quote(row['remote']) +
               ' && sha256sum --check --quiet', stdin=checks)
        checked += len(row['files'])
        print(json.dumps({'name': name, 'archive_sha256_verified': True}), flush=True)
    print(json.dumps({'archives_checked': len(TARGETS), 'file_hashes_checked': checked}))


def archive(name, delete=False):
    source = WORKSPACE / name
    receipt = RECEIPTS / name / 'receipt.json'
    if not source.exists():
        if receipt.exists() and json.loads(receipt.read_text()).get('local_removed'):
            return {'name': name, 'status': 'already-archived'}
        raise ValueError('source missing without a completed archive receipt')
    guard(source)
    if not delete:
        return {'name': name, 'status': 'eligible', 'source': str(source)}
    uuid = remote('findmnt -n -o UUID --target /srv/hdd').strip()
    if uuid != DISK_UUID:
        raise ValueError('Pi archive is not on the expected mounted disk')
    files, directories = compact.inventory(source)
    allocated = sum(p.stat().st_blocks * 512 for p in source.rglob('*') if p.is_file())
    destination = REMOTE + '/' + name
    remote('mkdir -p ' + shlex.quote(destination) + ' ' + shlex.quote(REMOTE_RECEIPTS))
    row = {'schema_version': 'pm99-verified-test-archive-v1', 'source': str(source),
           'host': HOST, 'remote': destination, 'disk_uuid': uuid,
           'files': files, 'directories': directories, 'file_count': len(files),
           'logical_bytes': sum(r['size'] for r in files.values()),
           'allocated_file_bytes': allocated, 'local_removed': False}
    save(receipt, row)
    transport = 'ssh -o BatchMode=yes -o ConnectTimeout=8'
    command(['rsync', '-rltz', '--compress-level=1', '-e', transport,
             str(source) + '/', HOST + ':' + destination + '/'])
    checks = ''.join(value['sha256'] + '  ' + key + '\n' for key, value in files.items())
    proof = remote('cd ' + shlex.quote(destination) + ' && sha256sum --check --quiet', stdin=checks)
    if proof.strip():
        raise ValueError('unexpected output from remote all-file SHA256 check')
    comparison = command(['rsync', '-rcni', '--delete', '-e', transport,
                          str(source) + '/', HOST + ':' + destination + '/'])
    if comparison.strip():
        raise ValueError('checksum dry-run found differences: ' + comparison[:300])
    # Rehash the complete source just before deletion; never trust just sizes.
    if compact.inventory(source) != (files, directories):
        raise ValueError('local test installation changed during backup')
    guard(source)
    row.update(verification='remote all-file SHA256, empty checksum-rsync, fresh local inventory',
               archive_verified=True)
    save(receipt, row)
    command(['rsync', '-lt', '-e', transport, str(receipt),
             HOST + ':' + REMOTE_RECEIPTS + '/' + name + '.json'])
    remote('sync')
    # This is a literal selected child of the workspace, not a recursive root.
    shutil.rmtree(source)
    row.update(local_removed=True)
    save(receipt, row)
    command(['rsync', '-lt', '-e', transport, str(receipt),
             HOST + ':' + REMOTE_RECEIPTS + '/' + name + '.json'])
    command(['ssh', '-o', 'BatchMode=yes', HOST,
             'test "$(sha256sum ' + shlex.quote(REMOTE_RECEIPTS + '/' + name + '.json') +
             ' | cut -d " " -f1)" = ' + shlex.quote(compact.digest(receipt))])
    return {k: row[k] for k in ('source', 'remote', 'file_count', 'logical_bytes',
                                'allocated_file_bytes', 'local_removed')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-and-remove', action='store_true')
    parser.add_argument('--seed-common-files', action='store_true')
    parser.add_argument('--verify-archives', action='store_true')
    parser.add_argument('--name', choices=TARGETS)
    args = parser.parse_args()
    if args.verify_archives:
        verify_archives()
        return
    if args.seed_common_files:
        seed_common_archive_files()
        return
    results = []
    names = (args.name,) if args.name else TARGETS
    for name in names:
        print(json.dumps({'name': name, 'stage': 'checking-and-archiving'}), flush=True)
        result = archive(name, args.archive_and_remove)
        results.append(result)
        print(json.dumps(result), flush=True)
        if args.archive_and_remove:
            save(RECEIPTS / 'summary.json', {'results': results})


if __name__ == '__main__':
    main()
