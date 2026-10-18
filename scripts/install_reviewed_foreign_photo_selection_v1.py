#!/usr/bin/env python3
"""Install the explicitly reviewed cross-season real-photo selections."""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art
from scripts import season_art_transaction_v1 as transaction


def prepare(season, selection_root, review_path, output):
    release = registry.load_preferred_release(season)
    selection_path = selection_root / season / 'selection.json'
    selected = json.loads(selection_path.read_text())
    review = json.loads(review_path.read_text())
    if selected['package_sha256'] != art.sha(release.package_path):
        raise ValueError('photographic selection targets another recipe')
    decisions = {int(r['carrier_id']): r for r in review['rows'] if r['season'] == season}
    package = json.loads(release.package_path.read_text())
    players = {int(p['carrier_id']): p for p in package['players']}
    rows = []
    if output.exists() and any(output.iterdir()):
        plan_path = output / 'plan.json'
        receipt_path = output / 'patch/receipt.json'
        if not plan_path.is_file() or not receipt_path.is_file():
            raise ValueError('incomplete prepared output; inspect it before retrying')
        plan = json.loads(plan_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        if (plan['inputs']['release_id'] != release.release_id
                or plan['inputs']['package_sha256'] != art.sha(release.package_path)
                or plan['inputs']['selection_sha256'] != art.sha(selection_path)
                or plan['inputs']['visual_review_sha256'] != art.sha(review_path)
                or receipt['plan_sha256'] != art.sha(plan_path)
                or receipt['archive_before_sha256'] != art.sha(release.game_path / 'DBDAT/MINIFOTO.PKF')
                or any(not art.PATCH_FILE.fullmatch(name) or art.sha(output / 'patch' / name) != digest
                       for name, digest in receipt['outputs'].items())):
            raise ValueError('prepared photo patch bindings changed; do not resume it')
        return len(receipt['replacements'])
    output.mkdir(parents=True, exist_ok=True)
    for row in selected['players']:
        if row['status'] != 'source-and-framing-pass': continue
        carrier = int(row['carrier_id']); decision = decisions.get(carrier)
        if not decision: raise ValueError('source selection has not been visually reviewed')
        if not decision['accepted']: continue
        if selected.get('policy_version', '').startswith('football-face-') and (
                not decision.get('football_kit_confirmed') or not row.get('face_view', {}).get('passed')):
            raise ValueError('football clothing/framing has not been confirmed')
        if (row['source_sha256'] != decision['source_sha256'] or row['bitmap_sha256'] != decision['bitmap_sha256']
                or row['name'] != players[carrier]['name']
                or row['birth_date'] != players[carrier]['facts']['birth_date']
                or art.sha(Path(row['bitmap_path'])) != row['bitmap_sha256']):
            raise ValueError('reviewed player, source or bitmap changed')
        installed = release.game_path / 'DBDAT/MINIFOTO' / f'J96{carrier:05d}.BMP'
        if installed.is_file() and art.sha(installed) == row['bitmap_sha256']:
            continue
        target = output / 'patch/DBDAT/MINIFOTO' / f'J96{carrier:05d}.BMP'
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(row['bitmap_path'], target)
        rows.append(row)
    if not rows:
        return 0
    no_photo, included = [], []
    old_path = ROOT / '.local/season-visual-patches-v2' / season / 'plan.json'
    if old_path.exists():
        old = json.loads(old_path.read_text())
        if old['inputs']['release_id'] == release.release_id:
            receipt = json.loads((old_path.parent / 'patch/receipt.json').read_text())
            if receipt['plan_sha256'] != art.sha(old_path) or receipt['archive_before_sha256'] != art.sha(release.game_path / 'DBDAT/MINIFOTO.PKF'):
                raise ValueError('old no-photo cleanup is stale')
            installed = {int(r['carrier_id']) for r in rows}
            no_photo = [r for r in old['no_photo'] if int(r['carrier_id']) not in installed]
            shutil.copyfile(old_path.parent / 'patch/DBDAT/MINIFOTO.PKF', output / 'patch/DBDAT/MINIFOTO.PKF')
            included = [art.sha(old_path)]
    plan = {'schema_version': art.SCHEMA, 'season': season,
            'inputs': {'release_id': release.release_id, 'package_sha256': art.sha(release.package_path),
                       'selection_sha256': art.sha(selection_path), 'visual_review_sha256': art.sha(review_path)},
            'no_photo': no_photo, 'replacements': [], 'included_visual_patch_plan_sha256s': included}
    art.save(output / 'plan.json', plan)
    receipt = {'schema_version': 'pm99-season-visual-patch-materialisation-v1', 'season': season,
               'plan_sha256': art.sha(output / 'plan.json'), 'archive_before_sha256': art.sha(release.game_path / 'DBDAT/MINIFOTO.PKF'),
               'outputs': {str(p.relative_to(output / 'patch')): art.sha(p) for p in sorted((output / 'patch').rglob('*')) if p.is_file()},
               'replacements': rows, 'no_photo_count': len(no_photo), 'visual_review_sha256': art.sha(review_path)}
    art.save(output / 'patch/receipt.json', receipt)
    return len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection-root', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--season', default='all')
    parser.add_argument('--release-id', required=True, help='fresh, explicit artwork revision; never reuse r9')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', args.release_id):
        parser.error('release-id must be a single safe directory name')
    outcomes = []
    for season in registry.supported_seasons():
        if args.season not in ('all',season): continue
        release_id = args.release_id
        current = registry.load_preferred_release(season)
        if current.release_id == release_id:
            outcomes.append({'season':season,'status':'already-installed'});continue
        output = args.output_root / season
        count = prepare(season, args.selection_root, args.review, output)
        if not count:
            outcomes.append({'season': season, 'status': 'no-new-approved-photos'})
            print(json.dumps(outcomes[-1]), flush=True)
            continue
        transaction.install(output / 'plan.json', output / 'patch',
            ROOT / '.local/season-art-transactions-v1' / release_id / season, release_id)
        outcomes.append({'season':season,'installed_real_photos':count})
        print(json.dumps(outcomes[-1]),flush=True)
    if args.season=='all':
        summary = args.output_root / 'summary.json'
        if not summary.exists():
            art.save(summary, {'seasons':outcomes})
