"""Queue actual repaired Stoke startup and Commons profile after manager sweep."""
import argparse
import os
from pathlib import Path
import time
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.build_stoke_original_alias_reserve_20261016 import ROOT, SEASON, RELEASE

TAG = 'stoke_original_alias_2001_02_r117a_20261016'


def wait_for_sweep(pid):
    deadline = time.monotonic() + 7200
    while True:
        try:
            command = (Path('/proc') / str(pid) / 'cmdline').read_bytes()
        except FileNotFoundError:
            return
        if b'scripts.capture_remaining_manager_tenures_20261016' not in command:
            raise ValueError('manager sweep PID identity changed; inspect instead of guessing')
        if time.monotonic() > deadline:
            raise ValueError('bounded wait expired; inspect still-live manager sweep')
        time.sleep(10)


def main(wait_pid=None):
    if not all((ROOT / name).is_file() for name in ('native-byte-proof.json', 'complete-SOURCE-replay.json')):
        raise ValueError('actual alias native and complete SOURCE proofs required')
    if wait_pid is not None:
        wait_for_sweep(wait_pid)
    release = registry.load_registered_release(SEASON, RELEASE)
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command, evidence = capture.capture_command(season=SEASON, worker='default', run_tag=TAG,
        compact_evidence=True, release_id=RELEASE)
    bound_capture(command, evidence, ROOT / 'startup-transport.json', release, env)
    people = pipeline.read_json_file(release.package_path)['players']
    player = next(p for p in people if p['carrier_id'] == 27013)
    if (player['source_name'], player['facts']['birth_date']) != ('Kris Commons', '1983-08-30'):
        raise ValueError('actual replacement is not the independently sourced reserve')
    target = ROOT / 'runtime/commons'
    command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--worker', 'default', '--run-tag', TAG + '_commons', '--local-game-dir', str(release.game_path),
        '--local-artifact-dir', str(target), '--player-search', player['name'], '--player-label', 'commons',
        '--profile-name-token', 'Commons', '--profile-only', '--provenance-file', str(release.compiler_receipt_path)]
    bound_capture(command, target, ROOT / 'commons-profile-transport.json', release, env)
    print(dict(actual_startup_and_Commons_profile_captured=True, visual_review_pending=True), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait-manager-sweep-pid', type=int)
    args = parser.parse_args()
    main(args.wait_manager_sweep_pid)
