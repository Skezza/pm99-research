#!/usr/bin/env python3
"""Inventory repeated English clubs and absent, already-captured alternatives.

Read-only with respect to recipes/games. This selects no replacement and
approves no player: full original-source replay and fixed-capacity allocation
must still pass the whole-club route. Missing evidence stays explicit.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import prepare_duplicate_club_disposition_v1 as whole


def candidates(clubs, captures):
    clubs = [c for c in clubs if whole.roster.club_group(c) == 'england']
    keys = {c['id']: whole.club_keys(c['name'], c.get('full_name', '')) for c in clubs}
    duplicated = []
    for club in sorted(clubs, key=lambda c: c['carrier_id']):
        if not 3300 <= club['carrier_id'] <= 3331:
            continue
        peers = [c for c in clubs if c['carrier_id'] < club['carrier_id'] and keys[c['id']] & keys[club['id']]]
        if peers:
            duplicated.append({'club_id': club['id'], 'club': club['name'],
                'carrier_id': club['carrier_id'], 'fixed_capacity': len(club['roster_player_ids']),
                'same_real_club_lower_carriers': [{'club_id': p['id'], 'club': p['name'],
                    'carrier_id': p['carrier_id']} for p in peers]})
    represented = set().union(*keys.values()) if keys else set()
    targets = []
    visited = set()
    for row in captures:
        if not row['source_path'].startswith('soccerbase/team/'):
            continue
        names = whole.club_keys(row['club_name'])
        if names & represented or names & visited:
            continue
        visited.update(names)
        openings = [r for r in captures if r['source_path'].startswith('soccerbase/team/')
            and whole.club_keys(r['club_name']) & names]
        annuals = [r for r in captures if r['source_path'].endswith('.txt')
            and whole.roster.source_group(r['country_catalog']) == 'england'
            and whole.club_keys(r['club_name']) & names]
        targets.append({'club': row['club_name'], 'opening_capture_count': len(openings),
            'annual_fact_capture_count': len(annuals),
            'whole_club_route_input_unambiguous': len(openings) == len(annuals) == 1,
            'opening_sources': [{'source_path': r['source_path'], 'source_sha256': r['source_sha256']}
                for r in openings],
            'annual_sources': [{'source_path': r['source_path'], 'source_sha256': r['source_sha256']}
                for r in annuals]})
    return duplicated, targets


def inventory(output):
    if output.exists():
        raise ValueError('whole-club inventory is immutable; never overwrite')
    seasons = []
    for season in whole.registry.supported_seasons():
        release = whole.registry.load_preferred_release(season)
        layers = list(whole.planner.package_layers(release))
        captures, bindings = whole.roster.load_sources(season)
        duplicate, targets = candidates([c for _, p, _ in layers for c in p['clubs']], captures)
        row = {'season': season, 'release_id': release.release_id,
            'recipe_layers': [{'layer': label, 'path': whole.registry.relative_workspace_path(path),
                'sha256': whole.registry.sha256_file(path)} for label, _, path in layers],
            'capture_bindings': bindings, 'duplicate_nonplayable_clubs': duplicate,
            'unrepresented_captured_targets': targets}
        seasons.append(row)
        print(json.dumps({'season': season, 'duplicate_nonplayable_clubs': len(duplicate),
            'unrepresented_captured_targets': len(targets)}), flush=True)
    result = {'schema_version': 'pm99-duplicate-club-disposition-inventory-v1',
        'native_writes': 0, 'replacement_selection_authorised': False,
        'scope': 'exact country-scoped aliases and captured source availability; NOT roster or historical approval',
        'seasons': seasons, 'duplicate_nonplayable_clubs': sum(len(s['duplicate_nonplayable_clubs']) for s in seasons),
        'unrepresented_captured_targets': sum(len(s['unrepresented_captured_targets']) for s in seasons)}
    whole.pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); r = inventory(a.output)
    print(json.dumps({k: v for k, v in r.items() if k != 'seasons'}), flush=True)
