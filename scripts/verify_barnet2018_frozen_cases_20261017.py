"""Prove four exact frozen Hartlepool duplicates, leaving Josh Hill open."""
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_opening_order_repair_v1 as owners
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.season_historical_roster_audit_v1 import normalise
from scripts.publish_barnet2018_private_20261017 import ROOT, FOLDER, SEASON, RELEASE
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

PAIRS = ((159419, 10780, 11080), (42026, 10776, 11076),
         (45607, 10777, 11079), (58647, 10772, 11073))


def verify(*, root=ROOT, folder=FOLDER, season=SEASON, release_id=RELEASE, pairs=PAIRS,
           source_club=2577, expected_date='2018-08-04', retained_club=3300, replaced_club=3317,
           require_hill=True):
    ROOT,FOLDER,SEASON,RELEASE=root,folder,season,release_id
    output = FOLDER / 'independent-frozen-case-proof.json'
    if output.exists():
        raise ValueError('completed independent proof must not repeat')
    actual = registry.load_registered_release(SEASON, RELEASE)
    pair = pipeline.read_json_file(FOLDER / 'complete-singleton-source.json')
    proposal = pipeline.read_json_file(registry.ROOT / pair['proposals'][0]['path'])
    if registry.sha256_file(registry.ROOT / pair['proposals'][0]['path']) != pair['proposals'][0]['sha256']:
        raise ValueError('original complete source proposal changed')
    base = registry.load_registered_release(SEASON, proposal['release_id'])
    before, after = (pipeline.read_json_file(r.package_path) for r in (base, actual))
    old, new = ({p['carrier_id']: p for p in doc['players']} for doc in (before, after))
    frozen_path = ROOT / 'cross-club-identities-enriched.json'
    frozen = next(g['candidates'] for g in pipeline.read_json_file(frozen_path)['seasons'] if g['season'] == SEASON)
    capture_path = registry.ROOT / f'.local/transfermarkt-opening-plans-current-v1/{season}/opening-lineups.json'
    captures = pipeline.read_json_file(capture_path)
    selected = [c for c in captures['clubs'] if c['source_selector'].get('transfermarkt_club_id') == source_club]
    if len(selected) != 1:
        raise ValueError('retained Hartlepool opening source ambiguous')
    positive = opening.verify_opening(selected[0], captures, capture_path.parent / 'cache')
    if positive['date'] != expected_date or positive['source_club_id'] != source_club:
        raise ValueError('original retained opening date or numerical club differs')
    before_jug, after_jug = ((r.game_path / 'DBDAT/JUG98030.FDI').read_bytes() for r in (base, actual))
    before_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(before_jug).entries}
    after_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(after_jug).entries}
    ownership = owners.native_owners((actual.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    dispositions = []
    for person, keep, replace in pairs:
        cases = [c for c in frozen if c['identity'] == ['published-person', person]]
        if len(cases) != 1 or {p['carrier_id'] for p in cases[0]['players']} != {keep, replace}:
            raise ValueError('exact frozen two-carrier group differs')
        if str(person) not in positive['starting_xi']:
            raise ValueError('original first XI does not positively retain this actor')
        if old[keep] != new[keep] or new[keep]['club_id'] != 'club-'+str(retained_club):
            raise ValueError('retained original recipe actor changed')
        identity = (normalise(old[keep]['source_name']), old[keep]['facts']['birth_date'])
        matching = [p['carrier_id'] for p in after['players'] if (
            normalise(p.get('source_name') or p['name']), p['facts'].get('birth_date')) == identity]
        if matching != [keep]:
            raise ValueError('original player still globally duplicated or moved')
        if before_entries[keep].decode_payload(before_jug) != after_entries[keep].decode_payload(after_jug):
            raise ValueError('retained native record bytes changed')
        row = next(r for r in proposal['allocation'] if r['carrier_id'] == replace)
        desired = row['replacement']['source_player']
        if (new[replace]['source_name'], new[replace]['facts']['birth_date']) != (desired['name'], desired['birth_date']):
            raise ValueError('current replacement differs from complete original source allocation')
        for carrier, club in ((keep, retained_club), (replace, replaced_club)):
            native = facts.native_facts(after_jug, carrier)
            if (ownership.get(carrier) != {club} or native['birth_date'] != new[carrier]['facts']['birth_date']
                    or normalise(native['name']) != normalise(new[carrier]['name'])):
                raise ValueError('actual native actor identity or exclusive owner differs')
        dispositions.append(dict(case_id=pipeline.canonical_json_sha256(dict(season=SEASON, case=cases[0])),
            season=SEASON, state='confirmed-fault-repaired-current-game', source_person_id=person,
            retained_native_carrier=keep, retained_owner=next(c['name'] for c in after['clubs'] if c['carrier_id']==retained_club),
            replaced_native_carrier=replace, replacement=desired['name'],
            exact_retained_native_record_preserved=True, positive_original_first_XI=positive))
    remaining_hill = [p['carrier_id'] for p in after['players']
        if normalise(p.get('source_name') or p['name']) == 'joshhill']
    if require_hill and set(remaining_hill) != {11233, 11267}:
        raise ValueError('expected unresolved Josh Hill copies differ; do not hide them')
    retained(output, dict(season=SEASON, release_id=RELEASE, manifest_sha256=actual.manifest_sha256,
        confirmed_frozen_cases_repaired=len(pairs), dispositions=dispositions,
        original_retained_capture=dict(path=registry.relative_workspace_path(capture_path), sha256=registry.sha256_file(capture_path)),
        frozen_cases=dict(path=registry.relative_workspace_path(frozen_path), sha256=registry.sha256_file(frozen_path)),
        **(dict(remaining_Josh_Hill_carriers=remaining_hill,Josh_Hill_case_still_open=True) if require_hill else {}),
        preferred_publication_pending=True, native_writes=0))
    print(dict(exact_frozen_cases_repaired=len(pairs), unrelated_cases_closed=False, preferred_publication_pending=True), flush=True)


if __name__ == '__main__':
    verify()
