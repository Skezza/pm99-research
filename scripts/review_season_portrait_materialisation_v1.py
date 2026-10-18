#!/usr/bin/env python3
"""Check a cached portrait pilot and quarantine uncertain rows, without scraping.

Checks recipe identity, dated CSV identity, URL/edition binding, original cache
hash, exactly one sufficiently large face, and converted bitmap structure/hash.
These are source/framing checks, not independent facial identity certification.
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_portrait_pipeline_v1 as portrait
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.season_historical_photo_qa_v1 import decode, faces


def source_issues(row, player, csv_row):
    issues = []
    if player is None or row['name'] != player['name']:
        issues.append('recipe-player-name-mismatch')
    if csv_row is None:
        issues.append('source-id-not-in-captured-edition')
        return issues
    if portrait._name_score(row['name'], csv_row['short_name'], csv_row['long_name'])[0] < 85:
        issues.append('identity-match-below-85')
    if not player or player.get('facts', {}).get('birth_date') != csv_row['dob']:
        issues.append('source-birth-date-not-corroborated')
    source_id = int(csv_row['sofifa_id'])
    expected = f"https://cdn.sofifa.net/players/{source_id // 1000}/{source_id % 1000:03d}/{row['source_edition']}_120.png"
    if row.get('source_image_url') != expected:
        issues.append('image-url-identity-or-edition-mismatch')
    return issues


def run(manifest_path, output_root):
    import cv2
    cv2.setNumThreads(1)
    manifest = portrait._read_json(manifest_path)
    release = registry.load_preferred_release(manifest['season'])
    package = json.loads(release.package_path.read_text())
    if manifest['inputs']['package_canonical_sha256'] != registry.canonical_document_sha256(release.package_path):
        raise ValueError('portrait pilot targets another recipe')
    plan_path = Path(manifest['inputs']['plan_path'])
    if registry.sha256_file(plan_path) != manifest['inputs']['plan_sha256']:
        raise ValueError('portrait plan has changed')
    plan = portrait._read_json(plan_path)
    edition_path = Path(plan['inputs']['edition_csv_path'])
    edition_rows, digest = portrait._load_edition_rows(edition_path)
    if digest != plan['inputs']['edition_csv_sha256']:
        raise ValueError('dated source CSV has changed')
    edition = {int(p['sofifa_id']): p for p in edition_rows}
    players = {int(p['carrier_id']): p for p in package['players']}
    carriers = [int(row['carrier_id']) for row in manifest['players']]
    if len(carriers) != len(set(carriers)) or set(carriers) != set(players):
        raise ValueError('portrait pilot does not exactly cover the recipe')
    model = ROOT / '.local/season-historical-photo-pilots-v1/shared/face_detection_yunet_2023mar.onnx'
    detector = cv2.FaceDetectorYN_create(str(model), '', (320, 320), score_threshold=.75)
    result_rows, checks = [], []
    for row in manifest['players']:
        issues, face_detail = [], {}
        if row['status'] == 'applied':
            issues = source_issues(row, players.get(int(row['carrier_id'])), edition.get(int(row['sofifa_id'])))
            _, cache_path = portrait._cache_paths(portrait.DEFAULT_CACHE, row['source_image_url'])
            if not cache_path.is_file() or registry.sha256_file(cache_path) != row.get('source_sha256'):
                issues.append('original-source-bytes-not-bound')
            else:
                found = faces(detector, decode(cache_path.read_bytes()))
                face_detail = {'face_count': len(found), 'largest_face_pixels':
                               round(float(max(min(f[2], f[3]) for f in found)), 1) if len(found) else 0}
                if len(found) != 1 or face_detail['largest_face_pixels'] < 40:
                    issues.append('source-face-framing-uncertain')
            bitmap = Path(row['converted_path'])
            if not bitmap.is_file() or registry.sha256_file(bitmap) != row.get('converted_sha256'):
                issues.append('converted-bitmap-not-bound')
            else:
                portrait.validate_minifoto_bitmap(bitmap.read_bytes())
        updated = dict(row)
        if issues:
            updated.update(status='native-no-photo', reason='qa-quarantine:' + ','.join(issues))
        result_rows.append(updated)
        checks.append({'carrier_id': row['carrier_id'], 'name': row['name'], 'target_club': row['target_club'],
                       'previous_status': row['status'], 'status': updated['status'], 'issues': issues, **face_detail})
        if len(checks) % 1000 == 0:
            print(json.dumps({'checked': len(checks), 'quarantined': sum(bool(c['issues']) for c in checks)}), flush=True)
    statuses = Counter(p['status'] for p in result_rows)
    reviewed = {**manifest, 'players': result_rows, 'coverage': {**manifest['coverage'],
                'applied_count': statuses['applied'], 'native_no_photo_count': statuses['native-no-photo'],
                'status_counts': dict(statuses), 'pending_count': 0},
                'source_review': {'input_sha256': registry.sha256_file(manifest_path),
                                  'detector_sha256': registry.sha256_file(model)}}
    report = {'schema_version': 'pm99-portrait-materialisation-source-review-v1', 'season': manifest['season'],
              'input_sha256': registry.sha256_file(manifest_path), 'source_csv_sha256': digest,
              'players_checked': len(checks), 'quarantined_count': sum(bool(c['issues']) for c in checks),
              'issues': dict(Counter(i for c in checks for i in c['issues'])), 'coverage': reviewed['coverage'],
              'scope': 'Source identity, bytes and framing; NOT independent visual certification of every face.',
              'players': checks}
    output_root.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(output_root / 'reviewed-materialisation.json', reviewed)
    pipeline.write_canonical_json(output_root / 'source-review.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'players'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--materialisation', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.materialisation, args.output_root)
