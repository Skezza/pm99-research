#!/usr/bin/env python3
"""Publish bounded club/coach repairs once; resume without rebuilding releases."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json


def apply_one(season, plan_root, release_id):
    current = registry.load_preferred_release(season)
    if current.release_id == release_id:
        receipt = json.loads(current.compiler_receipt_path.read_text())
        return {'season': season, 'release_id': release_id, 'publication_reused': True,
            'changed_clubs': receipt['clubs_written'], 'changed_managers': receipt['managers_written'],
            'changed_players': receipt['players_written'], 'historical_verification_complete': False}
    directory = plan_root / season
    club_plan = json.loads((directory / 'club-plan.json').read_text())
    if not club_plan['updates']:
        return {'season': season, 'release_id': current.release_id, 'skipped': 'no unambiguous label repair',
            'changed_clubs': 0, 'changed_managers': 0, 'changed_players': 0, 'historical_verification_complete': False}
    if registry.locator_path(season, release_id).exists():
        publisher.register_completed_delta(season, release_id)
        return apply_one(season, plan_root, release_id)
    return publisher.publish(season, directory / 'role-plan.json', release_id=release_id, register=True,
        manager_plan_path=directory / 'manager-plan.json', club_plan_path=directory / 'club-plan.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release-id', required=True); parser.add_argument('--skip-season', action='append', default=[])
    parser.add_argument('--wait-seconds', type=int, default=600)
    parser.add_argument('--execute', action='store_true'); args = parser.parse_args()
    seasons = [s for s in registry.supported_seasons() if s not in args.skip_season]
    if not args.execute:
        print(json.dumps({'execution_requested': False, 'seasons': seasons})); return
    args.output.mkdir(parents=True, exist_ok=True); results = []
    for season in seasons:
        destination = args.output / season / 'application.json'
        if destination.exists():
            row = json.loads(destination.read_text())
            if registry.load_preferred_release(season).release_id != row['release_id']:
                raise ValueError('saved club repair application has been superseded')
        else:
            deadline = time.monotonic() + args.wait_seconds
            while not (args.plan_root / season / 'club-plan.json').exists():
                if registry.load_preferred_release(season).release_id == args.release_id: break
                if time.monotonic() >= deadline: raise TimeoutError('missing source-backed club plan: ' + season)
                time.sleep(2)
            row = apply_one(season, args.plan_root, args.release_id)
            destination.parent.mkdir(parents=True, exist_ok=True); pipeline.write_canonical_json(destination, row)
        results.append(row); print(json.dumps(row), flush=True)
        _atomic_replace_json(args.output / 'progress.json', {'seasons': results, 'historical_verification_complete': False})
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': results,
        'changed_clubs': sum(r['changed_clubs'] for r in results),
        'changed_managers': sum(r['changed_managers'] for r in results), 'historical_verification_complete': False})


if __name__ == '__main__': main()
