#!/usr/bin/env python3
"""Capture exact-release runner smoke evidence for historical corrections.

Waits for each bounded publication rather than rebuilding or reusing a proof
from another release. Smoke evidence is not historical roster certification.
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json


def collect_existing(season, prefix):
    release = registry.load_preferred_release(season)
    if not release.release_id.startswith(prefix):
        return {'season': season, 'exit_code': 2, 'error': 'requested revision not preferred'}
    issues = registry._validate_runtime_attestation(release)
    return {'season': season, 'release_id': release.release_id,
            'release_manifest_sha256': release.manifest_sha256,
            'exit_code': int(bool(issues)), 'issues': issues,
            'attestation_path': registry.relative_workspace_path(release.attestation_path) if release.attestation_path else None,
            'runtime_evidence_path': registry.relative_workspace_path(release.runtime_evidence_path) if release.runtime_evidence_path else None,
            'scope': 'runtime smoke, NOT independent historical roster verification',
            'existing_proof_reused': not issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-prefix', required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=[1, 2], default=1)
    parser.add_argument('--skip-season', action='append', default=[])
    parser.add_argument('--wait-publication-seconds', type=int, default=0)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--collect-existing', action='store_true', help='Validate and collect completed exact-release proofs; launch nothing')
    args = parser.parse_args()
    seasons = [s for s in registry.supported_seasons() if s not in args.skip_season]
    if args.collect_existing:
        results = [collect_existing(s, args.release_prefix) for s in seasons]
        args.output_root.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(args.output_root / 'collected-summary.json', {'seasons': results})
        print(json.dumps({'proved_seasons': sum(r['exit_code'] == 0 for r in results), 'seasons': results}))
        return int(any(r['exit_code'] for r in results))
    if not args.execute:
        print(json.dumps({'seasons': seasons, 'execution_requested': False}))
        return 0
    if args.output_root.exists():
        raise ValueError('evidence output exists; never overwrite completed proof')
    args.output_root.mkdir(parents=True)
    stamp = datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')

    def capture(season):
        deadline = time.monotonic() + args.wait_publication_seconds
        while True:
            release = registry.load_preferred_release(season)
            if release.release_id.startswith(args.release_prefix):
                break
            if time.monotonic() >= deadline:
                return {'season': season, 'exit_code': 2, 'error': 'requested revision not published'}
            time.sleep(5)
        tag = f'historical_roles_dob_{season.replace("-", "_")}_{stamp}'
        command = [str(ROOT / 'pm99-season'), 'prove', season, '--execute', '--attest',
                   '--compact-evidence', '--run-tag', tag]
        env = os.environ.copy()
        # The shell CLI invokes python3. Keep child validation in this same
        # explicitly selected environment instead of silently using system Python.
        env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
        env['PM99_RUNNER_WORKER_LANE_COUNT'] = str(args.jobs)
        env['PM99_RUNNER_HOST_LOCK_CONCURRENCY'] = str(args.jobs)
        # Keep runner storage guardrails and lease isolation enabled.
        log = args.output_root / (season + '.log')
        with log.open('w') as handle:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        current = registry.load_preferred_release(season)
        exact = current.release_id == release.release_id and current.manifest_sha256 == release.manifest_sha256
        return {'season': season, 'release_id': release.release_id,
                'release_manifest_sha256': release.manifest_sha256,
                'exit_code': result.returncode if exact else 3,
                'preferred_release_unchanged': exact, 'log': str(log), 'run_tag': tag,
                'scope': 'runtime smoke, NOT independent historical roster verification'}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(capture, season) for season in seasons]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
            _atomic_replace_json(args.output_root / 'progress.json', {'seasons': results})
    pipeline.write_canonical_json(args.output_root / 'summary.json', {'seasons': sorted(results, key=lambda r: r['season'])})
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
