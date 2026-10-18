#!/usr/bin/env python3
"""Archive obsolete ingress game children, retaining their local recipes/receipts.

Default is a read-only list. --plan records the exact targets; --apply requires
that plan. Current release paths and rebuild/recovery bases cannot be selected.
Old launch locations intentionally cease to work; current pm99-season commands
are unchanged. Restore an archived game to a fresh directory before using it.
"""
import argparse
import fcntl
from functools import lru_cache
import json
import os
import shlex
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import archive_retired_season_tests_20261004 as transport
from scripts import compact_superseded_kit_experiments_v1 as compact
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes

HOST = transport.HOST
REMOTE = '/srv/hdd/pm99-archive/packages/superseded-ingress-games/20261004'
REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/superseded-ingress-games-20261004'
OUTPUT = ROOT / '.local/cleanup-20261004/superseded-ingress-games'
ROOTS = ('season-static-ingress-v1', 'season-static-ingress-batch-v1',
         'season-quality-ingress-v1')
GLOBS = ('*/game', '*/*/game', '*/*/game')


def save(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def selected_shape(path):
    parts = path.relative_to(ROOT).parts
    return (len(parts) in (4, 5) and parts[0] == '.local' and parts[-1] == 'game'
            and parts[1] in ROOTS
            and len(parts) == (4 if parts[1] == ROOTS[0] else 5))


def nested_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from nested_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_strings(item)


@lru_cache(maxsize=64)
def package_paths(path, mtime_ns, size):
    # The stat signature invalidates the cache if an editor changes a recipe.
    values = set(value for value in nested_strings(json.loads(path.read_text()))
                 if value.startswith(('.local/', str(ROOT) + '/')))
    return tuple(str((ROOT / value).resolve()) for value in values)


def guard(source):
    if not selected_shape(source) or source.is_symlink() or source.resolve() != source.absolute():
        raise ValueError('not an exact permitted game child: ' + str(source))
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        # Protect all current locator paths, not only its primary game.
        for value in nested_strings(release.locator):
            if value.startswith('.local/'):
                target = (ROOT / value).resolve()
                if target == source or target.is_relative_to(source):
                    raise ValueError('current release depends on this game: ' + season)
        # Current rebuild is previous.game + clean base; recipes stay local.
        stat = release.package_path.stat()
        if any(target == str(source) or target.startswith(str(source) + '/')
               for target in package_paths(release.package_path, stat.st_mtime_ns, stat.st_size)):
            raise ValueError('current recipe depends on this game: ' + season)
    # Do not remove any installation in use, even by an ordinary shell.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if Path(os.readlink(proc / 'cwd')).is_relative_to(source):
                raise ValueError('process working in game: ' + proc.name)
            for fd in (proc / 'fd').iterdir():
                try:
                    if Path(os.readlink(fd)).is_relative_to(source):
                        raise ValueError('process has game file open: ' + proc.name)
                except OSError:
                    pass
        except OSError:
            pass


def disk_guard():
    if transport.remote('findmnt -n -o UUID --target /srv/hdd').strip() != transport.DISK_UUID:
        raise ValueError('Pi archive disk is not mounted with expected UUID')


def receipt_path(source):
    return OUTPUT / source.relative_to(ROOT / '.local') / 'receipt.json'


def destination(source):
    return REMOTE + '/' + source.relative_to(ROOT / '.local').as_posix()


def archive(source):
    receipt = receipt_path(source)
    if not source.exists():
        row = json.loads(receipt.read_text())
        if not row.get('archive_verified') or not row.get('local_removed'):
            raise ValueError('missing source without completed receipt')
        return row
    guard(source)
    disk_guard()
    files, directories = compact.inventory(source)
    allocated = sum(p.stat().st_blocks * 512 for p in source.rglob('*') if p.is_file())
    remote = destination(source)
    transport.remote('mkdir -p ' + shlex.quote(remote) + ' ' + shlex.quote(REMOTE_RECEIPTS))
    row = dict(source=str(source), host=HOST, remote=remote, files=files,
               directories=directories, file_count=len(files),
               logical_bytes=sum(v['size'] for v in files.values()),
               allocated_file_bytes=allocated, archive_verified=False, local_removed=False)
    save(receipt, row)
    # Only immutable REMOTE archive bytes are hardlinked. Default rsync uses
    # temporary new files + rename, never --inplace and never writable local links.
    seed = transport.REMOTE + '/' + transport.TARGETS[0]
    ssh = 'ssh -o BatchMode=yes -o ConnectTimeout=8'
    # Compare content, not build-specific timestamps. Original metadata is in
    # the receipt. Omitting -t permits identical immutable files to share inodes
    # even when the old build stamped every unchanged native file with a new date.
    transport.command(['rsync', '-rlcpz', '--compress-level=1', '--link-dest=' + seed,
                       '-e', ssh, str(source) + '/', HOST + ':' + remote + '/'])
    checks = ''.join(v['sha256'] + '  ' + k + '\n' for k, v in files.items())
    transport.remote('cd ' + shlex.quote(remote) + ' && sha256sum --check --quiet', stdin=checks)
    diff = transport.command(['rsync', '-rcni', '--delete', '-e', ssh,
                              str(source) + '/', HOST + ':' + remote + '/'])
    if diff.strip():
        raise ValueError('archive checksum comparison differs: ' + diff[:200])
    if compact.inventory(source) != (files, directories):
        raise ValueError('source changed during archive')
    guard(source)
    disk_guard()
    row['archive_verified'] = True
    row['verification'] = 'all-file Pi SHA256, empty checksum-rsync, fresh local inventory'
    save(receipt, row)
    remote_receipt = REMOTE_RECEIPTS + '/' + source.relative_to(ROOT / '.local').as_posix().replace('/', '__') + '.json'
    transport.command(['rsync', '-lt', '-e', ssh, str(receipt), HOST + ':' + remote_receipt])
    transport.remote('sync')
    # Exact planned child only; no artifact root or source/receipt directory.
    shutil.rmtree(source)
    row['local_removed'] = True
    save(receipt, row)
    marker = source.parent / 'game.pi-archive.json'
    save(marker, {k: row[k] for k in ('source', 'host', 'remote', 'file_count', 'logical_bytes',
                                    'archive_verified', 'local_removed')})
    # Older registered releases must report archival explicitly, not silently
    # look like broken current releases. No preferred locator is modified.
    for locator in (registry.LOCAL_ROOT / 'releases').glob('*/*/locator.json'):
        old = json.loads(locator.read_text())
        if old.get('game_path') == source.relative_to(ROOT).as_posix():
            old.update(technical_status='archived-superseded-game-on-pi',
                       archived_game_receipt_path=receipt.relative_to(ROOT).as_posix(),
                       archived_game_host=HOST, archived_game_path=remote)
            save(locator, old)
    transport.command(['rsync', '-lt', '-e', ssh, str(receipt), HOST + ':' + remote_receipt])
    expected = compact.digest(receipt)
    actual = transport.remote('sha256sum ' + shlex.quote(remote_receipt)).split()[0]
    if actual != expected:
        raise ValueError('completed remote receipt differs')
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--jobs', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--verify-current', action='store_true')
    parser.add_argument('--verify-receipts', action='store_true')
    args = parser.parse_args()
    if args.verify_current:
        rows = [registry.validate_preferred_release(s, level='release')
                for s in registry.supported_seasons()]
        plan = json.loads((OUTPUT / 'plan.json').read_text())
        unchanged = compact.digest(registry.CATALOG_PATH) == plan['catalogue_sha256']
        report = {'valid': all(r['valid'] for r in rows) and unchanged,
                  'catalogue_unchanged': unchanged, 'seasons': rows,
                  'free_bytes': shutil.disk_usage(ROOT).free}
        save(OUTPUT / 'post-cleanup-current-release-validation.json', report)
        print(json.dumps({k: v for k, v in report.items() if k != 'seasons'}))
        if not report['valid']:
            raise ValueError('current release validation failed')
        return
    if args.verify_receipts:
        disk_guard()
        plan = json.loads((OUTPUT / 'plan.json').read_text())
        checks, count, files = [], 0, 0
        for target in plan['targets']:
            source = ROOT / target
            receipt = receipt_path(source)
            row = json.loads(receipt.read_text())
            if source.exists() or not row.get('local_removed') or not row.get('archive_verified'):
                raise ValueError('archive not complete: ' + target)
            if row['remote'] != destination(source) or row['host'] != HOST:
                raise ValueError('archive receipt location differs')
            name = source.relative_to(ROOT / '.local').as_posix().replace('/', '__') + '.json'
            checks.append(compact.digest(receipt) + '  ' + REMOTE_RECEIPTS + '/' + name + '\n')
            count += 1
            files += row['file_count']
        transport.remote('sha256sum --check --quiet', stdin=''.join(checks))
        report = {'completed_archives': count, 'archived_file_count': files,
                  'all_completed_remote_receipt_sha256s_match': True,
                  'note': 'Each original file SHA256 was checked on Pi before deletion; this is a fresh receipt check, not another full archive read.'}
        save(OUTPUT / 'final-receipt-verification.json', report)
        print(json.dumps(report))
        return
    OUTPUT.mkdir(parents=True, exist_ok=True) if args.plan or args.apply else None
    if not args.apply:
        targets = sorted(p for name, glob in zip(ROOTS, GLOBS)
                         for p in (ROOT / '.local' / name).glob(glob)
                         if (p / 'MANAGPRE.EXE').is_file())
        for p in targets:
            guard(p)
        row = {'catalogue_sha256': compact.digest(registry.CATALOG_PATH),
               'targets': [p.relative_to(ROOT).as_posix() for p in targets]}
        if args.plan:
            path = OUTPUT / 'plan.json'
            if path.exists():
                raise ValueError('existing plan; do not replace audit history')
            save(path, row)
        print(json.dumps(row, indent=2))
        return
    with (OUTPUT / 'cleanup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = json.loads((OUTPUT / 'plan.json').read_text())
        if compact.digest(registry.CATALOG_PATH) != plan['catalogue_sha256']:
            raise ValueError('preferred seasons changed since plan')
        def process(target):
            source = ROOT / target
            if not selected_shape(source):
                raise ValueError('invalid planned child')
            print(json.dumps({'archiving': target}), flush=True)
            row = archive(source)
            brief = {k: row[k] for k in ('source', 'remote', 'file_count', 'logical_bytes',
                                       'allocated_file_bytes', 'local_removed')}
            print(json.dumps(brief), flush=True)
            return brief
        results = []
        # Warm the read-only dependency cache once before concurrent archiving.
        remaining = [ROOT / p for p in plan['targets'] if (ROOT / p).exists()]
        if remaining:
            guard(remaining[0])
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for brief in pool.map(process, plan['targets']):
                results.append(brief)
                summary = {'results': results, 'count': len(results),
                           'allocated_file_bytes_removed': sum(r['allocated_file_bytes'] for r in results),
                           'catalogue_unchanged': compact.digest(registry.CATALOG_PATH) == plan['catalogue_sha256']}
                save(OUTPUT / 'summary.json', summary)


if __name__ == '__main__':
    main()
