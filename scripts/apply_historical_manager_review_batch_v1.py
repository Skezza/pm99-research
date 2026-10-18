#!/usr/bin/env python3
"""Apply independently checked manager deltas as completed source reports arrive.

Reuses completed publications and unchanged player/source audits. A failed
roster QA is recorded, never converted into approval by correcting a manager.
Only one publisher writes the preferred-release catalogue at a time.
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
from scripts import season_historical_manager_plan_v1 as managers
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import refresh_historical_roster_native_view_v1 as native
from scripts import supplement_historical_player_facts_review_v1 as facts
from scripts import season_historical_review_inventory_v1 as inventory
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json


def previous_qa_finished(release, report_path):
    if not report_path.exists() or registry._validate_runtime_attestation(release): return False
    report = json.loads(report_path.read_text())
    expected = {'release_id': release.release_id, 'release_manifest_sha256': release.manifest_sha256,
                'package_sha256': registry.sha256_file(release.package_path)}
    if report.get('historical_revision_binding') != expected:
        raise ValueError('previous QA does not bind the source revision')
    # Let a passing QA registration finish before any catalogue transition.
    if report['result'] == 'pass' and release.locator.get('qa_report_sha256') != registry.sha256_file(report_path):
        return False
    return True


def immutable(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value: raise ValueError('saved manager plan is stale')
    else:
        path.parent.mkdir(parents=True, exist_ok=True); pipeline.write_canonical_json(path, value)


def refresh_reviews(season, args):
    roster_path = args.output / season / 'roster-audit.json'
    facts_path = args.output / season / 'player-facts-audit.json'
    csv_root = args.output / season / 'review'
    release = registry.load_preferred_release(season)
    current_hash = registry.sha256_file(release.package_path)
    for path in (roster_path, facts_path):
        if path.exists() and json.loads(path.read_text())['bindings']['package_sha256'] != current_hash:
            raise ValueError('completed manager-revision player review is stale')
    if not roster_path.exists():
        native.refresh(season, args.roster_root / season / 'report.json', roster_path)
    if not facts_path.exists():
        facts.supplement(season, args.facts_root / season / 'player-facts-audit.json', None, facts_path)
    if not (csv_root / 'summary.json').exists(): inventory.export(season, roster_path, facts_path, csv_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opening-root', type=Path, required=True)
    parser.add_argument('--prior-qa-root', type=Path, required=True)
    parser.add_argument('--plan-root', type=Path, required=True)
    parser.add_argument('--roster-root', type=Path, required=True)
    parser.add_argument('--facts-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--wait-seconds', type=int, default=3600)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'execution_requested': False, 'seasons': registry.supported_seasons()})); return 0
    args.output.mkdir(parents=True, exist_ok=True)
    results = []; deadline = time.monotonic() + args.wait_seconds
    for season in registry.supported_seasons():
        result_path = args.output / season / 'application.json'
        if result_path.exists():
            result = json.loads(result_path.read_text()); current = registry.load_preferred_release(season)
            if result['release_id'] != current.release_id: raise ValueError('completed manager application is stale')
            results.append(result); print(json.dumps({'existing_application_reused': True, **result}), flush=True); continue
        while True:
            release = registry.load_preferred_release(season)
            if release.release_id == args.release_id: break
            audit = args.opening_root / season / 'opening-review.json'
            if audit.exists() and previous_qa_finished(release, args.prior_qa_root / season / 'qa-report.json'): break
            if time.monotonic() >= deadline: raise TimeoutError('source/prior runtime/QA missing: ' + season)
            time.sleep(2)
        reused = release.release_id == args.release_id
        if reused:
            path = release.package_path.parent / 'manager-plan.json'; plan = json.loads(path.read_text())
            receipt = json.loads(release.compiler_receipt_path.read_text())
            changed = receipt['managers_written']
        else:
            plan = managers.plan(season, args.opening_root / season / 'opening-review.json')
            path = args.plan_root / season / 'manager-plan.json'; immutable(path, plan)
            control = {'season': season, 'release_id': release.release_id,
                'package_sha256': registry.sha256_file(release.package_path),
                'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'), 'updates': [], 'unresolved': []}
            control_path = path.parent / 'role-control-plan.json'; immutable(control_path, control)
            if not plan['updates']:
                changed = 0
            elif registry.locator_path(season, args.release_id).exists():
                publisher.register_completed_delta(season, args.release_id)
                changed = json.loads(registry.load_preferred_release(season).compiler_receipt_path.read_text())['managers_written']
            else:
                changed = publisher.publish(season, control_path, release_id=args.release_id,
                    register=True, manager_plan_path=path)['changed_managers']
        refresh_reviews(season, args)
        current = registry.load_preferred_release(season)
        result = {'season': season, 'release_id': current.release_id, 'changed_manager_names': changed,
            'manager_plan_sha256': registry.sha256_file(path), **plan['summary'],
            'source_publication_reused': reused, 'historical_verification_complete': False,
            'scope': 'Dated exclusively-owned manager names only; roster/identity gaps remain release blockers'}
        immutable(result_path, result); results.append(result)
        _atomic_replace_json(args.output / 'progress.json', {'seasons': results, 'historical_verification_complete': False})
        print(json.dumps(result), flush=True)
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': results,
        'changed_manager_names': sum(r['changed_manager_names'] for r in results),
        'historical_verification_complete': False})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
