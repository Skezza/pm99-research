#!/usr/bin/env python3
"""Archive three obsolete artwork game copies as verified local deltas.

Exact allowlist only. Preferred games, recipes, source caches and all unique
bytes are retained. The clean base becomes an explicit recovery dependency.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import compact_superseded_kit_experiments_v1 as compact
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import _active_game, atomic_bytes
from scripts import season_pipeline_v2 as pipeline

BASE = ROOT / '.local/season-pipeline-v2/pm99-base-clean'
OUTPUT = ROOT / '.local/cleanup-20261003/superseded-visual-game-deltas'
TARGETS = ('.local/season-visual-patches-v2/2014-15/playable/game',
           '.local/season-visual-patches-v3/2014-15/playable/game',
           '.local/season-visual-patches-v2/2015-16/playable/game')


def run(delete=False):
    preferred = {registry.load_preferred_release(s).game_path.resolve() for s in registry.supported_seasons()}
    base, dirs = compact.inventory(BASE)
    results = []
    for index, name in enumerate(TARGETS):
        source = ROOT / name
        target = OUTPUT / f'variant-{index+1}'
        receipt = target / 'receipt.json'
        if not source.exists():
            row = json.loads(receipt.read_text())
        else:
            if source.is_symlink() or source.resolve() in preferred or _active_game(source):
                raise ValueError('not an inactive superseded game: ' + name)
            original, directories = compact.inventory(source)
            delta = [k for k,v in original.items() if base.get(k,{}).get('sha256') != v['sha256']]
            for key in delta:
                dest = target / 'files' / key
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / key, dest)
                if compact.digest(dest) != original[key]['sha256']:
                    raise ValueError('delta verification failed')
            row = {'source': str(source), 'base': str(BASE), 'files': original, 'directories': directories,
                   'delta_files': delta, 'original_bytes': sum(v['size'] for v in original.values()),
                   'delta_bytes': sum(original[k]['size'] for k in delta), 'deleted': False,
                   'recovery': 'copy ONLY the listed inventory files from base/delta into a new directory; verify every SHA256',
                   'pi_backup': False}
            compact.save(receipt, row)
            # Rehash every reconstruction input immediately before removal.
            for key, expected in original.items():
                retained = target / 'files' / key if key in delta else BASE / key
                if compact.digest(retained) != expected['sha256']:
                    raise ValueError('full reconstruction verification failed')
            if compact.inventory(source)[0] != original:
                raise ValueError('source changed during compaction')
            if delete:
                shutil.rmtree(source)
                row['deleted'] = True
                compact.save(receipt, row)
                for locator in (registry.LOCAL_ROOT / 'releases').glob('*/*/locator.json'):
                    old = json.loads(locator.read_text())
                    if old.get('game_path') == name:
                        old.update(technical_status='archived-visual-game-delta',
                                   compact_game_recovery_receipt=registry.relative_workspace_path(receipt))
                        atomic_bytes(locator, pipeline.canonical_json_bytes(old))
        results.append({k:v for k,v in row.items() if k not in ('files','directories','delta_files')})
        print(json.dumps(results[-1]), flush=True)
    compact.save(OUTPUT / 'summary.json', {'variants': results, 'retained_base': str(BASE)})


def restore(variant, destination):
    if variant not in (1,2,3) or destination.exists():
        raise ValueError('choose variant 1--3 and a new recovery directory')
    row = json.loads((OUTPUT / f'variant-{variant}/receipt.json').read_text())
    delta = set(row['delta_files'])
    inputs = {}
    for name, expected in row['files'].items():
        path = OUTPUT / f'variant-{variant}/files' / name if name in delta else BASE / name
        if compact.digest(path) != expected['sha256']:
            raise ValueError('recovery input changed: ' + name)
        inputs[name] = path
    destination.mkdir(parents=True)
    for name, path in inputs.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
        expected = row['files'][name]
        os.chmod(target, expected['mode']); os.utime(target, ns=(expected['mtime_ns'],expected['mtime_ns']))
        if compact.digest(target) != expected['sha256']: raise ValueError('restored bytes differ')
    print(json.dumps({'restored':str(destination),'variant':variant,'files':len(inputs)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delete-verified-duplicates', action='store_true')
    parser.add_argument('--restore-variant',type=int)
    parser.add_argument('--destination',type=Path)
    args=parser.parse_args()
    if args.restore_variant:
        if not args.destination:parser.error('restore needs --destination')
        restore(args.restore_variant,args.destination)
    else:run(args.delete_verified_duplicates)
