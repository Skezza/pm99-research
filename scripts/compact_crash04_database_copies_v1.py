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
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json
from scripts import season_release_registry_v1 as registry

CONTROLS = ROOT / '.local/crash04-diagnostics-v1'
BASE = ROOT / '.local/season-pipeline-v2/pm99-base-clean/DBDAT'
OUTPUT = ROOT / '.local/cleanup-20261004/crash04-database-deltas'
ALLOWED = {'EQ98030.FDI', 'JUG98030.FDI', 'ENT98030.FDI'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def recover(row, output=OUTPUT):
    base = (ROOT / row['base_path']).read_bytes()
    delta_path = output / row['delta_path']
    if not delta_path.is_file():
        archive = output / 'pi-archive.json'
        if not archive.is_file():
            raise ValueError('local reconstruction delta missing and no Pi archive recorded')
        remote = json.loads(archive.read_text())
        delta_path = Path(remote['mounted_archive_root']) / row['delta_path']
        if not delta_path.is_file():
            raise ValueError('mount the verified Pi archive before restoring this retired control: '
                             + remote['smb_uri'])
    packed = delta_path.read_bytes()
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
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
    else:
        games = [registry.load_preferred_release(s).game_path.resolve() for s in registry.supported_seasons()]
        rows = []
        for source in sorted(CONTROLS.glob('*/DBDAT/*.FDI')):
            if source.parent.parent.name == 'identity-repair' or source.name not in ALLOWED:
                continue
            info = source.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                continue
            if any(source.resolve().is_relative_to(game) for game in games):
                raise ValueError('diagnostic file is part of a preferred game')
            if not (source.parent / 'diagnostic.json').is_file():
                raise ValueError('diagnostic recipe missing: ' + str(source))
            base_path = BASE / source.name
            base, target = base_path.read_bytes(), source.read_bytes()
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
                if destination.exists() and destination.read_bytes() != packed:
                    raise ValueError('delta collision')
                if not destination.exists():
                    destination.write_bytes(packed)
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
        source.resolve().relative_to(CONTROLS.resolve())
        if source.name not in ALLOWED or source.parent.parent.name == 'identity-repair':
            raise ValueError('unsafe removal target')
        if source.exists() and (source.is_symlink() or source.read_bytes() != recovered):
            raise ValueError('source changed since receipt')
    if execute:
        for row in receipt['rows']:
            source = ROOT / row['source_path']
            if source.exists():
                if sha(source.read_bytes()) != row['target_sha256']:
                    raise ValueError('source changed before deletion')
                source.unlink()
        receipt['state'] = 'compacted'
        _atomic_replace_json(receipt_path, receipt)
    return {'status': receipt['state'], 'files_verified': len(receipt['rows']),
            'original_allocated_bytes': sum(r['allocated_bytes_before'] for r in receipt['rows']),
            'local_delta_bytes': sum(p.stat().st_size for p in (OUTPUT / 'files').iterdir())
                if (OUTPUT / 'files').is_dir() else 0,
            'pi_archive_recorded': (OUTPUT / 'pi-archive.json').is_file(),
            'receipt': str(receipt_path.relative_to(ROOT))}


def archive_deltas(mounted_root, smb_uri):
    """Remove only our newly generated delta blobs after independent readback."""
    receipt_path = OUTPUT / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt['state'] != 'compacted':
        raise ValueError('database compaction has not completed')
    if (mounted_root / 'receipt.json').read_bytes() != receipt_path.read_bytes():
        raise ValueError('Pi reconstruction receipt differs')
    verified = {}
    for row in receipt['rows']:
        name = row['delta_path']
        if name in verified:
            continue
        if sha((mounted_root / name).read_bytes()) != row['delta_sha256']:
            raise ValueError('Pi delta readback hash mismatch')
        local = OUTPUT / name
        local.resolve().relative_to((OUTPUT / 'files').resolve())
        if local.exists() and sha(local.read_bytes()) != row['delta_sha256']:
            raise ValueError('local delta changed during archival')
        verified[name] = row['delta_sha256']
    record = {'schema_version': 'pm99-crash04-pi-delta-archive-v1',
        'mounted_archive_root': str(mounted_root), 'smb_uri': smb_uri,
        'receipt_sha256': sha(receipt_path.read_bytes()), 'verified_files': verified,
        'verification': 'rsync checksum pass plus independent anonymous SMB SHA256 readback'}
    _atomic_replace_json(OUTPUT / 'pi-archive.json', record)
    for name in verified:
        local = OUTPUT / name
        if local.exists():
            local.unlink()
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
        if not args.destination or args.destination.exists():
            parser.error('restoration requires a new --destination')
        receipt = json.loads((OUTPUT / 'receipt.json').read_text())
        matches = [r for r in receipt['rows'] if r['source_path'] == args.restore_file]
        if len(matches) != 1:
            parser.error('source path is not in the reconstruction receipt')
        args.destination.resolve().relative_to(ROOT / '.local')
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        args.destination.write_bytes(recover(matches[0]))
        print(json.dumps({'restored': str(args.destination), 'sha256': sha(args.destination.read_bytes())}))
    else:
        print(json.dumps(compact(args.execute), indent=2))


if __name__ == '__main__':
    main()
