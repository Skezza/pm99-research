#!/usr/bin/env python3
"""Refine independently replayed reviews without re-scraping or game writes.

Rehash original sources and verify the previous parser binding. A V2 positive
appearance must already be in the original published/replayed bench. This
bounded refinement may remove penalty false alarms, not invent appearances.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_opening_used_substitutes_v1 as old
from scripts import season_opening_used_substitutes_v2 as new
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def refine(document, loader, original_document):
    result = copy.deepcopy(document)
    original_rows = {r['carrier_id']: r for r in original_document['clubs']}
    unresolved, ignored = [], 0
    for row in result['clubs']:
        if row['status'] != 'original-first-fixture-reparsed':
            continue
        evidence = row['evidence']
        matches = [s for s in evidence['raw_sources'] if s.get('url') == evidence.get('source_url')
                   and s['path'].endswith('.html')]
        if len(matches) != 1:
            unresolved.append({'carrier_id': row['carrier_id'], 'reason': 'not-one-original-HTML-match-report'})
            continue
        parsed = new.parse(loader(matches[0]), evidence['source_club_id'], evidence['starting_xi'])
        original_bench = original_rows[row['carrier_id']]['evidence']['substitutes']
        additions = set(evidence['substitutes']) - set(original_bench)
        if not additions <= set(parsed['used_substitutes']):
            raise ValueError('a replay-added appearance lacks actual substitution markers')
        for id, name in parsed['used_substitutes'].items():
            if transfer._normalise(evidence['substitutes'].get(id, '')) != transfer._normalise(name):
                raise ValueError('refinement cannot introduce an unreplayed player appearance')
        if parsed['unresolved_events']:
            unresolved.append({'carrier_id': row['carrier_id'], 'reason': 'unresolved-substitution-event',
                               'events': parsed['unresolved_events']})
        ignored += parsed['ignored_penalty_events']
    result['used_substitute_refresh']['summary']['unresolved'] = unresolved
    return result, {'ignored_penalty_events': ignored, 'unresolved_clubs': len(unresolved)}


def run(input_root, output_root, seasons=None):
    for season in seasons or registry.supported_seasons():
        if season not in registry.supported_seasons():
            raise ValueError('unsupported season')
        source = input_root / 'opening' / season / 'opening-review.json'
        target = output_root / 'opening' / season / 'opening-review.json'
        if target.exists():
            raise ValueError('refinement is immutable; use another output root')
        document = json.loads(source.read_text())
        binding = document['used_substitute_refresh']
        if (registry.sha256_file(ROOT / binding['input_path']) != binding['input_sha256'] or
                registry.sha256_file(Path(old.__file__)) != binding['implementation_sha256']):
            raise ValueError('original review or replay implementation changed')
        transfer.verify_opening_sources(document)
        def loader(row):
            path = ROOT / row['path']
            if registry.sha256_file(path) != row['sha256']:
                raise ValueError('original report changed during refinement')
            return path.read_bytes()
        original_document = json.loads((ROOT / binding['input_path']).read_text())
        result, summary = refine(document, loader, original_document)
        result['substitution_event_refinement'] = {
            'policy': new.POLICY, 'input_path': registry.relative_workspace_path(source),
            'input_sha256': registry.sha256_file(source),
            'implementation_sha256': registry.sha256_file(Path(new.__file__)), 'summary': summary}
        target.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(target, result)
        parent = output_root / 'reviews' / season
        parent.mkdir(parents=True, exist_ok=True)
        for name in ('report.json', 'roster-audit.json'):
            original = input_root / 'reviews' / season / name
            if original.is_file():
                os.link(original, parent / name)
        print(json.dumps(dict(summary, season=season)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--season', action='append')
    args = parser.parse_args()
    run(args.input_root, args.output_root, args.season)
