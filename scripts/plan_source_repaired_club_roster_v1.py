#!/usr/bin/env python3
"""Plan a wrongly selected opening XI as one club transaction, not reserve swaps.

Bind the independently corrected original report, identify every actual XI and
bench person, preserve existing genuine club players, and expose other-club
copies that must be reconciled before a duplicate-clean publication.
"""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_person_identity_v1 as person_source
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def unique_people_by_id(people):
    rows = collections.defaultdict(dict)
    for entries in people.values():
        for id, person in entries.items():
            rows[id][json.dumps(person, sort_keys=True)] = person
    return {id: next(iter(variants.values())) for id, variants in rows.items() if len(variants) == 1}


def local_dob_conflicts(players, club_id, desired_ids, by_id, excluded_ids):
    """Expose exact full-name date conflicts, never silently join through DOB.

    This is a club-transaction review queue, not a relaxation of the global
    full-name/DOB person join. Original opponent XI slots are excluded. A
    surname/display abbreviation or two existing same-name players cannot
    establish which record needs a correction.
    """
    result = {}
    desired_by_name = collections.defaultdict(list)
    for id in desired_ids:
        person = by_id.get(id)
        if person:
            desired_by_name[transfer._normalise(person['name'])].append(person)
    local_by_name = collections.defaultdict(list)
    for player in players.values():
        name = player.get('source_name')
        if player['club_id'] == club_id and player['id'] not in excluded_ids and isinstance(name, str):
            local_by_name[transfer._normalise(name)].append(player)
    for name, persons in desired_by_name.items():
        local = local_by_name.get(name, [])
        if len(persons) != 1 or len(local) != 1:
            continue
        player, person = local[0], persons[0]
        before, after = player['facts'].get('birth_date'), person['birth_date']
        if not isinstance(before, str) or before == after:
            continue
        dt.date.fromisoformat(before)
        dt.date.fromisoformat(after)
        result[person['source_player_id']] = {'player_id': player['id'],
            'carrier_id': player['carrier_id'], 'source_name': player['source_name'],
            'source_player_id': person['source_player_id'], 'before': before, 'after': after,
            'status': 'exact-full-name-local-DOB-conflict-needs-explicit-fact-correction',
            'approved_for_native_write': False}
    return result


def run(season, carrier, release_id, review_path, person_path, roster_review_path, output):
    if output.exists():
        raise ValueError('club reconciliation plan is immutable')
    release = registry.load_registered_release(season, release_id)
    layers = planner.package_layers(release)
    clubs = {c['id']: c for _, v, _ in layers for c in v['clubs']}
    players = {p['id']: p for _, v, _ in layers for p in v['players']}
    selected = [c for c in clubs.values() if c['carrier_id'] == carrier]
    if len(selected) != 1:
        raise ValueError('club reconciliation requires one exact native carrier')
    club = selected[0]
    doc = json.loads(review_path.read_text())
    transfer.verify_opening_sources(doc)
    row = next(r for r in doc['clubs'] if r['carrier_id'] == carrier)
    if row['club'] != club['name'] or row['status'] != 'original-first-fixture-reparsed':
        raise ValueError('corrected original opening source does not match the exact club')
    original = [r for r in doc['wrong_side_source_replay']['corrected'] if r['carrier_id'] == carrier]
    if len(original) != 1:
        raise ValueError('club transaction requires its explicit original wrong-side correction')
    source_repair_path = ROOT / original[0]['repair_path']
    correction = json.loads(source_repair_path.read_text())
    if correction['carrier_id'] != carrier or correction['club'] != club['name']:
        raise ValueError('wrong source correction club')
    people, _, _, pin = transfer.load_snapshot(
        ROOT / '.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb',
        ROOT / '.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json')
    people, refusal = person_source.merge(people, json.loads(person_path.read_text()))
    by_id = unique_people_by_id(people)
    evidence = row['evidence']
    desired_ids = set(map(int, evidence['starting_xi'])) | set(map(int, evidence['substitutes']))
    missing_identities = sorted(desired_ids - set(by_id))
    existing, outside = collections.defaultdict(list), collections.defaultdict(list)
    for player in players.values():
        person = transfer.unique_person(player, people)
        if person is None or person['source_player_id'] not in desired_ids:
            continue
        target = existing if player['club_id'] == club['id'] else outside
        target[person['source_player_id']].append(player['id'])
    old_xi = club.get('opening', {}).get('starting_xi_player_ids', [])
    old_person_ids = [transfer.unique_person(players[id], people) for id in old_xi]
    old_ids = {p['source_player_id'] for p in old_person_ids if p is not None}
    declared_wrong = {int(p['source_player_id']) for p in correction['before']['starting_xi']}
    if len(old_xi) != 11 or len(old_ids) != 11 or old_ids != declared_wrong or old_ids & desired_ids:
        raise ValueError('native recipe is not exactly the rejected opponent XI; no broad replacement authorised')
    dob_conflicts = local_dob_conflicts(players, club['id'], desired_ids, by_id, set(old_xi))
    raw_sources, bindings = roster.load_sources(season)
    verifier = roster.SourceVerifier(season, json.loads(roster_review_path.read_text()), bindings)
    facts = collections.defaultdict(list)
    for raw in raw_sources:
        candidates = [(p, transfer.unique_person({'name': p['name'], 'facts': p}, people)) for p in raw['players']]
        candidates = [(p, person) for p, person in candidates if person and person['source_player_id'] in desired_ids]
        if not candidates:
            continue
        proof = verifier.verify(raw)
        if proof['status'] != 'raw-source-reparsed':
            continue
        for p, person in candidates:
            facts[person['source_player_id']].append({'source_player': p, 'source_person': person,
                'original_squad_club': raw['club_name'], 'raw_evidence': proof,
                'scope': 'secondary player facts only; opening ownership comes from exact original match report'})
    desired = []
    for id in sorted(desired_ids):
        alternatives = facts[id]
        preferred = [f for f in alternatives if roster.normalise(f['original_squad_club']) in
                     roster.club_names(roster.club_group(club), club['name'], club.get('full_name', ''))]
        chosen = preferred or alternatives
        roles = {f['source_player'].get('position') for f in chosen}
        desired.append({'source_player_id': id, 'source_person': by_id.get(id),
            'matchday_role': 'starter' if str(id) in evidence['starting_xi'] else 'substitute',
            'existing_club_player_ids': existing[id], 'other_club_player_ids': outside[id],
            'historical_fact_sources': chosen, 'source_broad_position_unambiguous': len(roles) == 1,
            'requires_new_club_slot': not existing[id],
            'pending_existing_player_DOB_correction': dob_conflicts.get(id)})
    new = [r for r in desired if r['requires_new_club_slot']]
    result = {'schema_version': 'pm99-source-repaired-opening-club-roster-plan-v1',
        'season': season, 'release_id': release_id, 'club_id': club['id'], 'carrier_id': carrier,
        'club': club['name'], 'formation': correction['after']['formation'], 'manager': correction['after']['declared_manager'],
        'bindings': {'package_sha256': registry.sha256_file(release.package_path),
            'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
            'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            'source_review_path': registry.relative_workspace_path(review_path), 'source_review_sha256': registry.sha256_file(review_path),
            'source_correction_path': registry.relative_workspace_path(source_repair_path), 'source_correction_sha256': registry.sha256_file(source_repair_path),
            'person_input_path': registry.relative_workspace_path(person_path), 'person_input_sha256': registry.sha256_file(person_path),
            'snapshot': pin, 'historical_captures': bindings},
        'original_wrong_xi_player_ids': old_xi, 'desired_matchday_people': desired,
        'local_DOB_conflicts': list(dob_conflicts.values()),
        'summary': {'wrong_xi_slots': len(old_xi), 'new_matchday_people': len(new),
            'already_present_matchday_people': len(desired) - len(new),
            'missing_identity_ids': missing_identities,
            'missing_fact_ids': [r['source_player_id'] for r in new if not r['historical_fact_sources']],
            'ambiguous_position_ids': [r['source_player_id'] for r in new if not r['source_broad_position_unambiguous']],
            'pending_existing_player_DOB_corrections': len(dob_conflicts),
            'new_slots_after_explicit_DOB_corrections': len(new) - len(dob_conflicts),
            'other_club_copy_count': sum(len(r['other_club_player_ids']) for r in new)},
        'source_identity_refusals': refusal['refused'], 'native_installation_ready': False,
        'remaining_work': ['Reconcile every other-club copy before claiming a duplicate-clean result.',
            'Resolve explicit local DOB conflicts without adding second copies of existing club players.',
            'Assign the actual sourced people to capacity-fitting native slots and independently verify name fit.',
            'Reorder the actual XI, rebuild only this club contextual tactics, remove displaced portraits, and runner-check it.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(output, result)
    print(json.dumps(result['summary']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--carrier', type=int, required=True)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--opening-review', type=Path, required=True)
    parser.add_argument('--person-input', type=Path, required=True)
    parser.add_argument('--roster-review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.season, args.carrier, args.release_id, args.opening_review,
        args.person_input, args.roster_review, args.output)
