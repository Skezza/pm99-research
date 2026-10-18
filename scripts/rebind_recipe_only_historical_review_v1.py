#!/usr/bin/env python3
"""Retain historical player comparisons through a recipe-only manager repair.

Reuse is explicit, not a new scrape or a fresh historical verification claim.
All player/club fields used by the reviews and all native game bytes must be
unchanged. Every available underlying raw player source is rehashed first.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_historical_review_inventory_v1 as inventory
from scripts import season_historical_role_plan_v1 as roles


def assert_review_inputs_unchanged(before, after):
    if before.keys() != after.keys():
        raise ValueError('recipe shape changed')
    for key in before.keys() - {'clubs', 'managers', 'artifacts', 'proofs'}:
        if before[key] != after[key]:
            raise ValueError('player/source/calendar review inputs changed: ' + key)
    if len(before['clubs']) != len(after['clubs']):
        raise ValueError('club review inputs changed')
    for old, new in zip(before['clubs'], after['clubs'], strict=True):
        if {k: v for k, v in old.items() if k != 'manager_id'} != {k: v for k, v in new.items() if k != 'manager_id'}:
            raise ValueError('club review inputs changed')


def rebind(prior_review, prior_opening, output):
    release = registry.load_preferred_release('2015-16')
    if output.exists():
        raise ValueError('completed derived review exists; never overwrite it')
    plan_path = ROOT / release.locator['manager_graph_reconciliation_path']
    plan = json.loads(plan_path.read_text())
    previous = registry.load_registered_release('2015-16', plan['source_release_id'])
    if registry.sha256_file(previous.package_path) != plan['source_package_sha256']:
        raise ValueError('recipe-only predecessor changed')
    assert_review_inputs_unchanged(json.loads(previous.package_path.read_text()),
                                   json.loads(release.package_path.read_text()))
    native_inventory = pipeline.read_json_file(previous.inventory_path)
    if (native_inventory['files_fingerprint'] != plan['source_game_inventory_fingerprint'] or
            release.locator['game_inventory_fingerprint'] != native_inventory['files_fingerprint']):
        raise ValueError('recipe-only native game inventory differs')
    pipeline.assert_tree_matches_inventory(release.game_path, native_inventory)
    native_path = prior_review / 'roster-audit.json'
    if not native_path.exists(): native_path = prior_review / 'report.json'
    fact_path = prior_review / 'player-facts-audit.json'
    opening_path = prior_opening / 'opening-review.json'
    documents = [json.loads(path.read_text()) for path in (native_path, fact_path, opening_path)]
    native, facts, opening = documents
    checked = {}

    def check(path, digest):
        path = path.resolve()
        path.relative_to(ROOT.resolve())
        actual = checked.setdefault(path, registry.sha256_file(path)) if path not in checked else checked[path]
        if actual != digest:
            raise ValueError('retained underlying historical source changed: ' + str(path))

    for document in documents:
        if (document['season'], document['bindings']['package_sha256']) != ('2015-16', plan['source_package_sha256']):
            raise ValueError('review is not from the exact unchanged predecessor')
        bindings = document['bindings']
        for key, value in bindings.items():
            if isinstance(value, dict) and 'path' in value and 'sha256' in value:
                check(ROOT / value['path'], value['sha256'])
            if isinstance(value, list):
                for row in value:
                    if 'path' in row and 'sha256' in row: check(ROOT / row['path'], row['sha256'])
        for filename, key in [('JUG98030.FDI', 'jug_sha256'), ('EQ98030.FDI', 'eq_sha256'), ('ENT98030.FDI', 'ent_sha256')]:
            if key in bindings: check(release.game_path / 'DBDAT' / filename, bindings[key])
    raw = {}
    for source in native['raw_sources']:
        if source['status'] == 'raw-source-reparsed':
            check(ROOT / source['local_path'], source['source_sha256'])
            raw[source['source_path'], source['source_sha256']] = True
    detail = facts['bindings'].get('detailed_capture')
    detail_root = ROOT / json.loads((ROOT / detail['path']).read_text())['cache_root'] if detail else None
    check(roles.FIFA, facts['bindings']['exact_editions_FIFA_sha256'])
    for player in facts['players']:
        for source in player['evidence']:
            if source['provider'] == 'exact-edition-FIFA': continue
            if (source.get('source_path'), source.get('source_sha256')) in raw: continue
            path = ROOT / source['source_path']
            if not path.is_file() and detail_root and source['provider'] == 'original-dated-detailed-squad-reparse':
                path = detail_root / source['source_path']
            check(path, source['source_sha256'])
    destination = output / '2015-16'
    destination.mkdir(parents=True)
    new_native = destination / 'roster-audit.json'
    new_facts = destination / 'player-facts-audit.json'
    new_opening = destination / 'opening-review.json'
    provenance = {'scope': 'Retained comparisons, NOT a new scrape or historical certification',
                  'unchanged_review_inputs': 'all players, all club fields except manager reference, all native bytes',
                  'recipe_delta_path': registry.relative_workspace_path(plan_path),
                  'recipe_delta_sha256': registry.sha256_file(plan_path),
                  'rehash_checked_source_files': len(checked)}
    for path, target, document in zip((native_path, fact_path, opening_path),
                                     (new_native, new_facts, new_opening), documents, strict=True):
        result = copy.deepcopy(document)
        result['bindings'].update(release_id=release.release_id,
                                  package_sha256=registry.sha256_file(release.package_path))
        result['recipe_only_rebinding'] = {**provenance,
            'previous_audit_path': registry.relative_workspace_path(path),
            'previous_audit_sha256': registry.sha256_file(path)}
        if target == new_facts:
            result['bindings'].update(roster_audit_path=registry.relative_workspace_path(new_native),
                                      roster_audit_sha256=registry.sha256_file(new_native))
        pipeline.write_canonical_json(target, result)
    prior_application = json.loads((prior_review / 'application.json').read_text())
    application = {**prior_application, 'release_id': release.release_id,
                   'source_verified_exclusive_managers': len(plan['dated_foreign_managers']) + len(plan['english_manager_graph_checked_unchanged']),
                   'remaining_clubs': len(plan['preserved_non_club_links']),
                   'scope': 'Recipe-only manager graph reconciliation; dated legacy repair retained, no new native corrections',
                   'recipe_only_rebinding': provenance}
    pipeline.write_canonical_json(destination / 'application.json', application)
    result = inventory.export('2015-16', new_native, new_facts, destination / 'review')
    pipeline.write_canonical_json(output / 'summary.json', {'season': '2015-16', 'release_id': release.release_id,
        'reused_source_work': True, 'historical_verification_complete': False, 'provenance': provenance,
        'clubs': result['clubs'], 'players': result['players']})
    return {'season': '2015-16', 'clubs': result['clubs'], 'players': result['players'],
            'rehash_checked_source_files': len(checked), 'reused_source_work': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-review', type=Path, required=True)
    parser.add_argument('--prior-opening', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(rebind(args.prior_review, args.prior_opening, args.output)))


if __name__ == '__main__': main()
