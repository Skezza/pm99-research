#!/usr/bin/env python3
"""Retain byte-verified deltas before deleting explicitly superseded kit games.

The retained V4 game is the reconstruction base. This is not a general cleaner:
the only removable targets are the eight historical experiments named below.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / '.local/season-workspace-v1'
BASE = WORKSPACE / '2015-16-kit-factory-template-v4-native-hem-contour-game'
OUTPUT = ROOT / '.local/cleanup-20261003/kit-experiment-deltas'
TARGETS = (
    '2015-16-kit-factory-template-v1-game',
    '2015-16-kit-factory-template-v1-barcelona-selector-probe-game',
    '2015-16-kit-factory-template-v1-barcelona-selector-probe-r2-game',
    '2015-16-kit-factory-template-v2-pattern-structure-game',
    '2015-16-kit-factory-template-v2-pattern-structure-barcelona-selector-probe-game',
    '2015-16-kit-factory-template-v3-native-boundaries-game',
    '2015-16-kit-factory-template-v3-native-boundaries-barcelona-selector-probe-game',
    '2015-16-kit-shading-v1-game',
)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory(path):
    files, directories = {}, []
    for child in sorted(path.rglob('*')):
        if child.is_symlink():
            raise ValueError(f'Refusing symlink: {child}')
        key = child.relative_to(path).as_posix()
        if child.is_dir():
            directories.append(key)
        elif child.is_file():
            s = child.stat()
            files[key] = {'sha256': digest(child), 'size': s.st_size,
                          'mtime_ns': s.st_mtime_ns, 'mode': stat.S_IMODE(s.st_mode)}
        else:
            raise ValueError(f'Refusing special file: {child}')
    return files, directories


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def run(delete=False):
    if BASE.is_symlink() or not BASE.is_dir():
        raise ValueError('Retained V4 base missing or symlinked')
    base_files, base_dirs = inventory(BASE)
    save(OUTPUT / 'retained-base-inventory.json', {'base': str(BASE), 'files': base_files,
                                                 'directories': base_dirs})
    results = []
    for name in TARGETS:
        source = WORKSPACE / name
        receipt = OUTPUT / name / 'receipt.json'
        if not source.exists():
            if receipt.is_file():
                results.append(json.loads(receipt.read_text()))
                continue
            raise ValueError(f'Expected experiment missing without receipt: {source}')
        if source.is_symlink() or source.resolve().parent != WORKSPACE.resolve():
            raise ValueError(f'Unsafe target: {source}')
        original, directories = inventory(source)
        changed = [key for key, value in original.items()
                   if base_files.get(key, {}).get('sha256') != value['sha256']]
        delta = OUTPUT / name / 'files'
        for key in changed:
            destination = delta / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / key, destination)
            if digest(destination) != original[key]['sha256']:
                raise ValueError(f'Delta copy verification failed: {key}')
        # Every original file is represented by a verified delta or the base.
        for key, value in original.items():
            retained = delta / key if key in changed else BASE / key
            if key not in changed and base_files[key]['sha256'] != value['sha256']:
                raise ValueError(f'Reconstruction mismatch: {key}')
            current = (source / key).stat()
            if (current.st_size, current.st_mtime_ns) != (value['size'], value['mtime_ns']):
                raise ValueError(f'Source changed during verification: {key}')
            if not retained.is_file():
                raise ValueError(f'Retained reconstruction input missing: {key}')
        row = {'source': str(source), 'base': str(BASE), 'files': original,
               'directories': directories, 'delta_files': changed,
               'original_bytes': sum(v['size'] for v in original.values()),
               'delta_bytes': sum(original[k]['size'] for k in changed),
               'verification': 'all-file SHA256 equality against retained base plus copied deltas',
               'pi_backup': 'not attempted: Pi archive returns filesystem I/O errors',
               'local_disposition': 'verified-retained' }
        save(receipt, row)
        if delete:
            # Exact literal allowlist target, never a workspace or archive root.
            shutil.rmtree(source)
            row['local_disposition'] = 'duplicate-full-game-removed; unique-files-retained-locally'
            save(receipt, row)
        results.append(row)
        print(json.dumps({k: row[k] for k in ('source', 'original_bytes', 'delta_bytes',
                                              'local_disposition')}), flush=True)
        save(OUTPUT / 'summary.json', {'experiments': [{k: v for k, v in r.items()
                                                      if k not in ('files', 'directories')}
                                                     for r in results]})
    return results


def verify_retained():
    """Check recoverability without recreating any complete game copies."""
    base, _ = inventory(BASE)
    checked = 0
    for name in TARGETS:
        directory = OUTPUT / name
        row = json.loads((directory / 'receipt.json').read_text())
        for key, expected in row['files'].items():
            actual = (digest(directory / 'files' / key) if key in row['delta_files']
                      else base.get(key, {}).get('sha256'))
            if actual != expected['sha256']:
                raise ValueError(f'Reconstruction input mismatch: {name}/{key}')
            checked += 1
    print(json.dumps({'result': 'recoverability-verified', 'experiments': len(TARGETS),
                      'file_hash_comparisons': checked}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delete-verified-duplicates', action='store_true')
    parser.add_argument('--verify-retained', action='store_true')
    args = parser.parse_args()
    if args.verify_retained:
        verify_retained()
    else:
        run(args.delete_verified_duplicates)
