#!/usr/bin/env python3
"""Retain exact reconstruction deltas before deleting obsolete crash controls.

Scope is only unique EQ/JUG/ENT FDI copies under crash04-diagnostics-v1,
excluding the successful identity-repair control. Logs, receipts, EXEs,
archives, source recipes and all playable games are never deletion targets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import json_storage_io_v1 as storage_io
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json
from scripts import season_release_registry_v1 as registry

CONTROLS = ROOT / '.local/crash04-diagnostics-v1'
BASE = ROOT / '.local/season-pipeline-v2/pm99-base-clean/DBDAT'
OUTPUT = ROOT / '.local/cleanup-20261004/crash04-database-deltas'
ALLOWED = {'EQ98030.FDI', 'JUG98030.FDI', 'ENT98030.FDI'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def recover(row, output=OUTPUT):
    base = storage_io.read_bytes(ROOT / row['base_path'])
    delta_path = output / row['delta_path']
    if not storage_io.is_file(delta_path):
        archive = output / 'pi-archive.json'
        if not storage_io.is_file(archive):
            raise ValueError('local reconstruction delta missing and no Pi archive recorded')
        remote = json.loads(storage_io.read_text(archive))
        delta_path = Path(remote['mounted_archive_root']) / row['delta_path']
        if not storage_io.is_file(delta_path):
            raise ValueError('mount the verified Pi archive before restoring this retired control: '
                             + remote['smb_uri'])
    packed = storage_io.read_bytes(delta_path)
    if sha(base) != row['base_sha256'] or sha(packed) != row['delta_sha256']:
        raise ValueError('reconstruction input changed')
    delta = zlib.decompress(packed)
    if len(delta) != row['target_size']:
        raise ValueError('wrong delta length')
    common = min(len(base), row['target_size'])
    target = bytes(a ^ b for a, b in zip(base[:common], delta[:common])) + delta[common:]
    if sha(target) != row['target_sha256']:
        raise ValueError('reconstructed bytes do not match original')
    return target


def compact(execute=False):
    receipt_path = OUTPUT / 'receipt.json'
    if storage_io.exists(receipt_path):
        receipt = json.loads(storage_io.read_text(receipt_path))
    else:
        games = [storage_io.resolve(registry.load_preferred_release(s).game_path) for s in registry.supported_seasons()]
        rows = []
        for source in sorted(storage_io.glob(CONTROLS, '*/DBDAT/*.FDI')):
            if source.parent.parent.name == 'identity-repair' or source.name not in ALLOWED:
                continue
            info = source.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                continue
            if any(storage_io.resolve(source).is_relative_to(game) for game in games):
                raise ValueError('diagnostic file is part of a preferred game')
            if not storage_io.is_file(source.parent / 'diagnostic.json'):
                raise ValueError('diagnostic recipe missing: ' + str(source))
            base_path = BASE / source.name
            base, target = storage_io.read_bytes(base_path), storage_io.read_bytes(source)
            common = min(len(base), len(target))
            packed = zlib.compress(bytes(a ^ b for a, b in zip(base[:common], target[:common])) + target[common:], 9)
            delta_name = 'files/' + sha(packed) + '.xor.zlib'
            row = {'source_path': str(source.relative_to(ROOT)),
                'base_path': str(base_path.relative_to(ROOT)), 'base_sha256': sha(base),
                'target_sha256': sha(target), 'target_size': len(target),
                'delta_path': delta_name, 'delta_sha256': sha(packed),
                'allocated_bytes_before': info.st_blocks * 512, 'mode': stat.S_IMODE(info.st_mode),
                'mtime_ns': info.st_mtime_ns}
            rows.append(row)
            if execute:
                destination = OUTPUT / delta_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if storage_io.exists(destination) and storage_io.read_bytes(destination) != packed:
                    raise ValueError('delta collision')
                if not storage_io.exists(destination):
                    storage_io.write_bytes(destination, packed)
        if not execute:
            return {'status': 'planned', 'files': len(rows),
                    'logical_bytes': sum(r['target_size'] for r in rows), 'targets': rows}
        receipt = {'schema_version': 'pm99-crash04-database-compaction-v1', 'state': 'prepared',
            'rows': rows, 'preserved': ['identity-repair control', 'all diagnostic recipes and logs',
                'all executables', 'all art archives', 'all preferred releases'],
            'recovery_base_must_be_preserved': str(BASE.relative_to(ROOT))}
        _atomic_replace_json(receipt_path, receipt)
    # Verify every recovery input before unlinking any source. This is also
    # the read-only post-removal integrity check and interruption recovery.
    for row in receipt['rows']:
        recovered = recover(row)
        source = ROOT / row['source_path']
        storage_io.resolve(source).relative_to(storage_io.resolve(CONTROLS))
        if source.name not in ALLOWED or source.parent.parent.name == 'identity-repair':
            raise ValueError('unsafe removal target')
        if storage_io.exists(source) and (source.is_symlink() or storage_io.read_bytes(source) != recovered):
            raise ValueError('source changed since receipt')
    if execute:
        for row in receipt['rows']:
            source = ROOT / row['source_path']
            if storage_io.exists(source):
                if sha(storage_io.read_bytes(source)) != row['target_sha256']:
                    raise ValueError('source changed before deletion')
                storage_io.unlink(source)
        receipt['state'] = 'compacted'
        _atomic_replace_json(receipt_path, receipt)
    return {'status': receipt['state'], 'files_verified': len(receipt['rows']),
            'original_allocated_bytes': sum(r['allocated_bytes_before'] for r in receipt['rows']),
            'local_delta_bytes': sum(storage_io.size(p) for p in (OUTPUT / 'files').iterdir())
                if (OUTPUT / 'files').is_dir() else 0,
            'pi_archive_recorded': storage_io.is_file(OUTPUT / 'pi-archive.json'),
            'receipt': str(receipt_path.relative_to(ROOT))}


def archive_deltas(mounted_root, smb_uri):
    """Remove only our newly generated delta blobs after independent readback."""
    receipt_path = OUTPUT / 'receipt.json'
    receipt = json.loads(storage_io.read_text(receipt_path))
    if receipt['state'] != 'compacted':
        raise ValueError('database compaction has not completed')
    if storage_io.read_bytes(mounted_root / 'receipt.json') != storage_io.read_bytes(receipt_path):
        raise ValueError('Pi reconstruction receipt differs')
    verified = {}
    for row in receipt['rows']:
        name = row['delta_path']
        if name in verified:
            continue
        if sha(storage_io.read_bytes(mounted_root / name)) != row['delta_sha256']:
            raise ValueError('Pi delta readback hash mismatch')
        local = OUTPUT / name
        storage_io.resolve(local).relative_to(storage_io.resolve(OUTPUT / 'files'))
        if storage_io.exists(local) and sha(storage_io.read_bytes(local)) != row['delta_sha256']:
            raise ValueError('local delta changed during archival')
        verified[name] = row['delta_sha256']
    record = {'schema_version': 'pm99-crash04-pi-delta-archive-v1',
        'mounted_archive_root': str(mounted_root), 'smb_uri': smb_uri,
        'receipt_sha256': sha(storage_io.read_bytes(receipt_path)), 'verified_files': verified,
        'verification': 'rsync checksum pass plus independent anonymous SMB SHA256 readback'}
    _atomic_replace_json(OUTPUT / 'pi-archive.json', record)
    for name in verified:
        local = OUTPUT / name
        if storage_io.exists(local):
            storage_io.unlink(local)
    return compact(False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--restore-file', help='exact original source path listed in the retained receipt')
    parser.add_argument('--destination', type=Path, help='new disposable path for restored file')
    parser.add_argument('--archive-deltas', type=Path, help='verified mounted Pi copy of this delta directory')
    parser.add_argument('--smb-uri')
    args = parser.parse_args()
    if args.archive_deltas:
        if not args.smb_uri:
            parser.error('--archive-deltas requires --smb-uri')
        print(json.dumps(archive_deltas(args.archive_deltas, args.smb_uri), indent=2))
    elif args.restore_file:
        if not args.destination or storage_io.exists(args.destination):
            parser.error('restoration requires a new --destination')
        receipt = json.loads(storage_io.read_text(OUTPUT / 'receipt.json'))
        matches = [r for r in receipt['rows'] if r['source_path'] == args.restore_file]
        if len(matches) != 1:
            parser.error('source path is not in the reconstruction receipt')
        storage_io.resolve(args.destination).relative_to(ROOT / '.local')
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        storage_io.write_bytes(args.destination, recover(matches[0]))
        print(json.dumps({'restored': str(args.destination), 'sha256': sha(storage_io.read_bytes(args.destination))}))
    else:
        print(json.dumps(compact(args.execute), indent=2))


if __name__ == '__main__':
    main()
