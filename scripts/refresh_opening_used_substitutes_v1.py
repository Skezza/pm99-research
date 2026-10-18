#!/usr/bin/env python3
"""Supplement bound opening reviews with positive original substitution events.

No scraping, recipe edits or game builds. Preserve every original field except
the first-fixture substitutes map, and retain the exact source-review binding.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_opening_used_substitutes_v1 as substitutes
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def refresh(document, loader):
    result = copy.deepcopy(document)
    added = 0
    unresolved = []
    for row in result['clubs']:
        if row['status'] != 'original-first-fixture-reparsed':
            continue
        evidence = row['evidence']
        matches = [s for s in evidence['raw_sources'] if s.get('url') == evidence.get('source_url')
                   and s['path'].endswith('.html')]
        if len(matches) != 1:
            unresolved.append({'carrier_id': row['carrier_id'], 'reason': 'not-one-original-HTML-match-report'})
            continue
        payload = loader(matches[0])
        parsed = opening.match_team(payload, evidence['source_club_id'], evidence['date'])
        if (parsed['starting_xi'] != evidence['starting_xi'] or
                parsed['match_page_date_independently_published'] != evidence['match_page_date_independently_published']):
            raise ValueError('original XI or published fixture date differs from the bound review')
        incoming = substitutes.parse(payload, evidence['source_club_id'], evidence['starting_xi'])
        for id, name in incoming['used_substitutes'].items():
            old = evidence['substitutes'].get(id)
            if old is not None and transfer._normalise(old) != transfer._normalise(name):
                raise ValueError('incoming substitution name conflicts with published bench')
            if old is None:
                evidence['substitutes'][id] = name
                added += 1
        if incoming['unresolved_events']:
            unresolved.append({'carrier_id': row['carrier_id'], 'reason': 'unresolved-substitution-event',
                               'events': incoming['unresolved_events']})
    return result, {'added_positive_used_substitutes': added, 'unresolved': unresolved,
                    'not_a_complete_unused_bench_or_contract_history': True}


def run(input_root, output_root):
    cache = {}
    def loader(source):
        path = ROOT / source['path']
        if path not in cache:
            if registry.sha256_file(path) != source['sha256']:
                raise ValueError('original match report changed')
            cache[path] = path.read_bytes()
        return cache[path]
    summaries = []
    for season in registry.supported_seasons():
        source = input_root / 'opening' / season / 'opening-review.json'
        target = output_root / 'opening' / season / 'opening-review.json'
        document = json.loads(source.read_text())
        input_sha = registry.sha256_file(source)
        transfer.verify_opening_sources(document)
        if target.exists():
            completed = json.loads(target.read_text())
            if completed.get('used_substitute_refresh', {}).get('input_sha256') != input_sha:
                raise ValueError('completed source refresh is bound to another original review')
            transfer.verify_opening_sources(completed)
            summary = completed['used_substitute_refresh']['summary']
        else:
            completed, summary = refresh(document, loader)
            completed['used_substitute_refresh'] = {
                'input_path': registry.relative_workspace_path(source), 'input_sha256': input_sha,
                'implementation_sha256': registry.sha256_file(Path(substitutes.__file__)), 'summary': summary}
            target.parent.mkdir(parents=True, exist_ok=True)
            pipeline.write_canonical_json(target, completed)
        review_source = input_root / 'reviews' / season
        review_target = output_root / 'reviews' / season
        review_target.mkdir(parents=True, exist_ok=True)
        for name in ('report.json', 'roster-audit.json'):
            path = review_source / name
            if not path.is_file():
                continue
            dest = review_target / name
            if dest.exists():
                if registry.sha256_file(dest) != registry.sha256_file(path):
                    raise ValueError('inherited raw squad review changed')
            else:
                # Original reports remain immutable, so a hardlink is safe.
                import os
                os.link(path, dest)
        summaries.append(dict(summary, season=season))
        print(json.dumps(summaries[-1]), flush=True)
        cache.clear()
    return summaries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.input_root, args.output_root)
