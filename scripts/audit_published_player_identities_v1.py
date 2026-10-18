#!/usr/bin/env python3
"""Count cross-club identities without shirt-heading/display-alias blind spots.

Retain the pinned full-name/DOB person join and its source ID. Names absent or
ambiguous in that dataset remain full-name/DOB candidates, not certified people.
Support immutable release maps so before/after counts use identical rules.
"""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import audit_duplicate_club_cohorts_v1 as cohorts
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

DB = ROOT / '.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb'
SNAPSHOT = ROOT / '.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json'


def load_identity_snapshot():
    # This audit never reads appearance membership. Reuse the exact pinned
    # people/history reader instead of rebuilding a million-row appearance
    # join for both the plain and enriched identity count in every batch.
    from scripts import season_duplicate_source_context_v1 as source
    people, _, binding = source.load_snapshot(DB, SNAPSHOT)
    return people, binding


def key(player, people):
    person = transfer.unique_person(player, people)
    if person is not None:
        return ('published-person', person['source_player_id'])
    raw = cohorts.identity(player)
    return ('full-source-name-dob-candidate', *raw) if raw else None


def run(output, release_map=None, person_supplement=None):
    if output.exists():
        raise ValueError('identity evidence is immutable')
    mapping = {}
    if release_map is not None:
        document = json.loads(release_map.read_text())
        mapping = {row['season']: row for row in document['releases']}
        if set(mapping) != set(registry.supported_seasons()):
            raise ValueError('before-state release map must bind all 26 seasons')
    people, binding = load_identity_snapshot()
    public_binding = None
    if person_supplement is not None:
        from scripts import season_published_person_identity_v1 as public
        digest = registry.sha256_file(person_supplement)
        people, merge_report = public.merge(people, json.loads(person_supplement.read_text()))
        public_binding = {'path': registry.relative_workspace_path(person_supplement),
            'sha256': digest, 'policy': public.POLICY, 'merge_refusals': merge_report['refused']}
    seasons = []
    for season in registry.supported_seasons():
        release = (registry.load_registered_release(season, mapping[season]['release_id'])
                   if mapping else registry.load_preferred_release(season))
        package_sha = registry.sha256_file(release.package_path)
        if mapping and package_sha != mapping[season]['package_sha256']:
            raise ValueError('before-state recipe hash changed')
        players, clubs, layers = {}, {}, []
        for label, package, path in planner.package_layers(release):
            players.update({p['carrier_id']: p for p in package['players']})
            clubs.update({c['id']: c for c in package['clubs']})
            layers.append({'layer': label, 'path': registry.relative_workspace_path(path),
                           'sha256': registry.sha256_file(path)})
        groups = collections.defaultdict(list)
        for p in players.values():
            id = key(p, people)
            if id is not None:
                groups[id].append({'player_id': p['id'], 'carrier_id': p['carrier_id'],
                    'club_id': p['club_id'], 'club': clubs[p['club_id']]['name'],
                    'source_name': p.get('source_name') or p['name'],
                    'birth_date': p['facts']['birth_date']})
        candidates = [{'identity': list(id), 'players': rows} for id, rows in
            sorted(groups.items(), key=lambda item: str(item[0]))
            if len({row['club_id'] for row in rows}) > 1]
        row = {'season': season, 'release_id': release.release_id, 'package_sha256': package_sha,
            'layers': layers, 'cross_club_candidate_groups': len(candidates), 'candidates': candidates}
        seasons.append(row)
        print(json.dumps({k: row[k] for k in ('season', 'release_id', 'cross_club_candidate_groups')}), flush=True)
    result = {'schema_version': 'pm99-published-person-and-full-source-name-dob-audit-v1',
        'policy': 'exact full-name/DOB published ID; explicit shirt labels removed for joins, never initial expansion',
        'snapshot': binding, 'seasons': seasons,
        'cross_club_candidate_groups': sum(row['cross_club_candidate_groups'] for row in seasons)}
    if release_map is not None:
        result['release_map'] = {'path': registry.relative_workspace_path(release_map),
                                'sha256': registry.sha256_file(release_map)}
    if public_binding is not None:
        if registry.sha256_file(person_supplement) != public_binding['sha256']:
            raise ValueError('public identity source changed during the audit')
        result['public_person_supplement'] = public_binding
        result['policy'] += '; original publisher explicit full/short name and confirmed DOB aliases'
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release-map', type=Path)
    parser.add_argument('--person-supplement', type=Path)
    args = parser.parse_args()
    run(args.output, args.release_map, args.person_supplement)
