#!/usr/bin/env python3
"""Refresh genuine runner evidence for photo revisions, without rebuilding games."""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-prefix', required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=[1, 2], default=1)
    parser.add_argument('--skip-season', action='append', default=[])
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    seasons = [s for s in registry.supported_seasons()
               if s not in args.skip_season and registry.load_preferred_release(s).release_id.startswith(args.release_prefix)]
    if not args.execute:
        print(json.dumps({'seasons': seasons, 'jobs': args.jobs, 'execution_requested': False}))
        return 0
    args.output_root.mkdir(parents=True)
    stamp = datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')

    def capture(season):
        tag = f'football_photos_{season.replace("-", "_")}_{stamp}'
        command = [str(ROOT / 'pm99-season'), 'prove', season, '--execute', '--attest',
                   '--compact-evidence', '--run-tag', tag]
        environment = os.environ.copy()
        # The runner's native host/lane leases still allocate and isolate each
        # Wine process. Do not enable host setup/build while sharing two lanes.
        environment['PM99_RUNNER_WORKER_LANE_COUNT'] = str(args.jobs)
        environment['PM99_RUNNER_HOST_LOCK_CONCURRENCY'] = str(args.jobs)
        environment['PM99_RUNNER_ARCHIVE_COLD_RUNS'] = '0'
        environment['PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE'] = '0'
        log = args.output_root / (season + '.log')
        with log.open('w') as handle:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=handle, stderr=subprocess.STDOUT)
        return {'season': season, 'exit_code': result.returncode, 'log': str(log), 'run_tag': tag}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(capture, season) for season in seasons]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    results.sort(key=lambda r: r['season'])
    art.save(args.output_root / 'summary.json', {'seasons': results, 'jobs': args.jobs})
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
