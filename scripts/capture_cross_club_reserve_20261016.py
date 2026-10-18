"""Capture the exact final private game and both sides of the ownership fix."""
import os
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts.build_cross_club_reviewed_reserve_20261016 import ROOT, SEASON, RELEASE, TAG

PROFILES = ((9171, 'wright_phillips', 'Wright'), (2774, 'kanchelskis', 'Kanchelskis'))


def main(*, root=ROOT, release_id=RELEASE, tag=TAG):
    ROOT, RELEASE, TAG = root, release_id, tag
    if not all((ROOT / name).exists() for name in ('native-byte-proof.json', 'complete-SOURCE-replay.json')):
        raise ValueError('final actual native/SOURCE proofs must precede runner capture')
    release = registry.load_registered_release(SEASON, RELEASE)
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command, evidence = capture.capture_command(season=SEASON, worker='default', run_tag=TAG,
        compact_evidence=True, release_id=RELEASE)
    captured(command, evidence, ROOT / 'startup-transport.json', release, env)
    players = {p['carrier_id']: p for p in pipeline.read_json_file(release.package_path)['players']}
    for carrier, label, token in PROFILES:
        target = ROOT / 'runtime' / label
        command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker', 'default', '--run-tag', TAG + '_' + label,
            '--local-game-dir', str(release.game_path), '--local-artifact-dir', str(target),
            '--player-search', players[carrier]['name'], '--player-label', label,
            '--profile-name-token', token, '--profile-only',
            '--provenance-file', str(release.compiler_receipt_path)]
        captured(command, target, ROOT / (label + '-profile-transport.json'), release, env)
        print(dict(carrier=carrier, captured=True, original_visual_review_pending=True), flush=True)


if __name__ == '__main__':
    main()
