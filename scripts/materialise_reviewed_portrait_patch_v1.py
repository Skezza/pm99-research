#!/usr/bin/env python3
"""Reuse QA-reviewed bitmaps in a small visual patch; no downloads or DB writes."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_visual_patch_v1 as patch
from scripts import season_portrait_pipeline_v1 as portraits
from scripts import season_release_registry_v1 as registry
from scripts.materialise_native_no_photo_v2 import _active_offsets_for_players


def materialise(manifest_path, output_root):
    manifest = json.loads(manifest_path.read_text())
    release = registry.load_preferred_release(manifest['season'])
    package = json.loads(release.package_path.read_text())
    if manifest['inputs']['package_canonical_sha256'] != registry.canonical_document_sha256(release.package_path):
        raise ValueError('reviewed materialisation targets another recipe')
    players = {int(p['carrier_id']): p for p in package['players']}
    rows = manifest['players']
    carriers = [int(p['carrier_id']) for p in rows]
    if len(set(carriers)) != len(rows) or set(carriers) != set(players):
        raise ValueError('reviewed materialisation does not exactly cover the recipe')
    for row in rows:
        if row['name'] != players[int(row['carrier_id'])]['name']:
            raise ValueError('reviewed player identity changed')
        if row['status'] == 'applied':
            bitmap = Path(row['converted_path'])
            if row.get('identity_score', 0) < 85 or patch.sha(bitmap) != row['converted_sha256']:
                raise ValueError('portrait failed identity/byte preflight')
            portraits.validate_minifoto_bitmap(bitmap.read_bytes())
        elif row['status'] != 'native-no-photo':
            raise ValueError('materialisation has pending players')
    if output_root.exists():
        raise ValueError('refusing to overwrite retained reviewed patch')
    output_root.mkdir(parents=True)
    no_photo = [{'carrier_id': p['carrier_id'], 'name': p['name'], 'reason': p.get('reason', 'no-reviewed-source')}
                for p in rows if p['status'] == 'native-no-photo']
    plan = {'schema_version': patch.SCHEMA, 'season': manifest['season'],
            'inputs': {'release_id': release.release_id, 'game': str(release.game_path),
                       'package_sha256': patch.sha(release.package_path),
                       'reviewed_materialisation_sha256': patch.sha(manifest_path)},
            'no_photo': no_photo, 'replacements': []}
    patch.save(output_root / 'plan.json', plan)
    root = output_root / 'patch'
    dbdat = root / 'DBDAT'
    dbdat.mkdir(parents=True)
    source_archive = release.game_path / 'DBDAT/MINIFOTO.PKF'
    data = bytearray(source_archive.read_bytes())
    offsets = _active_offsets_for_players(data, [p['carrier_id'] for p in no_photo])
    for places in offsets.values():
        for offset in places:
            data[offset] = 0
    (dbdat / 'MINIFOTO.PKF').write_bytes(data)
    for row in rows:
        if row['status'] == 'applied':
            loose = dbdat / 'MINIFOTO' / f"J96{int(row['carrier_id']):05d}.BMP"
            loose.parent.mkdir(exist_ok=True)
            loose.write_bytes(Path(row['converted_path']).read_bytes())
    receipt = {'schema_version': 'pm99-season-visual-patch-materialisation-v1', 'season': manifest['season'],
               'plan_sha256': patch.sha(output_root / 'plan.json'), 'archive_before_sha256': patch.sha(source_archive),
               'no_photo_count': len(no_photo), 'no_photo_offsets': offsets,
               'replacements': [p for p in rows if p['status'] == 'applied'],
               'reviewed_materialisation_sha256': patch.sha(manifest_path),
               'outputs': {str(p.relative_to(root)): patch.sha(p) for p in sorted(dbdat.rglob('*')) if p.is_file()}}
    patch.save(root / 'receipt.json', receipt)
    return {'players': len(rows), 'photos': len(receipt['replacements']), 'no_photo': len(no_photo)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--materialisation', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(materialise(args.materialisation, args.output_root)))
