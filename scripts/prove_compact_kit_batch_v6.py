#!/usr/bin/env python3
"""Attest installed V6 seasons and measure their genuine TEAM RATING pixels."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-db-editor'))
from scripts import build_registered_quality_release_v1 as builder
from scripts import capture_registered_season_runtime_v1 as capture
from scripts import pm99_factory_kit_renderer_v6 as factory
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as visual
from scripts import verify_compact_kit_runtime_v6 as pixels


def require_installed_v6(season):
    release = registry.load_preferred_release(season)
    receipt_path = builder._kit_receipt(season)
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('renderer') != factory.RENDERER_ID:
        raise ValueError('V6 kit fix is not installed; old release is not new-kit evidence')
    audit_path = Path(receipt['audit_path'])
    if visual.sha(audit_path) != receipt['audit_sha256']:
        raise ValueError('kit audit changed')
    audit = json.loads(audit_path.read_text())
    if audit['blockers'] or audit['all_records'] != 544:
        raise ValueError('complete kit audit has not passed')
    return release


def prove_one(season, worker, batch_tag):
    try:
        require_installed_v6(season)
        tag = f'{batch_tag}_{season.replace("-", "_")}'
        capture.capture_one(season=season, args=SimpleNamespace(
            run_tag=tag, worker=worker, execute=True, attest=True, compact_evidence=True))
        release = registry.load_preferred_release(season)
        evidence = ROOT / release.locator['runtime_evidence_path']
        result = pixels.verify(season, evidence)
        result['runtime_attested'] = True
        result['status'] = 'passed' if result['passed'] else 'pixel-check-failed'
        return result
    except (ValueError, OSError, registry.RegistryError, capture.CaptureError,
            capture.attester.RuntimeAttestationError) as exc:
        return {'season': season, 'passed': False, 'status': 'failed', 'error': str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season', help='YYYY-YY or all')
    parser.add_argument('--worker', default='linux-runner')
    parser.add_argument('--execute', action='store_true', help='default is read-only preflight')
    parser.add_argument('--report', type=Path, default=ROOT / '.local/compact-kit-v6/runtime-report.json')
    args = parser.parse_args()
    seasons = registry.supported_seasons() if args.season == 'all' else [args.season]
    failures = []
    for season in seasons:
        try:
            require_installed_v6(season)
        except (ValueError, OSError, registry.RegistryError) as exc:
            failures.append({'season': season, 'error': str(exc)})
    if failures:
        print(json.dumps({'status': 'preflight-blocked', 'failures': failures}, indent=2))
        return 2
    if not args.execute:
        print(json.dumps({'status': 'ready', 'seasons': seasons, 'worker_lanes': 2,
                          'local_screens_per_season': 2, 'full_screens_retained_remotely': True}))
        return 0
    # Two local proof images plus logs are ~0.7 MiB per season. Budget a
    # conservative 2 MiB, preserving the same 512 MiB safety reserve.
    if shutil.disk_usage(ROOT).free < (512 + 2 * len(seasons)) * 1024**2:
        print('Insufficient space for runner evidence above the 512 MiB reserve', file=sys.stderr)
        return 2
    os.environ['PM99_RUNNER_WORKER_LANE_COUNT'] = '2'
    tag = 'compact_v6_' + datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(prove_one, s, args.worker, tag): s for s in seasons}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            capture.attester._atomic_replace_json(args.report, {'schema_version': 'pm99-compact-kit-v6-runtime-batch-v1',
                'requested_seasons': len(seasons), 'completed': len(results),
                'passed': sum(r['passed'] for r in results),
                'results': sorted(results, key=lambda r: r['season'])})
            print(json.dumps(result), flush=True)
    return 0 if all(r['passed'] for r in results) else 2


if __name__ == '__main__':
    raise SystemExit(main())
