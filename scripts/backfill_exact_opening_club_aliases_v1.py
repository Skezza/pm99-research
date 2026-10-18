#!/usr/bin/env python3
"""Fill only unique country-scoped explicit aliases from already bound captures.

No fuzzy club join, new scraping, roster rename, or game modification. Reread
the exact original earliest fixture and lineup; add only actual substitutions.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_opening_used_substitutes_v2 as substitutes
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

POLICY = 'unique-country-scoped-explicit-club-alias-and-original-fixture-replay-v1'


def unique_capture(club, rows):
    group = roster.club_group(club)
    aliases = roster.club_names(group, club['name'], club.get('full_name', ''))
    candidates = [row for row in rows if
        roster.source_group(row['source_selector']['country_catalog']) == group and
        roster.normalise(row['source_selector']['club_name']) in aliases and
        'transfermarkt_club_id' in row['source_selector']]
    return candidates[0] if len(candidates) == 1 else None


def run(input_root, output_root, retry_failed_reparses=False):
    if output_root.exists():
        raise ValueError('alias source backfill is immutable')
    for season in registry.supported_seasons():
        source = input_root / 'opening' / season / 'opening-review.json'
        document = json.loads(source.read_text())
        transfer.verify_opening_sources(document)
        result = copy.deepcopy(document)
        capture_path = document['bindings'].get('opening_capture_path')
        capture = None
        if capture_path:
            capture_file = ROOT / capture_path
            if registry.sha256_file(capture_file) != document['bindings']['opening_capture_sha256']:
                raise ValueError('original opening capture changed')
            capture = json.loads(capture_file.read_text())
        clubs = {c['carrier_id']: c for _, package, _ in
                 planner.package_layers(registry.load_preferred_release(season)) for c in package['clubs']}
        added, gaps = [], []
        for row in result['clubs']:
            eligible_statuses = {'opening-source-unavailable'}
            if retry_failed_reparses:
                eligible_statuses.add('original-first-fixture-reparse-gap')
            if row['status'] not in eligible_statuses or capture is None:
                continue
            club = clubs.get(row['carrier_id'])
            if club is None or club['name'] != row['club']:
                continue
            raw = unique_capture(club, capture.get('clubs', []))
            if raw is None:
                continue
            try:
                cache = (ROOT / capture_path).parent / 'cache'
                evidence = opening.verify_opening(raw, capture, cache)
                match = next(r for r in evidence['raw_sources'] if r['url'] == evidence['source_url'])
                events = substitutes.parse((ROOT / match['path']).read_bytes(),
                                            evidence['source_club_id'], evidence['starting_xi'])
                for id, name in events['used_substitutes'].items():
                    if id in evidence['substitutes'] and transfer._normalise(evidence['substitutes'][id]) != transfer._normalise(name):
                        raise ValueError('original bench and substitution names disagree')
                    evidence['substitutes'][id] = name
                row.update(status='original-first-fixture-reparsed', evidence=evidence,
                    manager_status='source-reparsed-native-display-identity-not-reapproved',
                    full_opening_roster_verified=False)
                row.pop('error', None)
                if events['unresolved_events']:
                    result['used_substitute_refresh']['summary']['unresolved'].append({
                        'carrier_id': row['carrier_id'], 'reason': 'unresolved-substitution-event',
                        'events': events['unresolved_events']})
                added.append({'carrier_id': row['carrier_id'], 'club': club['name'],
                    'captured_selector': raw['source_selector'], 'fixture_date': evidence['date']})
            except (ValueError, OSError, KeyError) as exc:
                gaps.append({'carrier_id': row['carrier_id'], 'club': club['name'], 'reason': str(exc)})
        result['exact_club_alias_backfill'] = {'policy': POLICY,
            'input_path': registry.relative_workspace_path(source), 'input_sha256': registry.sha256_file(source),
            'implementation_sha256': registry.sha256_file(Path(__file__)), 'added': added, 'gaps': gaps}
        result['exact_club_alias_backfill']['retry_failed_reparses'] = retry_failed_reparses
        result['exact_club_alias_backfill']['opening_reader_sha256'] = registry.sha256_file(Path(opening.__file__))
        target = output_root / 'opening' / season / 'opening-review.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(target, result)
        parent = output_root / 'reviews' / season
        parent.mkdir(parents=True, exist_ok=True)
        for name in ('report.json', 'roster-audit.json'):
            prior = input_root / 'reviews' / season / name
            if prior.is_file():
                os.link(prior, parent / name)
        print(json.dumps({'season': season, 'added': len(added), 'gaps': gaps}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--retry-failed-reparses', action='store_true',
                        help='independently replay failed original claims; never reuse their declared XI')
    args = parser.parse_args()
    run(args.input_root, args.output_root, args.retry_failed_reparses)
