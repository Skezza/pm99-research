#!/usr/bin/env python3
"""Acquire missing histories for exact original annual-squad name/DOB joins.

Annual membership is NOT opening membership. Subsequent source preparation
still requires consistent entry/exit brackets at the original opening date.
No current squad scraping, inferred IDs, recipes or game writes.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def discover(plan, season, targets, people, events):
    captures, _ = whole.roster.load_sources(season)
    verifier = whole.roster.SourceVerifier(season)
    rows = []
    for target in targets:
        annuals = [c for c in captures if c['source_path'].endswith('.txt')
            and whole.roster.source_group(c['country_catalog']) == 'england'
            and whole.club_keys(target) & whole.club_keys(c['club_name'])]
        if len(annuals) != 1:
            raise ValueError('reserve history queries require one exact original annual squad')
        annual = annuals[0]
        original = verifier.verify(annual)
        if original['status'] != 'raw-source-reparsed':
            raise ValueError('reserve history queries require independent original annual replay')
        for player in annual['players']:
            person = whole.transfer.unique_person({'name': player['name'], 'facts': player}, people)
            if person is None or type(person['source_player_id']) is not int:
                continue
            rows.append({'club': target, 'source_player': copy.deepcopy(player),
                'source_person': copy.deepcopy(person), 'original_annual': original})
    ids = {r['source_person']['source_player_id'] for r in rows}
    if not ids:
        raise ValueError('no exact original name/DOB publisher identities to query')
    return {'schema_version': 'pm99-original-full-squad-history-query-discovery-v1',
        'season': season, 'query_player_ids': sorted(ids), 'witnesses': rows,
        'source_bindings': copy.deepcopy(plan['bindings']), 'native_writes': 0,
        'opening_ownership_approved': False}


def run(plan_path, season, targets, output):
    if (output / 'source-plan.json').exists():
        raise ValueError('completed original history extension is immutable')
    plan = json.loads(plan_path.read_text()); bindings = plan['bindings']; pin = bindings['snapshot']
    people, events, actual = context.load_snapshot(ROOT / pin['path'], ROOT / pin['pinned_receipt_path'])
    if actual != pin:
        raise ValueError('original person/history pin changed')
    people, events, _ = whole.public.merge_bound(people, events, bindings)
    discovery = discover(plan, season, targets, people, events)
    output.mkdir(parents=True, exist_ok=True)
    query = output / 'query-discovery.json'
    if query.exists() and json.loads(query.read_text()) != discovery:
        raise ValueError('saved exact annual history query no longer independently replays')
    if not query.exists():
        pipeline.write_canonical_json(query, discovery)
    old_binding = bindings['published_transfer_supplement']
    old_path = ROOT / old_binding['path']
    old = json.loads(old_path.read_text())
    existing = {r['player_id'] for r in old['players'] if r['status'] == 'raw-history-parsed'}
    requested = set(discovery['query_player_ids']) - existing
    additional = output / 'additional-histories.json'
    if requested and not additional.exists():
        whole.histories.capture_ids(requested, output / 'raw', additional,
            [{'path': registry.relative_workspace_path(query), 'sha256': registry.sha256_file(query)}],
            'exact original annual squad full-name/DOB joins; NOT opening ownership approval')
    merged = copy.deepcopy(old)
    if requested:
        fresh = json.loads(additional.read_text())
        whole.histories.merge({}, fresh)
        if {r['player_id'] for r in fresh['players']} != requested:
            raise ValueError('additional histories differ from exact independently replayed scope')
        replaced = {r['player_id'] for r in fresh['players']}
        merged['players'] = [r for r in merged['players'] if r['player_id'] not in replaced] + fresh['players']
    merged['source_extension'] = {'previous': old_binding, 'query': {
        'path': registry.relative_workspace_path(query), 'sha256': registry.sha256_file(query)}, 'native_writes': 0}
    history_path = output / 'histories.json'
    pipeline.write_canonical_json(history_path, merged)
    _, report = whole.histories.merge(events, merged)
    result = copy.deepcopy(plan)
    result['schema_version'] = 'pm99-source-only-original-annual-history-bindings-v1'
    result['bindings']['published_transfer_supplement'] = whole.public.binding(history_path, whole.histories.POLICY)
    result['updates'] = []; result['native_writes'] = 0; result['publication_authorised'] = False
    pipeline.write_canonical_json(output / 'source-plan.json', result)
    pipeline.write_canonical_json(output / 'merge-report.json', report)
    print(json.dumps({'queried_original_ids': len(requested), 'refused': len(report['refused']),
        'native_writes': 0, 'output': str(output)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True); parser.add_argument('--season', required=True)
    parser.add_argument('--club', action='append', required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); run(args.plan, args.season, args.club, args.output)
