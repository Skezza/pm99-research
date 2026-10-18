#!/usr/bin/env python3
"""Bounded foreign portrait expansion without full game copies or DB changes.

Source identity comes from the retained EA/SoFIFA ID/name/DOB catalogue. For
2014--22, matching the target edition's roster is required. Other editions use
the lifetime identity catalogue plus an EXACT target-edition image URL; this
does not assert the later source club belongs to the target season. Every
accepted face is checked for framing, and all installed bytes are inventoried.
"""
import argparse
import concurrent.futures
import csv
import io
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import cv2
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_portrait_pipeline_v1 as portraits
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art
from scripts import season_art_transaction_v1 as transaction
from scripts.season_historical_photo_qa_v1 import decode, faces


def source_index():
    path = ROOT / '.local/external-sources/sofifa-fifa16/male_players_legacy.csv'
    editions = defaultdict(lambda: defaultdict(dict))
    all_rows = defaultdict(dict)
    with path.open() as handle:
        for row in csv.DictReader(handle):
            candidate = {'sofifa_id': int(row['player_id']), 'short_name': row['short_name'],
                         'long_name': row['long_name'], 'dob': row['dob'], 'club': row['club_name'],
                         'source_profile': row['player_url'], 'source_edition': int(row['fifa_version'])}
            editions[candidate['source_edition']][candidate['dob']][candidate['sofifa_id']] = candidate
            all_rows[candidate['dob']][candidate['sofifa_id']] = candidate
    return path, editions, all_rows


def match(player, index):
    dob = player.get('facts', {}).get('birth_date')
    if not isinstance(dob, str): return None
    scored = [(portraits._name_score(player['name'], r['short_name'], r['long_name'])[0], r)
              for r in index.get(dob, {}).values()]
    scored = sorted((v for v in scored if v[0] >= 85), key=lambda v: (-v[0], v[1]['sofifa_id']))
    if not scored or len(scored) > 1 and scored[0][0] == scored[1][0]: return None
    return scored[0]


def prepare(season, output, source_path, editions, identities, detector, maximum):
    release = registry.load_preferred_release(season)
    if (output / 'patch/receipt.json').exists():
        raise ValueError('completed rollout output already exists')
    package = json.loads(release.package_path.read_text())
    club_names = portraits._club_by_player(package)
    from scripts.audit_registered_visual_assets_v1 import _source_roster_owners
    owners, _, modes = _source_roster_owners((release.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    edition = int(season[:4]) - 1999
    index = editions.get(edition, identities)
    grouped = defaultdict(list)
    used = set()
    for player in package['players']:
        carrier = int(player['carrier_id'])
        if not any(modes.get(c) == 1 for c in owners.get(carrier, [])): continue
        found = match(player, index)
        if not found or found[1]['sofifa_id'] in used: continue
        score, source = found
        used.add(source['sofifa_id'])
        source_id = source['sofifa_id']
        club = club_names.get(player['id'], '')
        grouped[club].append({'player_id': player['id'], 'carrier_id': carrier, 'name': player['name'],
            'birth_date': player['facts']['birth_date'], 'target_club': club, 'status': 'era-source-candidate',
            'sofifa_id': source_id, 'source_name': source['long_name'], 'identity_score': score,
            'source_identity_edition': source['source_edition'], 'source_profile': source['source_profile'],
            'source_edition': edition, 'source_image_url': f'https://cdn.sofifa.net/players/{source_id//1000}/{source_id%1000:03d}/{edition}_120.png',
            'era_grade': 'exact-target-edition-url', 'identity_policy':
                'target-edition-name-DOB' if edition in editions else 'stable-EA-ID-name-DOB-from-later-catalogue'})
    # Round-robin clubs: not merely a full elite-club roster then nothing else.
    candidates = []
    depth = 0
    while len(candidates) < maximum and any(depth < len(v) for v in grouped.values()):
        for club in sorted(grouped):
            if depth < len(grouped[club]) and len(candidates) < maximum:
                candidates.append(grouped[club][depth])
        depth += 1
    output.mkdir(parents=True, exist_ok=True)
    work_inputs = {'release_id': release.release_id, 'package_sha256': art.sha(release.package_path),
                   'source_sha256': art.sha(source_path), 'maximum': maximum, 'candidates': candidates}
    work_path = output / 'work-inputs.json'
    if work_path.exists():
        if json.loads(work_path.read_text()) != work_inputs:
            raise ValueError('resume inputs differ from the retained portrait job')
    else:
        art.save(work_path, work_inputs)
    records = list(portraits.iter_minifoto_records(release.game_path / 'DBDAT/MINIFOTO.PKF'))
    template = records[0]
    palette_path, _ = portraits.discover_riff_palette_resource(release.game_path / 'DBDAT/MINIFOTO.PKF',
        extra_roots=[release.game_path / 'DBDAT', release.game_path])
    palette = portraits.load_riff_palette(palette_path)
    palette_image = portraits._build_palette_image(palette)
    accepted, rejected = [], []
    for start in range(0, len(candidates), 16):
        if shutil.disk_usage(ROOT).free < 650 * 1024**2:
            raise ValueError('bounded rollout reached disk reserve; candidates retained, no game mutation')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            fetched = list(pool.map(lambda row: portraits._fetch(row, cache_root=portraits.DEFAULT_CACHE, timeout=12),
                                    candidates[start:start+16]))
        for result in fetched:
            row = {k:v for k,v in result.items() if k != 'payload'}
            raw = result.get('payload')
            if not raw:
                rejected.append(row); continue
            detected = faces(detector, decode(raw))
            if len(detected) != 1 or min(detected[0][2:4]) < 40:
                rejected.append({**row, 'reason': 'source-face-framing-uncertain'}); continue
            with Image.open(io.BytesIO(raw)) as image:
                bitmap, _, _ = portraits._build_replacement_bitmap(raw_bitmap_template=template.raw_bitmap,
                    pixel_offset=template.pixel_offset, width=template.width, height=template.height,
                    source_image=image, palette_image=palette_image, palette_rgb=palette,
                    allowed_indices=list(range(len(palette))))
            portraits.validate_minifoto_bitmap(bitmap)
            path = output / 'patch/DBDAT/MINIFOTO' / f'J96{int(row["carrier_id"]):05d}.BMP'
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != bitmap:
                raise ValueError('resumed bitmap differs from retained output')
            if not path.exists(): path.write_bytes(bitmap)
            accepted.append({**row, 'status': 'source-and-framing-pass', 'bitmap_sha256': art.sha(path),
                             'face_count': 1, 'face_pixels': round(float(min(detected[0][2:4])), 1)})
        print(json.dumps({'season': season, 'fetched': min(start+16,len(candidates)), 'accepted': len(accepted)}), flush=True)
    no_photo, included = [], []
    old_plan = ROOT / '.local/season-visual-patches-v2' / season / 'plan.json'
    old_patch = old_plan.parent / 'patch'
    if old_plan.is_file():
        old = json.loads(old_plan.read_text()); old_receipt = json.loads((old_patch / 'receipt.json').read_text())
        if old['inputs']['release_id'] == release.release_id:
            if old_receipt['plan_sha256'] != art.sha(old_plan) or old_receipt['archive_before_sha256'] != art.sha(release.game_path / 'DBDAT/MINIFOTO.PKF'):
                raise ValueError('old no-photo cleanup is stale')
            photos = {int(r['carrier_id']) for r in accepted}
            no_photo = [r for r in old['no_photo'] if int(r['carrier_id']) not in photos]
            path = output / 'patch/DBDAT/MINIFOTO.PKF'
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old_patch / 'DBDAT/MINIFOTO.PKF', path)
            included = [art.sha(old_plan)]
    plan = {'schema_version': art.SCHEMA, 'season': season,
            'inputs': {'release_id': release.release_id, 'package_sha256': art.sha(release.package_path),
                       'identity_catalogue_sha256': art.sha(source_path)},
            'no_photo': no_photo, 'replacements': [], 'included_visual_patch_plan_sha256s': included}
    art.save(output / 'plan.json', plan)
    receipt = {'schema_version': 'pm99-season-visual-patch-materialisation-v1', 'season': season,
               'plan_sha256': art.sha(output / 'plan.json'), 'archive_before_sha256': art.sha(release.game_path / 'DBDAT/MINIFOTO.PKF'),
               'outputs': {str(p.relative_to(output / 'patch')): art.sha(p) for p in sorted((output / 'patch').rglob('*')) if p.is_file()},
               'replacements': accepted, 'rejected': rejected, 'no_photo_count': len(no_photo),
               'coverage': {'candidate_count': len(candidates), 'accepted': len(accepted),
                            'foreign_clubs_with_new_photos': len({r['target_club'] for r in accepted})},
               'scope': 'bounded expansion, not full worldwide coverage or independent facial identity certification'}
    art.save(output / 'patch/receipt.json', receipt)
    return receipt['coverage']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--season', default='all')
    parser.add_argument('--maximum-per-season', type=int, default=200)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    model = ROOT / '.local/season-historical-photo-pilots-v1/shared/face_detection_yunet_2023mar.onnx'
    detector = cv2.FaceDetectorYN_create(str(model), '', (320,320), score_threshold=.8)
    source, editions, identities = source_index()
    for season in registry.supported_seasons():
        if int(season[:4]) < 2009 or season in ('2014-15','2015-16') or args.season not in ('all',season): continue
        output = args.output_root / season
        receipt = output / 'patch/receipt.json'
        if receipt.exists(): coverage = json.loads(receipt.read_text())['coverage']
        else: coverage = prepare(season, output, source, editions, identities, detector, args.maximum_per_season)
        if args.install:
            current = registry.load_preferred_release(season)
            release_id = 'visual-foreign-portraits-20261003-r8'
            if current.release_id != release_id:
                transaction.install(output / 'plan.json', output / 'patch',
                    ROOT / '.local/season-art-transactions-v1/foreign-r8' / season, release_id)
        print(json.dumps({'season': season, **coverage}), flush=True)
