"""Independently validate eight already-delivered whole-club corrections.

Research recommendations are inputs, never authority: raw schedules, numeric
match sides, original biographies and actual current native owners are reread.
No game is rebuilt and no previously delivered identity correction is discarded.
"""
import copy
from datetime import UTC, datetime

from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.season_historical_roster_audit_v1 import normalise
from scripts.checkpoint_frozen_fixture_reserve_v1 import next_count
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009'
REPORT = ROOT / 'luna-closeout-20261017/single-match-eight-review.json'
REPORT_SHA = '2637df4898cb3408fe417528ef333cf6ca1873ce427e06023e94135d4f04afa6'


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def main(*, report_path=REPORT, report_sha=REPORT_SHA, expected_count=8,
         previous_path=ROOT / 'release-delivery-checklist-v108.json',
         output=ROOT / 'release-delivery-checklist-v109.json',
         proof_path=ROOT / 'luna-closeout-20261017/boreham-eight-current-dispositions.json',
         namesake_validator=None):
    if output.exists() or proof_path.exists():
        raise ValueError('completed reconciliation must not repeat')
    if registry.sha256_file(report_path) != report_sha:
        raise ValueError('review report changed; inspect before integration')
    report = pipeline.read_json_file(report_path)
    if len(report['cases']) != expected_count or len({c['case_id'] for c in report['cases']}) != expected_count:
        raise ValueError('exact bounded research batch required')
    previous = pipeline.read_json_file(previous_path)
    catalog = registry.load_catalog()
    for row in previous['current_release_bindings']:
        current = catalog[row['season']]
        if (current['release_id'], current['release_manifest_sha256']) != (row['release_id'], row['manifest_sha256']):
            raise ValueError('preferred games advanced during reconciliation')
    prior = next(c['delivery'] for c in previous['within_club_cases']
        if c.get('delivery', {}).get('release_id') == 'sourced-boreham-retained-opening-20261010-r64b')
    for evidence in prior['evidence']:
        if registry.sha256_file(registry.ROOT / evidence['path']) != evidence['sha256']:
            raise ValueError('previous delivered proof changed')
    for filename in ('boreham-triple-full-rebuild-proof-v1.json',
            'boreham-retained-opening-full-rebuild-proof-v1.json'):
        result = pipeline.read_json_file(ROOT / filename)
        if not result['complete_game_inventory_identical'] or not result['complete_recipe_identical']:
            raise ValueError('prior whole SOURCE proof incomplete')
    base = registry.load_preferred_release('2017-18')
    package = pipeline.read_json_file(base.package_path)
    actors = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    owners = ownership.native_owners((base.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    frozen_path = registry.ROOT / previous['cross_club_case_file']
    frozen = next(g['candidates'] for g in pipeline.read_json_file(frozen_path)['seasons']
        if g['season'] == '2017-18')
    cases = {pipeline.canonical_json_sha256(dict(season='2017-18', case=c)): c for c in frozen}
    cache = registry.ROOT / '.local/season-2017-18/soccerbase-august-cache-v1'
    raw_sources, source_clubs, dispositions = [], {}, []
    for candidate in report['cases']:
        case = cases[candidate['case_id']]
        retained_player = candidate['current_global_exact_match']
        replaced_player = candidate['current_recipe_other_slot']
        keep, replace = retained_player['carrier_id'], replaced_player['carrier_id']
        if {p['carrier_id'] for p in case['players']} != {keep, replace}:
            raise ValueError('reviewed pair is not the exact original frozen case')
        witness = candidate['retained_owner_positive_dated_source']
        team, person = witness['club_team_id'], witness['numeric_player_id']
        if team not in (364, 1660):
            raise ValueError('unexpected original retained club identity')
        if team not in source_clubs:
            raw, url = replay.read_original(cache, 'team', team, raw_sources)
            heading = BeautifulSoup(raw, 'lxml').select_one('h1').get_text(' ', strip=True)
            if not heading.endswith(' Results'):
                raise ValueError('original club schedule heading differs')
            fixture = original.first_fixture(raw, team, '2017-18', 'National League', heading[:-8], url)
            raw, url = replay.read_original(cache, 'match', fixture['game_id'], raw_sources)
            sheet = original.match(raw, fixture, team, url)
            if fixture['date'] != '2017-08-05':
                raise ValueError('original opening date differs')
            source_clubs[team] = fixture, sheet
        fixture, sheet = source_clubs[team]
        if fixture['game_id'] != witness['match_id']:
            raise ValueError('reviewed original fixture identity differs')
        starting = [p for p in sheet['starting_xi'] if p['provider_player_id'] == person]
        if len(starting) != 1:
            raise ValueError('retained original person not in positive first XI')
        raw, url = replay.read_original(cache, 'player', person, raw_sources)
        biography = original.profile(raw, starting[0], url)
        if (normalise(biography['name']), biography['birth_date']) != (
                normalise(retained_player['name']), retained_player['dob']):
            raise ValueError('original numeric biography does not match retained actor')
        native_rows = []
        for expected in (retained_player, replaced_player):
            carrier = expected['carrier_id']
            matches = [p for p in package['players'] if normalise(p.get('source_name') or p['name']) == normalise(expected['name'])]
            namesake_proof = None
            if len(matches)>1 and namesake_validator is not None:
                namesake_proof=namesake_validator(matches,expected,jug)
                matches=[p for p in matches if p['facts']['birth_date']==expected['dob']]
            if len(matches) != 1 or matches[0]['carrier_id'] != carrier:
                raise ValueError('identity still duplicated or moved to another slot')
            actor = actors[carrier]
            native = facts.native_facts(jug, carrier)
            club = clubs[actor['club_id']]
            if (actor['club_id'] != expected['club_id'] or actor['facts']['birth_date'] != expected['dob']
                    or native['birth_date'] != expected['dob']
                    or normalise(native['name']) != normalise(actor['name'])
                    or owners.get(carrier) != {club['carrier_id']}):
                raise ValueError('current actual native identity or exclusive owner differs')
            native_rows.append(dict(carrier_id=carrier, club=club['name'], native=native,
                **(dict(independent_namesake_proof=namesake_proof) if namesake_proof else {})))
        if clubs[actors[keep]['club_id']]['carrier_id'] != {364: 3304, 1660: 3326}[team]:
            raise ValueError('retained native club differs from independently dated owner')
        replacement_profile = registry.ROOT / replaced_player['raw_profile']
        if registry.sha256_file(replacement_profile) != replaced_player['raw_profile_sha256']:
            raise ValueError('replacement original biography changed')
        # Exact delivered full-club source plans and prior native/rebuild/runtime
        # proofs were already hash-bound above; now verify the current replacement.
        plan_path = base.package_path.parent / replaced_player['plan']
        plan = pipeline.read_json_file(plan_path)
        update = next(r for r in plan['updates'] if r['carrier_id'] == replace)
        if (update['replacement']['source_player']['name'], update['replacement']['source_player']['birth_date']) != (
                replaced_player['name'], replaced_player['dob']):
            raise ValueError('replacement not the exact previously delivered source allocation')
        dispositions.append(dict(case_id=candidate['case_id'], season='2017-18',
            state='confirmed-fault-repaired-current-game', retained_native_carrier=keep,
            replaced_native_carrier=replace, replacement=replaced_player['name'],
            retained_owner=clubs[actors[keep]['club_id']]['name'],
            original_retained_fixture=fixture, original_retained_biography=biography,
            current_native_readback=native_rows, existing_source_plan=binding(plan_path)))
    remaining = next_count(previous, dispositions)
    proof = dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        previous_checklist=binding(previous_path), research_report=binding(report_path),
        current_release_id=base.release_id, current_manifest_sha256=base.manifest_sha256,
        existing_delivery_evidence=prior['evidence'], original_retained_sources=raw_sources,
        dispositions=dispositions, native_writes=0, regenerated_seasons=0,
        reused_original_runtime=True, scope=f'{expected_count} duplicate ownership cases only; no global historical approval.')
    retained(proof_path, proof)
    result = copy.deepcopy(previous)
    result['cross_club_dispositions'].extend(dict(row, delivery=binding(proof_path)) for row in dispositions)
    result.update(utc=proof['utc'], previous_checklist=binding(previous_path),
        remaining_cross_club_cases=remaining, all_required_work_complete=False,
        fresh_runtime_runs_this_checklist=[], next_batch='Continue source-backed ownership corrections; Jimmy Dunne2017 wrong opening owner remains open.')
    result['delivered_evidence'].append(binding(proof_path))
    retained(output, result)
    print(dict(newly_reconciled_cases=expected_count, remaining_cross_club_cases=remaining,
        rebuilt_games=0, checklist=registry.relative_workspace_path(output)), flush=True)


if __name__ == '__main__':
    main()
