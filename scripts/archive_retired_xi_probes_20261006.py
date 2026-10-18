#!/usr/bin/env python3
"""Archive the remaining bytes of eleven retired, unregistered crash probes.

Their SFX/SIMULDAT assets already have separate verified archives. Preserve
all source/evidence receipts; refuse current references or active games. The
existing transport verifies every remote file and rechecks local bytes before
removing only the exact allowlisted child. Default is read-only.
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import archive_retired_season_tests_20261004 as transport
from scripts import archive_old_crash_probe_assets_20261006 as old
from scripts import archive_superseded_ingress_games_20261004 as ingress
from scripts import season_release_registry_v1 as registry

NAMES = tuple(f'2004-05-stoke-xi{i:02d}' for i in range(1, 12))
RECEIPTS = ROOT / '.local/duplicate-ownership-v3/space-recovery/retired-xi-probes'
REMOTE = '/srv/hdd/pm99-archive/packages/retired-xi-probes/20261006'


@lru_cache(maxsize=128)
def reference_paths(path, mtime_ns, size):
    # Cache expensive path resolution only while the exact source stat is
    # unchanged. Publication replaces/modifies these files, invalidating it.
    return tuple((ROOT / value).resolve() for value in
        ingress.nested_strings(json.loads(path.read_text()))
        if value.startswith(('.local/', str(ROOT) + '/')))


def guard(name):
    if name not in NAMES:
        raise ValueError('not an exact retired XI crash probe')
    source = old.guard_probe(name)
    source_root = source.resolve()
    for asset in old.ASSETS:
        receipt = old.RECEIPTS / name / asset / 'receipt.json'
        value = json.loads(receipt.read_text())
        if (source / asset).exists() or not value.get('archive_verified') or not value.get('local_removed'):
            raise ValueError('retired probe assets lack their completed separate archive')
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        targets = [(ROOT / value).resolve() for value in ingress.nested_strings(release.locator)
                   if value.startswith(('.local/', str(ROOT) + '/'))]
        for path in (release.package_path, release.release_manifest_path,
                     release.compiler_receipt_path, release.build_chain_path):
            stat = path.stat()
            targets.extend(reference_paths(path, stat.st_mtime_ns, stat.st_size))
        if any(target == source_root or target.is_relative_to(source_root) for target in targets):
            raise ValueError('current release or rebuild input refers to retired probe')
    return source


def run(apply=False):
    transport.WORKSPACE = ROOT / '.local/probes'
    transport.TARGETS = NAMES
    transport.RECEIPTS = RECEIPTS
    transport.REMOTE = REMOTE
    transport.REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/retired-xi-probes-20261006'
    rows = []
    for name in NAMES:
        source = transport.WORKSPACE / name
        if not source.exists():
            receipt = json.loads((RECEIPTS / name / 'receipt.json').read_text())
            if not receipt.get('archive_verified') or not receipt.get('local_removed'):
                raise ValueError('missing retired probe lacks verified archive')
            rows.append(receipt)
            continue
        source = guard(name)
        files = [p for p in source.rglob('*') if p.is_file()]
        row = {'probe': name, 'files': len(files), 'bytes': sum(p.stat().st_size for p in files),
               'allocated_bytes': sum(p.stat().st_blocks * 512 for p in files), 'read_only': True}
        if apply:
            # Recheck task-specific reference guards at the exact deletion gate.
            original_guard = transport.guard
            def gate(path):
                original_guard(path)
                guard(path.name)
            transport.guard = gate
            try:
                row = transport.archive(name, True)
            finally:
                transport.guard = original_guard
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ('files', 'directories')}), flush=True)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-and-remove', action='store_true')
    args = parser.parse_args()
    run(args.archive_and_remove)
