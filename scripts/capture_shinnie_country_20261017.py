"""Queue genuine startup/country-profile evidence after the existing captures."""
import argparse
import os
from pathlib import Path
import time

from scripts import build_shinnie_country_20261017 as build
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture

TAG = 'shinnie_original_country_2021_22_r125a_20261017'


def wait_owned(pid, module):
    process = Path('/proc') / str(pid) / 'cmdline'
    while process.exists():
        try:
            command = process.read_bytes()
        except FileNotFoundError:
            return
        if not command:
            return
        if module.encode() not in command:
            raise ValueError('queued dependency PID identity changed')
        time.sleep(10)


def main(builder_pid, previous_runner_pid, *, folder=None, release_id=None, run_tag=TAG,
         previous_runner_module='scripts.capture_public_fixture_batch_20261017',season=None,profile=None,
         capture_startup=True):
    folder = folder if folder is not None else build.ROOT / 'country-delivery'
    release_id = release_id if release_id is not None else build.RELEASE
    season = season if season is not None else build.SEASON
    profile = profile if profile is not None else dict(label='shinnie',search='Graeme Shinnie',token='Shinnie')
    while not (folder / 'complete-SOURCE-replay.json').exists():
        process = Path('/proc') / str(builder_pid) / 'cmdline'
        try:
            command = process.read_bytes()
        except FileNotFoundError as exc:
            raise ValueError('country builder stopped without SOURCE proof; inspect partial state') from exc
        if b'scripts.build_shinnie_country_20261017' not in command:
            raise ValueError('country builder no longer running; do not assume SOURCE success')
        time.sleep(10)
    wait_owned(previous_runner_pid, previous_runner_module)
    release = registry.load_registered_release(season, release_id)
    if not (folder / 'native-byte-proof.json').exists():
        raise ValueError('country native preservation proof required before runtime')
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command, evidence = capture.capture_command(season=season, worker='default',
        run_tag=run_tag, compact_evidence=True, release_id=release_id)
    if capture_startup:
        bound_capture(command, evidence, folder / 'startup-transport.json', release, env)
    else:
        verify_existing_startup(folder, evidence, release)
    label = profile['label']
    target = folder / 'runtime' / label
    command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--worker', 'default', '--run-tag', run_tag + '_' + label,
        '--local-game-dir', str(release.game_path), '--local-artifact-dir', str(target),
        '--player-search', profile['search'], '--player-label', label,
        '--profile-name-token', profile['token'], '--profile-only',
        '--provenance-file', str(release.compiler_receipt_path)]
    bound_capture(command, target, folder / (label + '-profile-transport.json'), release, env)
    print(dict(actual_country_profile_captured=True, original_visual_review_pending=True), flush=True)


def verify_existing_startup(folder, evidence, release):
    """A second profile must reuse, not overwrite, the exact successful startup."""
    transport = pipeline.read_json_file(folder / 'startup-transport.json')
    summary = pipeline.read_json_file(evidence / 'summary.json')
    if (transport.get('exit_code') != 0
            or transport.get('evidence') != registry.relative_workspace_path(evidence)
            or transport.get('release_manifest_sha256') != release.manifest_sha256
            or summary.get('success') is not True
            or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('release_manifest_sha256') != release.manifest_sha256
            or summary.get('output_inventory_fingerprint') != release.locator['game_inventory_fingerprint']):
        raise ValueError('cannot reuse a failed or different-game startup for another profile')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder-pid', type=int, required=True)
    parser.add_argument('--previous-runner-pid', type=int, required=True)
    args = parser.parse_args()
    main(args.builder_pid, args.previous_runner_pid)
