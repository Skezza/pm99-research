#!/usr/bin/env python3
"""Rejoin completed historical sources against corrected club labels.

Do not re-scrape or inherit the old club-membership conclusions. Rehash
unchanged source evidence, then recompute native rosters and player-fact joins.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_player_facts_audit_v1 as facts
from scripts import season_historical_review_inventory_v1 as inventory
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release-id', required=True); parser.add_argument('--skip-season', action='append', default=[])
    parser.add_argument('--wait-seconds', type=int, default=1800); args = parser.parse_args()
    fifa = facts.fifa_facts_index(); results = []; args.output.mkdir(parents=True, exist_ok=True)
    for season in [s for s in registry.supported_seasons() if s not in args.skip_season]:
        deadline = time.monotonic() + args.wait_seconds
        while registry.load_preferred_release(season).release_id != args.release_id:
            if time.monotonic() >= deadline: raise TimeoutError('corrected club release not published: ' + season)
            time.sleep(2)
        release = registry.load_preferred_release(season)
        destination = args.output / season
        native_path = destination / 'report.json'; fact_path = destination / 'player-facts-audit.json'
        for path in (native_path, fact_path):
            if path.exists() and json.loads(path.read_text())['bindings']['package_sha256'] != registry.sha256_file(release.package_path):
                raise ValueError('saved club-label review is stale')
        prior_native = args.prior_root / season / 'roster-audit.json'
        prior_facts = args.prior_root / season / 'player-facts-audit.json'
        if not native_path.exists(): roster.audit_season(season, destination, prior_native)
        old = json.loads(prior_facts.read_text())
        detail = old['bindings'].get('detailed_capture')
        detail_path = ROOT / detail['path'] if detail else None
        if detail and registry.sha256_file(detail_path) != detail['sha256']:
            raise ValueError('prior dated player-fact source changed')
        if not fact_path.exists(): facts.audit_season(season, native_path, detail_path, fifa, destination)
        if not (destination / 'review/summary.json').exists():
            inventory.export(season, native_path, fact_path, destination / 'review')
        native = json.loads(native_path.read_text()); new_facts = json.loads(fact_path.read_text())
        result = {'season': season, 'release_id': release.release_id,
            'prior_same_club_verified': old['summary']['same-club-season-squad-identity-match'],
            'current_same_club_verified': new_facts['summary']['same-club-season-squad-identity-match'],
            'native_roster_mismatches': native['summary']['native_roster_mismatches'],
            'raw_source_reparses_reused': True, 'historical_verification_complete': False}
        results.append(result); print(json.dumps(result), flush=True)
        _atomic_replace_json(args.output / 'progress.json', {'seasons': results})
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': results,
        'historical_verification_complete': False,
        'additional_same_club_verified': sum(r['current_same_club_verified'] - r['prior_same_club_verified'] for r in results)})


if __name__ == '__main__': main()
