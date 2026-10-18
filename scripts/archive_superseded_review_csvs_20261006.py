#!/usr/bin/env python3
"""Move only regenerable CSV views from a fixed superseded review to the Pi.

Keep the underlying JSON reports, raw sources, recipes and every current game.
Default is read-only. All-file remote hashes and a fresh local hash gate removal.
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

SOURCE = ROOT / '.local/historical-authored-clubs-review-20261005-r1'
REMOTE = '/srv/hdd/pm99-archive/evidence/superseded-review-csvs/20261006'
RECEIPT = ROOT / '.local/duplicate-ownership-v3/space-recovery/superseded-review-csvs.json'
ADDITIONAL_REVIEW_ROOTS = (
    'historical-review-inventory-20261004-r1',
    'historical-review-inventory-20261004-r2',
    'historical-roster-audit-20261004-r1',
    'historical-roster-audit-20261004-r3',
)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def run(delete=False, review_root=None):
    if review_root is not None and review_root not in ADDITIONAL_REVIEW_ROOTS:
        raise ValueError('review root is outside the fixed regenerable CSV allowlist')
    source = ROOT / '.local' / review_root if review_root else SOURCE
    remote = REMOTE + '/' + review_root if review_root else REMOTE
    receipt = RECEIPT.with_name(review_root + '-csvs.json') if review_root else RECEIPT
    if receipt.exists():
        raise ValueError('archive receipt already exists; do not overwrite')
    references = set()
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        for value in strings([release.locator, json.loads(release.package_path.read_text())]):
            if value.endswith('players.csv'):
                path = Path(value)
                references.add((path if path.is_absolute() else ROOT / path).resolve())
                references.add((release.package_path.parent / path).resolve())
    files = []
    for season in registry.supported_seasons():
        path = source / season / 'players.csv'
        if not path.exists():
            continue
        if (path.is_symlink() or path.resolve().parent.parent != source.resolve()
                or path.resolve() in references):
            raise ValueError('CSV is not an unreferenced exact superseded export')
        files.append({'path': registry.relative_workspace_path(path),
            'sha256': registry.sha256_file(path), 'size': path.stat().st_size,
            'allocated_bytes': path.stat().st_blocks * 512})
    result = {'schema_version': 'pm99-superseded-review-csv-archive-v1',
        'host': archive.HOST, 'remote': remote, 'files': files,
        'file_count': len(files), 'logical_bytes': sum(f['size'] for f in files),
        'allocated_bytes': sum(f['allocated_bytes'] for f in files),
        'local_removed': False, 'source_json_reports_retained': True}
    if not delete:
        return result
    if archive.remote('findmnt -n -o UUID --target /srv/hdd').strip() != archive.DISK_UUID:
        raise ValueError('Pi archive disk is not the verified mounted disk')
    archive.remote('mkdir -p ' + shlex.quote(remote))
    for row in files:
        relative = Path(row['path']).relative_to(source.relative_to(ROOT))
        target = remote + '/' + relative.as_posix()
        archive.remote('mkdir -p ' + shlex.quote(str(Path(target).parent)))
        archive.command(['rsync', '-lt', '-e', 'ssh -o BatchMode=yes -o ConnectTimeout=8',
            str(ROOT / row['path']), archive.HOST + ':' + target])
        row['remote_path'] = target
    checks = ''.join(row['sha256'] + '  ' + row['remote_path'] + '\n' for row in files)
    archive.remote('sha256sum --check --quiet', stdin=checks)
    if any(registry.sha256_file(ROOT / row['path']) != row['sha256'] for row in files):
        raise ValueError('local export changed during transfer')
    result['verification'] = 'remote SHA256 and fresh local SHA256; exact old CSV views only'
    archive.save(receipt, result)
    archive.command(['rsync', '-lt', '-e', 'ssh -o BatchMode=yes -o ConnectTimeout=8',
        str(receipt), archive.HOST + ':' + remote + '/receipt.json'])
    archive.remote('sync')
    for row in files:
        (ROOT / row['path']).unlink()
    result['local_removed'] = True
    archive.save(receipt, result)
    archive.command(['rsync', '-lt', '-e', 'ssh -o BatchMode=yes -o ConnectTimeout=8',
        str(receipt), archive.HOST + ':' + remote + '/receipt.json'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delete-local-after-verification', action='store_true')
    parser.add_argument('--review-root', choices=ADDITIONAL_REVIEW_ROOTS)
    args = parser.parse_args()
    row = run(args.delete_local_after_verification, args.review_root)
    print(json.dumps({k: v for k, v in row.items() if k != 'files'}))
