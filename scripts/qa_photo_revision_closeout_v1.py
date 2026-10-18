#!/usr/bin/env python3
"""QA photo revisions as their fresh runtime attestations arrive; never rebuild."""
import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import pm99_season_qa_v1 as qa
from scripts import register_season_qa_results_v1 as registration
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art


def binding(release):
    return {'release_id': release.release_id, 'release_manifest_sha256': release.manifest_sha256,
            'output_inventory_fingerprint': release.locator['game_inventory_fingerprint']}


def save_report(path, report, release):
    report['photo_revision_binding'] = binding(release)
    path.parent.mkdir(parents=True, exist_ok=True)
    art.save(path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-prefix', required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=[1, 2], default=2)
    parser.add_argument('--wait-for-runtime', type=int, default=1800)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    bindings = {s: registry.load_preferred_release(s) for s in registry.supported_seasons()
                if registry.load_preferred_release(s).release_id.startswith(args.release_prefix)}
    pending = set(bindings)
    results = []
    for season in sorted(pending):
        path = args.output_root / season / 'qa-report.json'
        if not path.is_file(): continue
        report = json.loads(path.read_text())
        if report.get('photo_revision_binding') != binding(bindings[season]) or report['result'] != 'pass':
            raise ValueError('existing QA is stale or failed; use a fresh report root: ' + season)
        registration.register(season, path)
        results.append({'season': season, 'result': report['result'], **report['summary']})
        pending.remove(season)
    deadline = time.monotonic() + args.wait_for_runtime
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        running = {}
        while pending or running:
            for future in list(running):
                if not future.done(): continue
                season = running.pop(future)
                report = future.result()
                path = args.output_root / season / 'qa-report.json'
                current = registry.load_preferred_release(season)
                if binding(current) != binding(bindings[season]):
                    raise ValueError('preferred photo release changed while auditing: ' + season)
                save_report(path, report, current)
                if report['result'] == 'pass':
                    registration.register(season, path)
                result = {'season': season, 'result': report['result'], **report['summary']}
                results.append(result)
                print(json.dumps(result), flush=True)
            for season in sorted(pending):
                if len(running) >= args.jobs: break
                current = registry.load_preferred_release(season)
                original = bindings[season]
                if (current.release_id, current.manifest_sha256) != (original.release_id, original.manifest_sha256):
                    raise ValueError('preferred photo release changed during QA: ' + season)
                if current.attestation_path is not None:
                    running[pool.submit(qa.audit_season, season)] = season
                    pending.remove(season)
            if pending and time.monotonic() > deadline:
                raise TimeoutError('fresh runtime proof still missing for ' + ', '.join(sorted(pending)))
            if pending or running: time.sleep(1)
    results.sort(key=lambda row: row['season'])
    if not (args.output_root / 'summary.json').exists():
        art.save(args.output_root / 'summary.json', {'seasons': results})
    return int(any(r['result'] != 'pass' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
