#!/usr/bin/env python3
"""Read-only replay of the narrow missing-matchday-positive duplicate queue.

This is feasibility evidence, not a native correction or a publication receipt.
The saved source-release and original input hashes are independently replayed.
"""
import argparse
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_dated_reserve_owner_v1 as reserve
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_opening_person_supplement_v1 as supplement
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_published_person_identity_v1 as persons
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def review(path, people, events, snapshot):
    plan = json.loads(path.read_text())
    if plan['bindings']['snapshot'] != snapshot:
        raise ValueError('reserve audit snapshot differs from saved proposal')
    release = registry.load_registered_release(plan['season'], plan['release_id'])
    if (registry.sha256_file(release.package_path),
            registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI')) != (
            plan['package_sha256'], plan['jug_sha256']):
        raise ValueError('reserve audit original source release changed')
    clubs, players = {}, {}
    for _, layer, _ in planner.package_layers(release):
        clubs.update({c['id']: c for c in layer['clubs']})
        players.update({p['id']: p for p in layer['players']})
    original = []
    bindings = plan['bindings']
    sources = [(bindings['opening_path'], bindings['opening_sha256'])]
    if bindings.get('supplemental_opening'):
        extra = bindings['supplemental_opening']
        sources.append((extra['path'], extra['sha256']))
    for source_path, expected_sha in sources:
        source_path = ROOT / source_path
        if registry.sha256_file(source_path) != expected_sha:
            raise ValueError('reserve audit original opening review changed')
        opening = json.loads(source_path.read_text())
        transfer.verify_opening_sources(opening)
        original.extend((row, opening) for row in opening['clubs'])
    carriers = {c['carrier_id']: c for c in clubs.values()}
    evidence = {}
    for row, doc in original:
        club = carriers.get(row['carrier_id'])
        if (club and club['name'] == row['club']
                and row['status'] == 'original-first-fixture-reparsed'):
            evidence[club['id']] = planner.source_evidence(row, doc)
    captures, actual_bindings = roster.load_sources(plan['season'])
    if actual_bindings != bindings['captures']:
        raise ValueError('reserve audit original capture bindings changed')
    previous_path = ROOT / bindings['review_path']
    if registry.sha256_file(previous_path) != bindings['review_sha256']:
        raise ValueError('reserve audit prior raw reparse evidence changed')
    verifier = roster.SourceVerifier(plan['season'], json.loads(previous_path.read_text()), actual_bindings)
    people, _ = supplement.extend(people, list(clubs.values()), evidence, captures, verifier)
    rows = []
    for problem in plan['unresolved']:
        if problem['reason'] != 'dated-owner-lacks-positive-opening-matchday-person-id':
            continue
        candidates = [players[p['player_id']] for p in problem['candidates']]
        person = transfer.unique_person(candidates[0], people)
        winner, basis, witness = reserve.decide(candidates, evidence, person,
            events.get(person['source_player_id'], []) if person else [],
            clubs, captures, verifier, people)
        rows.append({'identity': problem['identity'], 'candidates': problem['candidates'],
            'owner_player_id': winner['id'] if winner else None, 'decision': basis,
            'original_squad_witness': witness, 'native_correction': False})
    return {'season': plan['season'], 'source_release_id': plan['release_id'],
        'plan_path': registry.relative_workspace_path(path), 'plan_sha256': registry.sha256_file(path),
        'summary': {'reviewed': len(rows), 'source_supported_owners': sum(r['owner_player_id'] is not None for r in rows),
            'decisions': dict(collections.Counter(r['decision'] for r in rows))}, 'rows': rows}


def run(plan_root, person_path, history_path, output):
    if output.exists():
        raise ValueError('reserve ownership feasibility evidence is immutable')
    paths = sorted(plan_root.glob('*/ownership-plan.json'))
    if not paths:
        raise ValueError('no completed original ownership proposals')
    first = json.loads(paths[0].read_text())
    pin = first['bindings']['snapshot']
    people, events, _, actual = transfer.load_snapshot(ROOT / pin['path'], ROOT / pin['pinned_receipt_path'])
    if actual != pin:
        raise ValueError('reserve audit original snapshot binding changed')
    bindings = {'published_person_supplement': public.binding(person_path, persons.POLICY),
        'published_transfer_supplement': public.binding(history_path, histories.POLICY)}
    people, events, summary = public.merge_bound(people, events, bindings)
    rows = []
    for path in paths:
        result = review(path, people, events, pin)
        rows.append(result)
        print(json.dumps({'season': result['season'], **result['summary']}), flush=True)
    result = {'schema_version': 'pm99-dated-reserve-owner-feasibility-v1',
        'policy': reserve.POLICY, 'verification_scope': 'completed-proposals-present-at-start',
        'bindings': {'snapshot': pin, **bindings}, 'original_public_input_summary': summary,
        'seasons': rows, 'native_corrections': 0,
        'summary': {'seasons': len(rows), 'reviewed': sum(r['summary']['reviewed'] for r in rows),
            'source_supported_owners': sum(r['summary']['source_supported_owners'] for r in rows)}}
    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(output, result)
    print(json.dumps(result['summary']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-root', type=Path, required=True)
    parser.add_argument('--person-input', type=Path, required=True)
    parser.add_argument('--history-input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.plan_root, args.person_input, args.history_input, args.output)
