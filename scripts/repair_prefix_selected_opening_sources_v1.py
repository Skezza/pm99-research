#!/usr/bin/env python3
"""Correct captured opponent XIs using two original, exact-club parsers.

Keep the original capture and report bytes. Only previously rejected source
claims can be corrected; no game changes or routine starter swaps occur here.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import capture_transfermarkt_opening_lineups_v1 as capture
from scripts import season_historical_opening_review_v1 as independent
from scripts import season_opening_used_substitutes_v2 as substitutes
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.backfill_exact_opening_club_aliases_v1 import unique_capture


def replay(row, document, cache):
    receipts = document['source']['cache_files']
    schedule, schedule_receipt = independent.verified_page(cache, receipts, row['schedule_url'])
    date, match_id = independent.first_fixture(schedule, row['source_competition_code'])
    if (date, match_id) != (row['first_league_fixture_date'], str(row['source_match_id'])):
        raise ValueError('wrong-side correction cannot change the original earliest fixture')
    raw, report_receipt = independent.verified_page(cache, receipts, row['lineup_source_url'])
    id = int(row['source_selector']['transfermarkt_club_id'])
    parsed = independent.match_team(raw, id, date)
    class ExistingReport:
        def get(self, url, key):
            if url != row['lineup_source_url'] or key != f'report/{match_id}.html':
                raise ValueError('wrong-side replay requested another report')
            return raw
    ref = capture.TeamRef(row['source_selector']['club_name'],
        row['source_selector'].get('transfermarkt_club_name', row['source_selector']['club_name']),
        id, '', 'original-capture-exact-numeric-ID-replayed')
    corrected = capture._lineup_from_report(ref, {'report_url': row['lineup_source_url'],
        'match_id': match_id, 'date': date, 'schedule_url': row['schedule_url']}, ExistingReport())
    for key in ('starting_xi', 'substitutes'):
        if set(parsed[key]) != {str(p['source_player_id']) for p in corrected[key]}:
            raise ValueError('primary and independent exact-club lineup parsers disagree')
    if transfer._normalise(parsed['manager']) != transfer._normalise(corrected['declared_manager']):
        raise ValueError('original exact-club managers disagree')
    if {str(p['source_player_id']) for p in row['starting_xi']} == set(parsed['starting_xi']):
        raise ValueError('not an original captured starting-XI identity disagreement')
    result = copy.deepcopy(row)
    for key in ('starting_xi', 'substitutes', 'formation', 'declared_manager',
                'lineup_source_style', 'source_status', 'source_blockers'):
        result[key] = corrected[key]
    events = substitutes.parse(raw, id, parsed['starting_xi'])
    parsed['substitutes'].update(events['used_substitutes'])
    evidence = {'date': date, 'source_club_id': id, 'source_url': row['lineup_source_url'],
        'schedule_url': row['schedule_url'], 'raw_sources': [schedule_receipt, report_receipt], **parsed}
    return result, evidence, events['unresolved_events']


def run(source_root, output_root):
    if output_root.exists():
        raise ValueError('corrected source review is immutable')
    for season in registry.supported_seasons():
        path = source_root / 'opening' / season / 'opening-review.json'
        doc = json.loads(path.read_text())
        transfer.verify_opening_sources(doc)
        result = copy.deepcopy(doc)
        original_path = doc['bindings'].get('opening_capture_path')
        original = None
        if original_path:
            original_path = ROOT / original_path
            if registry.sha256_file(original_path) != doc['bindings']['opening_capture_sha256']:
                raise ValueError('original opening capture changed')
            original = json.loads(original_path.read_text())
        clubs = {c['carrier_id']: c for _, p, _ in planner.package_layers(
            registry.load_preferred_release(season)) for c in p['clubs']}
        corrected_rows, gaps = [], []
        for row in result['clubs']:
            if (original is None or row['status'] != 'original-first-fixture-reparse-gap'
                    or row.get('error') != 'original starting_xi IDs differ from capture'):
                continue
            club = clubs.get(row['carrier_id'])
            if club is None or club['name'] != row['club']:
                continue
            raw_row = unique_capture(club, original['clubs'])
            if raw_row is None:
                continue
            try:
                corrected, evidence, unresolved = replay(raw_row, original, original_path.parent / 'cache')
                receipt = {'schema_version': 'pm99-original-wrong-side-capture-repair-v1',
                    'club': club['name'], 'carrier_id': club['carrier_id'],
                    'original_capture_path': registry.relative_workspace_path(original_path),
                    'original_capture_sha256': registry.sha256_file(original_path),
                    'before': raw_row, 'after': corrected,
                    'primary_reader_sha256': registry.sha256_file(Path(capture.__file__)),
                    'independent_reader_sha256': registry.sha256_file(Path(independent.__file__)),
                    'native_game_modified': False}
                target = output_root / 'capture-repairs' / season / f"club-{club['carrier_id']}.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                pipeline.write_canonical_json(target, receipt)
                evidence['raw_sources'].append({'path': registry.relative_workspace_path(target),
                    'sha256': registry.sha256_file(target), 'url': evidence['source_url']})
                row.update(status='original-first-fixture-reparsed', evidence=evidence,
                    manager_status='exact-club-source-repaired-native-manager-not-reapproved')
                row.pop('error', None)
                if unresolved:
                    result['used_substitute_refresh']['summary']['unresolved'].append({
                        'carrier_id': club['carrier_id'], 'reason': 'unresolved-substitution-event', 'events': unresolved})
                corrected_rows.append({'carrier_id': club['carrier_id'], 'club': club['name'],
                    'repair_path': registry.relative_workspace_path(target), 'native_game_modified': False})
            except (ValueError, KeyError, OSError) as exc:
                gaps.append({'carrier_id': club['carrier_id'], 'club': club['name'], 'reason': str(exc)})
        result['wrong_side_source_replay'] = {'input_path': registry.relative_workspace_path(path),
            'input_sha256': registry.sha256_file(path), 'corrected': corrected_rows, 'gaps': gaps,
            'scope': 'source repair only; any wrong native opening XI requires a separate bounded club transaction'}
        review_path = output_root / 'opening' / season / 'opening-review.json'
        review_path.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(review_path, result)
        for name in ('report.json', 'roster-audit.json'):
            prior = source_root / 'reviews' / season / name
            if prior.is_file():
                target = output_root / 'reviews' / season / name
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(prior, target)
        print(json.dumps({'season': season, 'sources_corrected': len(corrected_rows), 'gaps': gaps}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source_root, args.output)
