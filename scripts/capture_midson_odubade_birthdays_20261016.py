"""Capture nine exact corrected-game startups and three typed date profiles."""
import argparse
import os

from scripts import season_kit_render_bindings_v1
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.build_midson_odubade_birthdays_20261016 import ROOT, RELEASE, TARGETS

PROFILE_SEASONS = {'2006-07', '2011-12', '2015-16'}


def tag(season):
    return 'birthday_disagreement_' + season.replace('-', '_') + '_r114a_20261016'


def run(season):
    root = ROOT / season
    if not all((root / n).exists() for n in ('native-byte-proof.json', 'complete-SOURCE-replay.json')):
        raise ValueError('actual source/native and full SOURCE proofs required before runner')
    release = registry.load_registered_release(season, RELEASE)
    native = pipeline.read_json_file(root / 'native-byte-proof.json')
    if native['manifest_sha256'] != release.manifest_sha256:
        raise ValueError('birthday native proof targets another game')
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command, evidence = capture.capture_command(season=season, worker='default', run_tag=tag(season) + '_stoke',
        compact_evidence=True, release_id=RELEASE)
    bound_capture(command, evidence, root / 'startup-transport.json', release, env)
    if season in PROFILE_SEASONS:
        player = pipeline.read_json_file(root / 'birthday-plan.json')['updates'][0]['before_player']
        target = root / 'runtime/player'
        label = 'odubade' if 'Odubade' in player['source_name'] else 'midson'
        command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker', 'default', '--run-tag', tag(season) + '_' + label,
            '--local-game-dir', str(release.game_path), '--local-artifact-dir', str(target),
            '--player-search', player['name'], '--player-label', label,
            '--profile-name-token', 'Odubade' if label == 'odubade' else 'Midson', '--profile-only',
            '--provenance-file', str(release.compiler_receipt_path)]
        bound_capture(command, target, root / 'player-profile-transport.json', release, env)
    print(dict(season=season, actual_corrected_game_captured=True,
        profile_captured=season in PROFILE_SEASONS, original_visual_review_pending=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons', nargs='*')
    args = parser.parse_args()
    seasons = args.seasons or [r[0] for r in TARGETS]
    if not set(seasons) <= {r[0] for r in TARGETS}:
        raise ValueError('unknown birthday capture season')
    for season in seasons:
        run(season)


if __name__ == '__main__':
    main()
