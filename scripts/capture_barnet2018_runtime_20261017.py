"""Capture genuine startup and representative sourced Barnet native profiles."""
import os

from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.publish_barnet2018_private_20261017 import ROOT, FOLDER, SEASON, RELEASE

TAG = 'barnet_original_opening_2018_19_r143a_20261017'
PROFILES = ((11073, 'cousins', 'Cousins'), (11077, 'boucaud', 'Boucaud'))


def main(*, folder=FOLDER, season=SEASON, release_id=RELEASE, tag=TAG, profiles=PROFILES):
    FOLDER,SEASON,RELEASE,TAG,PROFILES=folder,season,release_id,tag,profiles
    if not (FOLDER / 'complete-SOURCE-replay.json').exists():
        raise ValueError('exact full SOURCE proof required before runtime capture')
    if (FOLDER / 'startup-transport.json').exists():
        raise ValueError('inspect retained runtime work rather than repeating the queue')
    release = registry.load_registered_release(SEASON, RELEASE)
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0',
        PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command, evidence = capture.capture_command(season=SEASON, worker='default',
        run_tag=TAG, compact_evidence=True, release_id=RELEASE)
    bound_capture(command, evidence, FOLDER / 'startup-transport.json', release, env)
    players = {p['carrier_id']: p for p in pipeline.read_json_file(release.package_path)['players']}
    for carrier, label, token in PROFILES:
        target = FOLDER / 'runtime' / label
        command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker', 'default', '--run-tag', TAG + '_' + label,
            '--local-game-dir', str(release.game_path), '--local-artifact-dir', str(target),
            '--player-search', players[carrier]['name'], '--player-label', label,
            '--profile-name-token', token, '--profile-only',
            '--provenance-file', str(release.compiler_receipt_path)]
        bound_capture(command, target, FOLDER / (label + '-profile-transport.json'), release, env)
        print(dict(actual_profile_captured=players[carrier]['source_name'], carrier=carrier,
            visual_review_pending=True), flush=True)


if __name__ == '__main__':
    main()
