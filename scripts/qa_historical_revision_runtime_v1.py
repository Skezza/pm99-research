#!/usr/bin/env python3
"""Check corrected seasons as their exact-release runner proofs arrive.

No database is rebuilt. Passed reports for the identical manifest/package are
reused; published revisions and historical evidence gaps are kept distinct.
"""
import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import pm99_season_qa_v1 as qa
from scripts import register_season_qa_results_v1 as registration
from scripts import season_pipeline_v2 as pipeline


def binding(release):
    return {'release_id': release.release_id, 'release_manifest_sha256': release.manifest_sha256,
            'package_sha256': registry.sha256_file(release.package_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-prefix', required=True); parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    parser.add_argument('--wait-seconds', type=int, default=1800)
    parser.add_argument('--skip-season', action='append', default=[])
    args = parser.parse_args(); args.output_root.mkdir(parents=True, exist_ok=True)
    pending = set(registry.supported_seasons()) - set(args.skip_season); results = []
    deadline = time.monotonic() + args.wait_seconds
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        running = {}
        while pending or running:
            for future in list(running):
                if not future.done(): continue
                season, original = running.pop(future)
                report = future.result(); current = registry.load_preferred_release(season)
                if binding(current) != original:
                    raise ValueError('season revision changed while QA was running: ' + season)
                report['historical_revision_binding'] = original
                path = args.output_root / season / 'qa-report.json'; path.parent.mkdir(parents=True, exist_ok=True)
                pipeline.write_canonical_json(path, report)
                if report['result'] == 'pass': registration.register(season, path)
                result = {'season': season, 'release_id': current.release_id, 'result': report['result'], **report['summary']}
                results.append(result); print(json.dumps(result), flush=True)
            for season in sorted(pending):
                if len(running) >= args.jobs: break
                release = registry.load_preferred_release(season)
                if not release.release_id.startswith(args.release_prefix): continue
                path = args.output_root / season / 'qa-report.json'
                original = binding(release)
                if path.exists():
                    report = json.loads(path.read_text())
                    if report.get('historical_revision_binding') != original or report['result'] != 'pass':
                        raise ValueError('saved QA is stale/failed; use fresh output root: ' + season)
                    registration.register(season, path); pending.remove(season)
                    results.append({'season': season, 'release_id': release.release_id,
                                    'result': 'pass', **report['summary'], 'existing_proof_reused': True})
                elif release.attestation_path is not None and not registry._validate_runtime_attestation(release):
                    running[pool.submit(qa.audit_season, season)] = (season, original)
                    pending.remove(season)
            if pending and time.monotonic() >= deadline:
                raise TimeoutError('corrected publication/runtime evidence missing: ' + ', '.join(sorted(pending)))
            if pending or running: time.sleep(1)
    pipeline.write_canonical_json(args.output_root / 'summary.json', {'seasons': sorted(results, key=lambda r: r['season']),
        'historical_verification_complete': False, 'scope': 'Technical/semantic QA with explicit historical warnings'})
    return int(any(r['result'] != 'pass' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
