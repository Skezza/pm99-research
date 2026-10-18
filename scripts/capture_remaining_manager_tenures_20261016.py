"""Capture exact private manager games after native and SOURCE proofs exist."""
import argparse
import os
from pathlib import Path
import time
from scripts import season_kit_render_bindings_v1
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts import build_remaining_manager_tenures_20261016 as batch


def tag(season):
    return 'remaining_manager_tenures_' + season.replace('-', '_') + '_r116a_20261016'


def wait_for_build(season, pids):
    deadline = time.monotonic() + 14400
    while not (batch.ROOT / season / 'complete-SOURCE-replay.json').is_file():
        live = []
        for pid in pids:
            try:
                command = (Path('/proc') / str(pid) / 'cmdline').read_bytes()
            except FileNotFoundError:
                continue
            if b'scripts.build_remaining_manager_tenures_20261016' in command:
                live.append(pid)
        if not live:
            raise ValueError('owned builders stopped before full SOURCE proof; inspect, never restart automatically')
        if time.monotonic() > deadline:
            raise ValueError('bounded build wait expired; inspect the still-live builder')
        time.sleep(10)


def run(season):
    root = batch.ROOT / season
    native = pipeline.read_json_file(root / 'native-byte-proof.json')
    replay = pipeline.read_json_file(root / 'complete-SOURCE-replay.json')
    actual = registry.load_registered_release(season, batch.RELEASE)
    if (native['manifest_sha256'] != actual.manifest_sha256
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
        raise ValueError('native and full SOURCE proof must bind exact candidate')
    command, evidence = capture.capture_command(season=season, worker='default', run_tag=tag(season),
        compact_evidence=True, release_id=batch.RELEASE)
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    bound_capture(command, evidence, root / 'startup-transport.json', actual, env)
    print(dict(season=season, startup_captured=True, original_visual_review_pending=True), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons', nargs='+')
    parser.add_argument('--build-pids', nargs='*', type=int, default=[])
    args = parser.parse_args()
    for season in args.seasons:
        if args.build_pids:
            wait_for_build(season, args.build_pids)
        run(season)
