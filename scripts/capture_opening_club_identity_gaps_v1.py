#!/usr/bin/env python3
"""Extend publisher club discovery from independently replayed dated starters.

Only stable IDs in original transfer brackets are queried. Contemporary names
are discovery, never historical squad or ownership approval. No game writes.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import capture_original_public_club_entities_v1 as capture
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_english_result_date_binding_v1 as entities
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def run(plan_path, season, targets, output):
    if (output / 'source-plan.json').exists():
        raise ValueError('completed club discovery extension is immutable')
    plan = json.loads(plan_path.read_text())
    bindings = plan['bindings']
    pin = bindings['snapshot']
    people, events, actual = context.load_snapshot(ROOT / pin['path'], ROOT / pin['pinned_receipt_path'])
    if actual != pin:
        raise ValueError('original person/history pin changed')
    people, events, _ = whole.public.merge_bound(people, events, bindings)
    old_binding = bindings['soccerbase_opening_sources']['club_entities']
    old_path = ROOT / old_binding['path']
    if registry.sha256_file(old_path) != old_binding['sha256']:
        raise ValueError('bound original club entity book changed')
    known = entities.read_entities(old_path)
    originals, _ = whole.roster.load_sources(season)
    witnesses = []
    ids = set()
    for target in targets:
        selected = [c for c in originals if c['source_path'].startswith('soccerbase/team/')
                    and whole.club_keys(target) & whole.club_keys(c['club_name'])]
        if len(selected) != 1:
            raise ValueError('target needs one independently replayable first fixture')
        opening = whole.replay.replay_club(season, selected[0], people, True)
        for person in opening['identity_bridges']['starting_xi']:
            identity = person['transfermarkt_person']
            if identity is None:
                continue
            bracket = whole.transfer.transfer_interval(
                events.get(identity['source_player_id'], []), opening['fixture']['date'])
            if bracket['status'] != 'recorded-entry-and-exit-bracket-fixture':
                continue
            id = bracket['source_owner_club_id']
            if id not in known:
                ids.add(id)
                witnesses.append({'club': target, 'source_player_id': identity['source_player_id'],
                    'fixture': opening['fixture'], 'original_capture': opening['source_capture'],
                    'bracket': bracket})
    if not ids:
        raise ValueError('no missing club identities in original dated starter brackets')
    output.mkdir(parents=True, exist_ok=True)
    discovery_path = output / 'query-discovery.json'
    discovery = {'schema_version': 'pm99-original-history-club-query-discovery-v1',
        'query_club_ids': sorted(ids), 'witnesses': witnesses,
        'source_plan': {'path': registry.relative_workspace_path(plan_path),
                        'sha256': registry.sha256_file(plan_path)},
        'native_writes': 0, 'historical_ownership_approved': False}
    if discovery_path.exists() and json.loads(discovery_path.read_text()) != discovery:
        raise ValueError('saved missing-club query no longer replays')
    if not discovery_path.exists():
        pipeline.write_canonical_json(discovery_path, discovery)
    additional_path = output / 'additional-entities.json'
    if additional_path.exists():
        entities.read_entities(additional_path)
        additional = json.loads(additional_path.read_text())
        if additional['discovery']['sha256'] != registry.sha256_file(discovery_path):
            raise ValueError('saved additional club capture has different discovery')
    else:
        additional = capture.run(discovery_path, output / 'raw', additional_path)
    merged = copy.deepcopy(json.loads(old_path.read_text()))
    merged['batches'].extend(additional['batches'])
    merged['source_extension'] = {'previous': old_binding,
        'additional': {'path': registry.relative_workspace_path(additional_path),
                       'sha256': registry.sha256_file(additional_path)},
        'policy': 'original-dated-XI-bracket-club-discovery-only-v1', 'native_writes': 0}
    merged_path = output / 'club-entities.json'
    pipeline.write_canonical_json(merged_path, merged)
    entities.read_entities(merged_path)
    result = copy.deepcopy(plan)
    result['bindings']['soccerbase_opening_sources']['club_entities'] = {
        'path': registry.relative_workspace_path(merged_path), 'sha256': registry.sha256_file(merged_path),
        'policy': old_binding['policy']}
    # This object is a source-binding carrier, NOT an approved ownership plan.
    result['schema_version'] = 'pm99-source-only-missing-club-entity-bindings-v1'
    result['updates'] = []
    result['native_writes'] = 0
    result['publication_authorised'] = False
    pipeline.write_canonical_json(output / 'source-plan.json', result)
    print(json.dumps({'queried_missing_ids': sorted(ids), 'dated_starter_witnesses': len(witnesses),
                      'native_writes': 0, 'output': str(output)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--season', required=True)
    parser.add_argument('--club', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.plan, args.season, args.club, args.output)
