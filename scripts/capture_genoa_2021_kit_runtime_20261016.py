"""Capture the exact corrected Genoa profile and ordinary Stoke startup."""
import os
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
# Existing renderer establishes the canonical upstream library import path.
from scripts import season_kit_render_bindings_v1
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.build_genoa_2021_kit_20261016 import ROOT, SEASON, RELEASE

TAG = 'genoa_period_kit_2021_22_r113a_20261016'


def main():
    if not all((ROOT / n).exists() for n in ('native-byte-proof.json', 'complete-SOURCE-replay.json')):
        raise ValueError('native and complete SOURCE proofs required before runner')
    release = registry.load_registered_release(SEASON, RELEASE)
    package = pipeline.read_json_file(release.package_path)
    player = next(p for p in package['players'] if p['carrier_id'] == 14650)
    if player['name'] != 'Nicolò Rovella':
        raise ValueError('exact source-bound profile identity differs')
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command, evidence = capture.capture_command(season=SEASON, worker='default', run_tag=TAG + '_stoke',
        compact_evidence=True, release_id=RELEASE)
    bound_capture(command, evidence, ROOT / 'startup-transport.json', release, env)
    target = ROOT / 'runtime/rovella'
    command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--worker', 'default', '--run-tag', TAG + '_rovella', '--local-game-dir', str(release.game_path),
        '--local-artifact-dir', str(target), '--player-search', player['name'],
        '--player-label', 'rovella', '--profile-name-token', 'Rovella', '--profile-only',
        '--provenance-file', str(release.compiler_receipt_path)]
    bound_capture(command, target, ROOT / 'rovella-profile-transport.json', release, env)
    print(dict(exact_game_startup_and_Rovella_profile_captured=True, original_visual_review_pending=True), flush=True)


if __name__ == '__main__':
    main()
