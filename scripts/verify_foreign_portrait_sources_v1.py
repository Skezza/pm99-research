#!/usr/bin/env python3
"""Check installed foreign photos against source bytes and dated FIFA identities.

This deliberately does NOT label source/receipt agreement as independent facial
identity certification. Face detection is a framing check, not recognition.
Existing all-season roster audits are reused; no release or game is modified.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import audit_registered_visual_assets_v1 as audit
from scripts.season_portrait_pipeline_v1 import _name_score, _normalise_name
from scripts.materialise_2015_world_portraits import _url_bound_to_id
from scripts.season_historical_photo_qa_v1 import decode
from scripts import season_portrait_pipeline_v1 as portraits
from scripts import season_pipeline_v2 as pipeline


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    import cv2
    cv2.setNumThreads(1)
    directory = ROOT / '.local/visual-qa-20261003'
    output = directory / 'foreign-source-verification'
    output.mkdir(exist_ok=True)
    csv_path = ROOT / '.local/external-sources/sofifa-fifa16/male_players_legacy.csv'
    edition = {}
    with csv_path.open() as stream:
        for row in csv.DictReader(stream):
            if row['fifa_version'] == '16':
                edition.setdefault(int(row['player_id']), row)
    source_rows = defaultdict(list)
    materialisations = sorted((ROOT / '.local/season-pipeline-v2').glob('*portrait-materialisation*.json'))
    for path in materialisations:
        doc = json.loads(path.read_text())
        for row in doc.get('rows', []):
            if row.get('status') == 'approved-crop-conversion-candidate':
                source_rows[(_normalise_name(row['name']),
                             row.get('converted_sha256'))].append((path, row))
    release = audit.registry.load_preferred_release('2015-16')
    package = json.loads(release.package_path.read_text())
    players = {int(p['carrier_id']): p for p in package['players']}
    detector_path = ROOT / '.local/season-historical-photo-pilots-v1/shared/face_detection_yunet_2023mar.onnx'
    detector = cv2.FaceDetectorYN_create(str(detector_path), '', (320, 320), score_threshold=.75)
    native_jug = (directory / 'native-source/JUG98030.FDI').read_bytes()
    native_entries = {int(e.record_id): e for e in audit.IndexedFDIFile.from_bytes(native_jug).entries}
    rows, cache, inherited = [], {}, []
    all_counts = []
    for path in sorted(directory.glob('????-??/player-photo-audit.json')):
        doc = json.loads(path.read_text())
        foreign = [r for r in doc['players'] if r['group'] == 'foreign-club']
        all_counts.append({'season': doc['season'], 'players': len(foreign),
                           'statuses': dict(Counter(r['physical_status'] for r in foreign))})
        for player in foreign:
            if player['physical_status'] == 'stock-carrier-photo':
                entry = native_entries.get(player['carrier_id'])
                original_name = (audit._player_name(entry.decode_payload(native_jug),
                                                   record_id=player['carrier_id']) if entry else None)
                inherited.append({'season': doc['season'], 'carrier_id': player['carrier_id'],
                                  'current_name': player['name'], 'native_photo_player_name': original_name,
                                  'result': 'native-photo-identity-needs-review'})
        if doc['season'] != '2015-16':
            continue
        for row in foreign:
            if row['physical_status'] != 'source-bound-photo':
                continue
            issues = []
            candidates = source_rows.get((_normalise_name(row['source_player_name']),
                                          row['bitmap_sha256']), [])
            result = {'carrier_id': row['carrier_id'], 'name': row['source_player_name'],
                      'installed_bitmap_sha256': row['bitmap_sha256'], 'issues': issues,
                      'independent_facial_identity': 'not-certified'}
            if not candidates:
                issues.append('no-original-materialisation-matching-name-and-installed-bitmap')
            else:
                materialisation, source = candidates[0]
                if len({r['fifa16_player_id'] for _, r in candidates}) != 1:
                    issues.append('same-name-and-bitmap-bound-to-multiple-source-player-ids')
                source_id = int(source['fifa16_player_id'])
                person = edition.get(source_id)
                result.update({'fifa_id': source_id, 'source_url': source.get('download_url'),
                               'materialisation': str(materialisation), 'source_sha256': source['source_sha256']})
                if not _url_bound_to_id(source.get('download_url', ''), source_id):
                    issues.append('source-url-player-id-mismatch')
                if person is None:
                    issues.append('player-id-not-in-dated-edition')
                else:
                    score, method = _name_score(result['name'], person['short_name'], person['long_name'])
                    result.update({'dated_source_name': person['long_name'], 'name_score': score,
                                   'name_match': method, 'source_date': person['fifa_update_date'],
                                   'source_birth_date': person['dob']})
                    if score < 85:
                        issues.append('source-name-needs-independent-review')
                    target_dob = players.get(row['carrier_id'], {}).get('facts', {}).get('birth_date')
                    result['recipe_birth_date'] = target_dob
                    if target_dob != person['dob']:
                        issues.append('recipe-and-source-birth-date-disagree-or-missing')
                source_path = Path(source['cache_path'])
                if not source_path.is_file():
                    issues.append('source-image-cache-missing')
                else:
                    key = source['source_sha256']
                    if key not in cache:
                        check = {'source_hash_matches': sha(source_path) == key}
                        try:
                            photo = decode(source_path.read_bytes())
                            detector.setInputSize((photo.shape[1], photo.shape[0]))
                            _, faces = detector.detect(photo)
                            check['face_count'] = 0 if faces is None else len(faces)
                            check['largest_face_pixels'] = 0 if faces is None else round(float(max(min(f[2], f[3]) for f in faces)), 1)
                        except (ValueError, OSError, cv2.error) as exc:
                            check['decode_error'] = str(exc)
                        cache[key] = check
                    result.update(cache[key])
                    if not result['source_hash_matches']:
                        issues.append('cached-source-image-hash-mismatch')
                    if result.get('face_count') != 1:
                        issues.append('source-does-not-have-one-detectable-face')
            result['result'] = 'needs-review' if issues else 'source-identity-and-framing-checks-pass'
            rows.append(result)
            if len(rows) % 250 == 0:
                print(json.dumps({'checked': len(rows), 'needs_review': sum(bool(r['issues']) for r in rows)}), flush=True)
    bitmap_ids = defaultdict(set)
    for row in rows:
        if 'fifa_id' in row:
            bitmap_ids[row['installed_bitmap_sha256']].add(row['fifa_id'])
    for row in rows:
        if len(bitmap_ids[row['installed_bitmap_sha256']]) > 1:
            row['issues'].append('identical-installed-bitmap-used-for-different-source-player-ids')
            row['result'] = 'needs-review'
    summary = {'schema_version': 'pm99-foreign-portrait-source-verification-v1',
               'all_season_foreign_coverage': all_counts, 'installed_2015_foreign_photos_checked': len(rows),
               'results': dict(Counter(r['result'] for r in rows)),
               'issues': dict(Counter(issue for r in rows for issue in r['issues'])),
               'dated_csv_sha256': sha(csv_path), 'face_detector_sha256': sha(detector_path),
               'inherited_nonmanaged_portraits': inherited,
               'scope': 'Source identity facts, cache bytes and source framing; NOT independent visual identification of every face.',
               'players': rows}
    (output / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    with (output / 'review-queue.csv').open('w') as stream:
        fields = ['carrier_id', 'name', 'fifa_id', 'dated_source_name', 'recipe_birth_date',
                  'source_birth_date', 'face_count', 'issues']
        writer = csv.DictWriter(stream, fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            if row['issues']:
                writer.writerow({**row, 'issues': '|'.join(row['issues'])})
    print(json.dumps({k: summary[k] for k in ('installed_2015_foreign_photos_checked', 'results', 'issues')}))


def english_identity_issues(player, receipt, edition_person, manual, official_person=None):
    """Missing secondary facts are warnings; wrong/undated faces are not."""
    issues, warnings = [], []
    if _name_score(player['name'], receipt['player'], receipt['player'])[0] < 85:
        issues.append('recipe-and-original-portrait-player-disagree')
    provider = receipt.get('portrait_source', '')
    edition_match = re.fullmatch(r'fifa(\d+)', provider)
    if edition_match:
        edition = int(edition_match[1])
        if receipt.get('portrait_player_id') is None:
            issues.append('portrait-id-not-declared-in-original-receipt')
            if abs(edition - 16) > 2:
                issues.append('portrait-edition-outside-two-year-era-window')
            return issues, warnings
        source_id = int(receipt['portrait_player_id'])
        # Exact edition in the URL is necessary; an ID alone is insufficient.
        url = receipt.get('source_url', '')
        direct = f'/fifa{edition}/img/players/{source_id}.png'
        sofifa = f'/players/{source_id // 1000}/{source_id % 1000:03d}/{edition}_120.png'
        if not (url.endswith(direct) or url.endswith(sofifa)):
            issues.append('image-url-not-bound-to-declared-edition-and-id')
        if abs(edition - 16) > 2:
            issues.append('portrait-edition-outside-two-year-era-window')
        official_names = [] if not official_person else [official_person.get('c') or '',
            ' '.join(str(official_person.get(k) or '') for k in ('f', 'l')).strip()]
        official_match = any(_name_score(player['name'], n, n)[0] >= 85 for n in official_names if n)
        if edition_person is None and not official_match:
            issues.append('portrait-id-absent-from-captured-edition')
        elif edition_person is not None:
            name_match = _name_score(player['name'], edition_person['short_name'], edition_person['long_name'])[0] >= 85
            if not name_match and not official_match:
                issues.append('dated-source-person-does-not-match-recipe')
            dob = player.get('facts', {}).get('birth_date')
            if not isinstance(dob, str):
                warnings.append('recipe-birthday-missing-not-an-identity-veto')
            elif dob != edition_person['dob']:
                # Strong, explicitly labelled official identity can preserve a
                # correct face while a secondary-data conflict stays logged.
                (warnings if official_match else issues).append('source-and-recipe-birthday-conflict-needs-corroboration')
    else:
        if not manual or manual.get('source_url') != receipt.get('source_url') or _name_score(
            player['name'], manual.get('player', ''), manual.get('player', ''))[0] < 85:
            issues.append('manual-photo-provenance-not-bound')
        else:
            # A current profile/career date is NOT a photograph date. Accept
            # only an explicitly recorded year on the photograph itself.
            note = manual.get('temporal_note', '')
            year = re.search(r'\b(20\d{2})\s+(?:player\s+)?photograph\b', note, re.I)
            if not year or not 2013 <= int(year[1]) <= 2017:
                issues.append('manual-photo-era-not-corroborated')
    return issues, warnings


def review_english(output, allow_network=False):
    """Audit the original English source join against the CURRENT release.

    Does not edit recipes or overwrite the old foreign audit. Optional network
    work recovers only edition-bound missing references, not modern substitutes.
    Newly hashing an old source is labelled honestly, not claimed as a historic
    download hash. Original converted bytes are independently retained.
    """
    import cv2
    cv2.setNumThreads(1)
    release = audit.registry.load_preferred_release('2015-16')
    package = json.loads(release.package_path.read_text())
    players = {int(p['carrier_id']): p for p in package['players']}
    # The 2015 migration package deliberately contains only mode-1 clubs.
    # The English ingress is a separate, registered compiler stage. Validate
    # its live roster and parser-backed identity rather than guessing a join
    # to a foreign player with the same carrier number.
    from app.models import PlayerRecord
    from datetime import date
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    jug_entries = {int(e.record_id): e for e in audit.IndexedFDIFile.from_bytes(jug).entries}
    owners, _, modes = audit._source_roster_owners((release.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    for carrier, owner_ids in owners.items():
        if any(modes.get(c) == 0 for c in owner_ids):
            entry = jug_entries[carrier]
            raw = entry.decode_payload(jug)
            parsed = PlayerRecord.from_bytes(raw, 0)
            try:
                dob = date(parsed.birth_year, parsed.birth_month, parsed.birth_day).isoformat()
            except ValueError:
                dob = None
            players[carrier] = {'name': audit._player_name(raw, record_id=carrier),
                                'facts': {'birth_date': dob}, 'english_roster_bound': True}
    original_root = ROOT / '.local/season-2015-16/english92-2015-16-build36-native-no-photo'
    receipt_path = original_root / 'face-stage-receipt.json'
    receipt = json.loads(receipt_path.read_text())
    manual_path = ROOT / 'docs/ENGLISH92_2015_16_MANUAL_FACE_SOURCES.json'
    manual_doc = json.loads(manual_path.read_text())
    manual_rows = {( _normalise_name(r['club']), _normalise_name(r['player'])): r for r in manual_doc['rows']}
    official_path = ROOT / '.local/season-2015-16/fifa16-ea-player-meta.json'
    official_players = {int(r['id']): r for r in json.loads(official_path.read_text())['players']}
    editions, inputs = {}, {}
    for edition in (15, 16, 17, 18, 19):
        if edition == 16:
            path = ROOT / '.local/external-sources/sofifa-fifa16/male_players_legacy.csv'
            with path.open() as stream:
                rows = [dict(r, sofifa_id=r['player_id']) for r in csv.DictReader(stream) if r['fifa_version'] == '16']
        else:
            path = ROOT / f'.local/season-2015-16/fifa{edition}-sofifa-backfill.csv'
            rows, _ = portraits._load_edition_rows(path)
        editions[edition] = {int(r['sofifa_id']): r for r in rows}
        inputs[str(path.relative_to(ROOT))] = sha(path)
    expected = {r.player_record_id: hashlib.sha256(r.raw_bitmap).hexdigest()
                for r in audit.iter_minifoto_records(original_root / 'game/DBDAT/MINIFOTO.PKF')}
    installed = {r.player_record_id: r.raw_bitmap for r in audit.iter_minifoto_records(release.game_path / 'DBDAT/MINIFOTO.PKF')}
    detector_path = ROOT / '.local/season-historical-photo-pilots-v1/shared/face_detection_yunet_2023mar.onnx'
    detector = cv2.FaceDetectorYN_create(str(detector_path), '', (320, 320), score_threshold=.75)
    references = {}
    def reference(original):
        source = Path(original.get('source_image_path') or '')
        if source.is_file():
            return source, original.get('source_url'), 'original-receipt-path'
        url = original.get('source_url', '')
        match = re.search(r'/fifa(\d+)/img/players/(\d+)\.png$|/players/(\d+)/(\d{3})/(\d+)_120\.png$', url)
        if match:
            edition = int(match[1] or match[5])
            if abs(edition - 16) > 2:
                return None, url, 'out-of-era-reference-not-downloaded'
            identity = int(match[2]) if match[2] else int(match[3]) * 1000 + int(match[4])
            mirror = f'https://cdn.sofifa.net/players/{identity // 1000}/{identity % 1000:03d}/{edition}_120.png'
            for candidate in (url, mirror):
                meta_path, payload_path = portraits._cache_paths(portraits.DEFAULT_CACHE, candidate)
                if meta_path.is_file() and payload_path.is_file():
                    meta = json.loads(meta_path.read_text())
                    if meta.get('url') == candidate and meta.get('source_sha256') == sha(payload_path):
                        return payload_path, candidate, 'retained-shared-source-cache'
            if allow_network:
                fetched = portraits._fetch({'status': 'era-source-candidate', 'source_image_url': mirror},
                    cache_root=portraits.DEFAULT_CACHE, timeout=12)
                if fetched.get('fetch_status'):
                    return portraits._cache_paths(portraits.DEFAULT_CACHE, mirror)[1], mirror, 'reacquired-era-bound-reference-not-original-download-hash'
        return None, url, 'unavailable-old-source-path'
    # Fetch/reuse source references once, independently of the face detector.
    # Four bounded workers; no bulk game copies or modern-player search.
    from concurrent.futures import ThreadPoolExecutor
    active = [r for r in receipt['rows'] if r['status'] == 'applied']
    with ThreadPoolExecutor(max_workers=4) as pool:
        for original, found in zip(active, pool.map(reference, active)):
            references[int(original['record_id'])] = found
    rows = []
    for original in receipt['rows']:
        carrier = int(original['record_id'])
        player = players.get(carrier)
        if player is None or not player.get('english_roster_bound'):
            raise ValueError('original English portrait carrier is absent from current English rosters')
        loose = release.game_path / 'DBDAT/MINIFOTO' / f'J96{carrier:05d}.BMP'
        payload = loose.read_bytes() if loose.is_file() else installed.get(carrier)
        row = {'carrier_id': carrier, 'name': player['name'], 'club': original['club'],
               'source_url': original.get('source_url'), 'original_status': original['status'],
               'issues': [], 'warnings': [], 'physical_status': 'photo' if payload else 'no-photo'}
        if original['status'] != 'applied':
            if payload:
                row['issues'].append('declared-no-photo-but-visible-photo-exists')
        elif payload is None:
            row['warnings'].append('previously-applied-photo-is-now-blank')
        else:
            provider = original.get('portrait_source', '')
            effective = dict(original)
            url_match = re.search(r'/fifa(\d+)/img/players/\d+\.png$|/players/\d+/\d{3}/(\d+)_120\.png$', original.get('source_url', ''))
            if url_match:
                actual_provider = 'fifa' + (url_match[1] or url_match[2])
                if actual_provider != provider:
                    row['warnings'].append('legacy-provider-label-corrected-from-exact-image-url')
                    provider = actual_provider
                    effective['portrait_source'] = actual_provider
            match = re.fullmatch(r'fifa(\d+)', provider)
            source_id = original.get('portrait_player_id')
            person = editions.get(int(match[1]), {}).get(int(source_id)) if match and source_id is not None else None
            manual = manual_rows.get((_normalise_name(original['club']), _normalise_name(original['player'])))
            issues, warnings = english_identity_issues(player, effective, person, manual,
                official_players.get(int(source_id)) if match and int(match[1]) == 16 and source_id is not None else None)
            row['issues'].extend(issues)
            row['warnings'].extend(warnings)
            row.update(source_edition=provider, source_id=source_id,
                       dated_source_name=person.get('long_name') if person else None,
                       recipe_birth_date=player.get('facts', {}).get('birth_date'),
                       source_birth_date=person.get('dob') if person else None)
            digest = hashlib.sha256(payload).hexdigest()
            row['installed_bitmap_sha256'] = digest
            original_loose = original_root / 'game/DBDAT/MINIFOTO' / f'J96{carrier:05d}.BMP'
            original_digest = sha(original_loose) if original_loose.is_file() else expected.get(carrier)
            if digest != original_digest:
                row['issues'].append('installed-bitmap-differs-from-original-conversion')
            audit.validate_minifoto_bitmap(payload)
            source, used_url, reference_basis = references[carrier]
            row['reference_basis'] = reference_basis
            row['reference_url'] = used_url
            if source is None:
                row['warnings'].append('original-source-cache-unavailable-reference-still-needed')
            else:
                row.update(source_cache_path=str(source), source_sha256_checked_now=sha(source),
                           source_hash_basis='first-checkpoint-for-legacy-english-receipt')
                image = decode(source.read_bytes())
                detector.setInputSize((image.shape[1], image.shape[0]))
                _, detected = detector.detect(image)
                row['face_count'] = 0 if detected is None else len(detected)
                row['largest_face_pixels'] = 0 if detected is None else round(float(max(min(f[2], f[3]) for f in detected)), 1)
                if row['face_count'] != 1 or row['largest_face_pixels'] < 35:
                    row['issues'].append('source-face-framing-needs-review')
        row['result'] = 'needs-review' if row['issues'] else 'source-consistency-pass'
        rows.append(row)
        if len(rows) % 250 == 0:
            print(json.dumps({'english_checked': len(rows), 'needs_review': sum(bool(r['issues']) for r in rows)}), flush=True)
    report = {'schema_version': 'pm99-english-portrait-source-review-v1', 'season': '2015-16',
              'release_id': release.release_id, 'package_sha256': sha(release.package_path),
              'minifoto_sha256': sha(release.game_path / 'DBDAT/MINIFOTO.PKF'),
              'original_receipt_sha256': sha(receipt_path), 'manual_sources_sha256': sha(manual_path),
              'official_edition_metadata_sha256': sha(official_path),
              'edition_csv_sha256s': inputs, 'face_detector_sha256': sha(detector_path),
              'players_checked': len(rows), 'results': dict(Counter(r['result'] for r in rows)),
              'issues': dict(Counter(i for r in rows for i in r['issues'])),
              'warnings': dict(Counter(i for r in rows for i in r['warnings'])),
              'scope': 'Source identity, era and framing checks; NOT independent facial certification.', 'players': rows}
    output.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(output / 'english-source-review.json', report)
    print(json.dumps({k: report[k] for k in ('players_checked', 'results', 'issues', 'warnings')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--english', action='store_true', help='check all 2015 English portraits against the current release')
    parser.add_argument('--allow-network', action='store_true', help='reacquire only missing edition-bound English references')
    parser.add_argument('--output-root', type=Path, default=ROOT / '.local/visual-quality-v1/2015-16/portraits')
    args = parser.parse_args()
    if args.english:
        review_english(args.output_root, args.allow_network)
    else:
        run()
