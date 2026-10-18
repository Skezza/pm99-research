"""Reproduce all remaining36 manager source claims without touching games.

Twenty-eight new original tenures, four primary-source conflict resolutions,
and four Altrincham claims with independently proven distinct same-name peers.
Native/current-owner admission and actual delivery remain separate obligations.
"""
from datetime import date
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import audit_deferred_manager_tenures_20261016 as history
from scripts import capture_deferred_manager_originals_20261016 as fresh
from scripts import capture_sunderland_manager_history_20261016 as sunderland
from scripts import manager_primary_conflict_resolutions_20261016 as primary

ROOT = fresh.ROOT.parent
SCHEMA = 'pm99-remaining36-original-manager-source-package-v1'


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def fresh_claim(row):
    source = row['download']
    raw = registry.ROOT / source['raw_path']; receipt = registry.ROOT / source['receipt_path']
    if registry.sha256_file(raw) != source['raw_sha256'] or registry.sha256_file(receipt) != source['receipt_sha256']:
        raise ValueError('fresh source original or receipt changed')
    downloaded = pipeline.read_json_file(receipt)
    if downloaded['url'] != source['url'] or downloaded['sha256'] != source['raw_sha256']:
        raise ValueError('new original download receipt URL/hash mismatch')
    actual = history.tenure(raw.read_bytes(), row['source_club_id'], date(int(row['season'][:4]), 8, 1))
    if actual != row['claim']:
        raise ValueError('new original tenure claim no longer independently reparses')
    return actual, dict(path=source['raw_path'], sha256=source['raw_sha256'], url=source['url'])


def original_claim(case):
    all_claims = case['claims']; parsed = []; sources = []
    receipts = history.receipt_index()
    for claim in all_claims:
        raw = registry.ROOT / claim['path']
        if registry.sha256_file(raw) != claim['sha256']:
            raise ValueError('retained original raw tenure changed')
        actual = history.tenure(raw.read_bytes(), case['source_club_id'], date(int(case['season'][:4]), 8, 1))
        if any(actual[k] != claim[k] for k in ('manager', 'source_manager_id', 'source_url', 'date')):
            raise ValueError('retained original coach claim does not reproduce')
        parsed.append(actual)
        if claim['original_download_receipt_verified']:
            witnesses = receipts.get((case['source_club_id'], claim['sha256']), [])
            if not claim['download_receipts']:
                raise ValueError('retained history has no actual original download body')
            for item in claim['download_receipts']:
                if (registry.sha256_file(registry.ROOT / item['receipt_path']) != item['receipt_sha256']
                        or item not in witnesses or item['original_download_url'] != actual['source_url']):
                    raise ValueError('original history download body does not join URL/SHA')
            sources.append(dict(path=claim['path'], sha256=claim['sha256'], url=claim['source_url']))
    if len({(p['manager'], p['source_manager_id'], p['date']) for p in parsed}) != 1 or not sources:
        raise ValueError('original coach histories disagree or have no original download receipt')
    return parsed[0], sources


def same_name_peer(season):
    if season == '2020-21':
        document = pipeline.read_json_file(sunderland.ROOT / 'capture-result.json')
        raw = registry.ROOT / document['source']['path']
        receipt = registry.ROOT / document['receipt']['path']
        if (registry.sha256_file(raw) != document['source']['sha256']
                or registry.sha256_file(receipt) != document['receipt']['sha256']):
            raise ValueError('Sunderland original source changed')
        downloaded = pipeline.read_json_file(receipt)
        if downloaded['url'] != document['source']['url'] or downloaded['sha256'] != document['source']['sha256']:
            raise ValueError('Sunderland original download body changed')
        result = history.tenure(raw.read_bytes(), 289, date(2020, 8, 1))
        source = document['source']; club = 'Sunderland'; club_id = 289
    else:
        doc = pipeline.read_json_file(registry.ROOT / '.local/consolidated-audit-20261009/august-manager-tenures-v1/phil-parkinson-original-identities.json')
        rows = [r for r in doc['rows'] if r['season'] == season and r['club'] == 'Wrexham']
        if len(rows) != 1:
            raise ValueError('original exact Wrexham peer evidence missing')
        row = rows[0]; case = dict(season=season, source_club_id=row['source_club_id'],
            claims=row['original_tenure_inspection']['claims'])
        result, sources = original_claim(case)
        source = sources[0]; club = 'Wrexham'; club_id = row['source_club_id']
    if (result['manager'], result['source_manager_id']) != ('Phil Parkinson', '3540'):
        raise ValueError('same-name peer must be original coach3540, not Altrincham84629')
    return dict(club=club, source_club_id=club_id, **result, original_source=source,
        basis='distinct original numeric publisher identity despite identical full name')


def prepare():
    original_path = history.ROOT / 'deferred-tenure-source-audit-v2.json'
    original = pipeline.read_json_file(original_path)
    capture_path = fresh.ROOT / 'capture-summary.json'
    capture = pipeline.read_json_file(capture_path)
    if original['original_deferred'] != 85 or capture['original_cases'] != 32:
        raise ValueError('original85/remaining32 source denominators changed')
    rows = []
    for row in capture['rows']:
        if row['status'] != 'fresh-original-August1-tenure-reparsed':
            continue
        claim, source = fresh_claim(row)
        rows.append(dict(season=row['season'], club=row['club'], club_id=row['club_id'],
            source_club_id=row['source_club_id'], **claim, source_policy='new-original-numeric-club-August1-tenure',
            original_deferred_case=row['original_case'], raw_sources=[source],
            download_evidence=row['download'], same_name_peer=None, primary_resolution=None))
    primary_path = ROOT / 'primary-four-manager-resolutions.json'
    resolved = primary.resolve()
    if resolved != pipeline.read_json_file(primary_path):
        raise ValueError('ROOT primary-source conflict decisions no longer reproduce')
    for row in resolved['resolutions']:
        rows.append(dict(season=row['season'], club=row['club'], club_id=row['club_id'],
            source_club_id=row['source_club_id'], manager=row['manager'], source_manager_id=row['source_manager_id'],
            source_url=row['raw_history']['url'], date=row['date'], source_policy=row['policy'],
            original_deferred_case=row['original_unresolved_case']['original_case'],
            raw_sources=[row['raw_history']] + [dict(path=s['path'], sha256=s['sha256'], url=s['url']) for s in row['primary_authorities']],
            primary_resolution=row, same_name_peer=None))
    phils = [r for r in original['rows'] if r['club'] == 'Altrincham'
        and r['season'] in ('2020-21', '2023-24', '2024-25', '2025-26')]
    if len(phils) != 4:
        raise ValueError('four originally deferred Altrincham cases missing')
    for case in phils:
        claim, sources = original_claim(case); peer = same_name_peer(case['season'])
        if (claim['manager'], claim['source_manager_id']) != ('Phil Parkinson', '84629') or claim['source_manager_id'] == peer['source_manager_id']:
            raise ValueError('Altrincham and same-name peer are not independently distinct original people')
        rows.append(dict(season=case['season'], club=case['club'], club_id=case['club_id'],
            source_club_id=case['source_club_id'], **claim,
            source_policy='original-numeric-person-and-club-tenure-distinguishes-same-full-name',
            original_deferred_case=case, raw_sources=sources + [peer['original_source']],
            primary_resolution=None, same_name_peer=peer))
    keys = {(r['season'], r['club_id']) for r in rows}
    if len(rows) != 36 or len(keys) != 36:
        raise ValueError('all remaining36 distinct original source cases must be represented')
    return dict(schema=SCHEMA, claims=sorted(rows, key=lambda r: (r['season'], r['club_id'])),
        original_deferred=85, prior49_delivery_required=True, remaining_source_claims=36,
        source_classes=dict(original_fresh_tenures=28, primary_conflict_resolutions=4, distinct_same_name_people=4),
        source_bindings=[binding(p) for p in (original_path, capture_path, primary_path)],
        native_writes=0, recipe_writes=0, manager_cases_closed=0,
        note='Source package only. No global manager clearance; known unverified Aalesund2024 same-name fallback is not approved by Altrincham identity correction.')


if __name__ == '__main__':
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    result = prepare()
    retained(ROOT / 'remaining36-source-package.json', result)
    print(dict(original_deferred=85, remaining_source_claims=len(result['claims']), native_writes=0,
        manager_cases_closed=0, source_classes=result['source_classes']), flush=True)
