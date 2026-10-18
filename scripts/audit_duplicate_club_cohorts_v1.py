#!/usr/bin/env python3
"""Separate whole-club duplication from isolated player ownership mistakes.

Read-only, recipe/native/source-bound evidence. A heavily overlapping squad is
only a candidate; it never authorises replacing a club or deleting its players.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-db-editor'))
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_package_compiler_v2 as compiler
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def identity(player):
    key = roster.person_identity_key(player)
    if key is None:
        return None
    raw = player.get('source_name') or player['name']
    labelled = re.fullmatch(r'#\d{1,2}\s+(.+)', raw.strip())
    return (roster.normalise(labelled.group(1)), key[1]) if labelled else key


def classify_pair(left, right, left_people, right_people, left_source, right_source):
    group = roster.club_group(left)
    if group is None or group != roster.club_group(right):
        return None
    overlap = left_people & right_people
    ratio = len(overlap) / max(1, min(len(left_people), len(right_people)))
    same_source = bool(left_source and right_source and
        left_source['source_club_id'] == right_source['source_club_id'])
    same_label = bool(roster.club_names(group, left['name'], left.get('full_name', '')) &
                      roster.club_names(group, right['name'], right.get('full_name', '')))
    if not same_source and not same_label and not (len(overlap) >= 3 and ratio >= .6):
        return None
    return {'country_group': group, 'shared_player_identities': len(overlap),
        'overlap_fraction_of_smaller_identified_squad': round(ratio, 3),
        'basis': 'independently-reparsed-same-published-club-id' if same_source else
                 'explicit-country-scoped-club-label-alias' if same_label else
                 'large-player-cohort-overlap-candidate-only',
        'whole_club_replacement_authorised': False}


def run(source_root, output):
    if output.exists():
        raise ValueError('cohort evidence is immutable; use another output path')
    seasons = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        clubs, players, layers = {}, {}, []
        for label, package, path in planner.package_layers(release):
            clubs.update({c['id']: c for c in package['clubs']})
            players.update({p['carrier_id']: p for p in package['players']})
            layers.append({'layer': label, 'path': registry.relative_workspace_path(path),
                           'sha256': registry.sha256_file(path)})
        eq = release.game_path / 'DBDAT/EQ98030.FDI'
        _, _, modes = compiler._source_roster_owners(eq.read_bytes())
        opening_path = source_root / 'opening' / season / 'opening-review.json'
        opening = json.loads(opening_path.read_text())
        transfer.verify_opening_sources(opening)
        by_carrier = {c['carrier_id']: c for c in clubs.values()}
        sources = {}
        for row in opening['clubs']:
            club = by_carrier.get(row['carrier_id'])
            if (row['status'] == 'original-first-fixture-reparsed' and club is not None
                    and club['name'] == row['club']):
                sources[club['id']] = row['evidence']
        people = collections.defaultdict(set)
        for p in players.values():
            key = identity(p)
            if key is not None:
                people[p['club_id']].add(key)
        countries = collections.defaultdict(list)
        for club in clubs.values():
            countries[roster.club_group(club)].append(club)
        pairs = []
        for country_clubs in countries.values():
            for left, right in itertools.combinations(sorted(country_clubs, key=lambda c: c['carrier_id']), 2):
                row = classify_pair(left, right, people[left['id']], people[right['id']],
                                    sources.get(left['id']), sources.get(right['id']))
                if row is None:
                    continue
                row['clubs'] = [{'club_id': c['id'], 'carrier_id': c['carrier_id'], 'name': c['name'],
                    'playable': modes[c['carrier_id']] == 0, 'capacity': len(c['roster_player_ids']),
                    'published_opening_source': sources.get(c['id'])} for c in (left, right)]
                playable = [c for c in (left, right) if modes[c['carrier_id']] == 0]
                row['next_action'] = ('protect-playable-carrier-and-source-distinct-same-country-replacement'
                    if len(playable) == 1 else 'source-whole-club-disposition-no-carrier-order-winner')
                pairs.append(row)
        item = {'season': season, 'release_id': release.release_id,
            'package_sha256': registry.sha256_file(release.package_path), 'layers': layers,
            'eq_sha256': registry.sha256_file(eq),
            'opening_path': registry.relative_workspace_path(opening_path),
            'opening_sha256': registry.sha256_file(opening_path), 'pairs': pairs}
        seasons.append(item)
        print(json.dumps({'season': season, 'whole_club_pairs': len(pairs),
            'basis_counts': dict(collections.Counter(r['basis'] for r in pairs))}), flush=True)
    result = {'schema_version': 'pm99-duplicate-club-cohort-audit-v1', 'seasons': seasons,
        'pair_count': sum(len(s['pairs']) for s in seasons),
        'limits': ['Pairs may overlap; their counts are not distinct player errors.',
            'Full names/DOB plus explicit shirt-label handling; no nationality split or initial expansion.',
            'No club disposition, source selection, recipe edit or native write is authorised by this audit.']}
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source_root, args.output)
