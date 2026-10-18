#!/usr/bin/env python3
"""Keep earlier verified secondary facts when rejoining corrected club labels.

The new club joins remain authoritative for membership and shirt numbers.
Unchanged identity facts must not lose already audited NTF/FIFA evidence just
because their source lives outside the main squad capture directory.
"""
import argparse
import collections
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_player_facts_audit_v1 as facts
from scripts import season_historical_review_inventory_v1 as inventory


def merge(previous, current):
    if (previous['player_id'], previous['name'], previous['birth_date'], previous['carrier_id'], previous['club_id']) != (
            current['player_id'], current['name'], current['birth_date'], current['carrier_id'], current['club_id']):
        raise ValueError('cannot reuse facts for a changed identity or roster owner')
    result = copy.deepcopy(current)
    for field in facts.FIELDS:
        old = previous['fields'][field]; new = current['fields'][field]
        if old['recipe_value'] != new['recipe_value']:
            raise ValueError('cannot reuse previous comparison for a changed fact')
        if field == 'shirt_number' and previous['club'] != current['club']: continue
        values = set(old['source_values']) | set(new['source_values'])
        candidates = [{'facts': {'nationalities': sorted(values)}}] if field == 'nationality' else [
            {'facts': {field: value}} for value in values]
        result['fields'][field] = facts.field_check(field, new['recipe_value'], candidates)
    result['evidence'] = list({json.dumps(r, sort_keys=True): r for r in previous['evidence'] + current['evidence']}.values())
    if previous['club'] == current['club']:
        result['same_club_season_identity_match'] |= previous['same_club_season_identity_match']
    return result


def retain(season, prior_root, current_root, output):
    release = registry.load_preferred_release(season)
    prior_path = prior_root / season / 'player-facts-audit.json'
    current_path = current_root / season / 'player-facts-audit.json'
    previous = json.loads(prior_path.read_text()); current = json.loads(current_path.read_text())
    if (current['season'], current['bindings']['package_sha256']) != (season, registry.sha256_file(release.package_path)):
        raise ValueError('new fact joins do not describe the current recipe')
    plan = json.loads((release.package_path.parent / 'club-plan.json').read_text())
    if previous['bindings']['package_sha256'] != plan['package_sha256']:
        raise ValueError('previous facts are not from the exact club-delta predecessor')
    if previous['bindings']['exact_editions_FIFA_sha256'] != current['bindings']['exact_editions_FIFA_sha256']:
        raise ValueError('previous FIFA source changed')
    roster = json.loads((current_root / season / 'report.json').read_text())
    accepted = {(s['source_path'], s['source_sha256']) for s in roster['raw_sources'] if s['status'] == 'raw-source-reparsed'}
    detailed = current['bindings'].get('detailed_capture')
    detailed_root = None
    if detailed:
        detail_path = ROOT / detailed['path']
        if registry.sha256_file(detail_path) != detailed['sha256']: raise ValueError('dated detailed source capture changed')
        detailed_root = ROOT / json.loads(detail_path.read_text())['cache_root']
    checked = {}
    for player in previous['players']:
        for source in player['evidence']:
            if source['provider'] == 'exact-edition-FIFA': continue
            if (source.get('source_path'), source.get('source_sha256')) in accepted: continue
            path = ROOT / source['source_path']
            if not path.is_file() and source['provider'] == 'original-dated-detailed-squad-reparse' and detailed_root:
                relative = Path(source['source_path'])
                if relative.is_absolute() or '..' in relative.parts: raise ValueError('unsafe previous detailed source path')
                path = detailed_root / relative
            if path not in checked: checked[path] = registry.sha256_file(path)
            if checked[path] != source['source_sha256']:
                raise ValueError('earlier independent secondary-fact source bytes changed')
    old = {p['player_id']: p for p in previous['players']}
    result = copy.deepcopy(current); result['players'] = [merge(old[p['player_id']], p) for p in current['players']]
    counts = collections.Counter()
    for player in result['players']:
        for field, check in player['fields'].items(): counts[field + ':' + check['status']] += 1
        counts['identity-with-dated-name-and-DOB-source' if player['evidence'] else 'identity-without-independent-DOB-match'] += 1
        counts['same-club-season-squad-identity-match' if player['same_club_season_identity_match'] else 'same-club-season-squad-identity-unverified'] += 1
    members = collections.defaultdict(list)
    for player in result['players']: members[player['club_id']].append(player)
    for club in result['clubs']:
        club['same_club_season_identity_matches'] = sum(p['same_club_season_identity_match'] for p in members[club['club_id']])
    result['summary'] = {'clubs': len(result['clubs']), 'players': len(result['players']), **dict(counts)}
    result['bindings']['retained_previous_facts'] = {'path': registry.relative_workspace_path(prior_path),
        'sha256': registry.sha256_file(prior_path), 'scope': 'Unchanged exact-identity secondary facts; no renamed-club shirt-number reuse'}
    destination = output / season; destination.mkdir(parents=True, exist_ok=True)
    fact_path = destination / 'player-facts-audit.json'
    if fact_path.exists(): raise ValueError('retained fact evidence output already exists')
    pipeline.write_canonical_json(fact_path, result)
    for name in ('report.json', 'application.json'):
        os.link(current_root / season / name, destination / name)
    inventory.export(season, destination / 'report.json', fact_path, destination / 'review')
    return {'season': season, 'same_club_verified': result['summary']['same-club-season-squad-identity-match'],
        'nationality_matches_retained': result['summary'].get('nationality:match', 0) - current['summary'].get('nationality:match', 0)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-root', type=Path, required=True); parser.add_argument('--current-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--skip-season', action='append', default=[])
    args = parser.parse_args(); summaries = []
    for season in registry.supported_seasons():
        if season in args.skip_season: continue
        row = retain(season, args.prior_root, args.current_root, args.output)
        summaries.append(row); print(json.dumps(row), flush=True)
    pipeline.write_canonical_json(args.output / 'retention-summary.json', {'seasons': summaries, 'historical_verification_complete': False})


if __name__ == '__main__': main()
