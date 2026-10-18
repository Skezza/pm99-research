"""Additional real club-selection evidence for the corrected Dawes display.

This does not replace ordinary Stoke startup attestation or certify all foreign
manager menus. Preserve selection/setup frames, not only the final lineup.
"""
import os
from scripts import season_kit_render_bindings_v1
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.season_tactics_formation_runtime_v1 import selector
from scripts import build_august_manager_tenures_20261016 as batch

SEASON = '2023-24'
TAG = 'august_manager_tenures_2023_24_r115a_20261016_tranmere'


def main():
    root = batch.ROOT / SEASON
    proof = pipeline.read_json_file(root / 'native-byte-proof.json')
    actual = registry.load_registered_release(SEASON, batch.RELEASE)
    if proof['manifest_sha256'] != actual.manifest_sha256 or not (root / 'complete-SOURCE-replay.json').exists():
        raise ValueError('complete actual manager-game proof required')
    plan = pipeline.read_json_file(root / 'manager-plan.json')
    rows = [r for r in plan['updates'] if r['club'] == 'Tranmere Rovers']
    if len(rows) != 1 or (rows[0]['after'], rows[0]['native_before'], rows[0]['native_after']) != ('Ian Dawes', 'Ian Dawes', 'Dawes'):
        raise ValueError('actual source/native Dawes target changed')
    package = pipeline.read_json_file(actual.package_path)
    club = next(c for c in package['clubs'] if c['id'] == rows[0]['club_id'])
    coords = selector(package, club)
    command, evidence = capture.capture_command(season=SEASON, worker='default', run_tag=TAG,
        compact_evidence=False, release_id=batch.RELEASE)
    for flag, value in (('--team-name', club['name']), ('--team-select-x', coords['team'][0]),
            ('--team-select-y', coords['team'][1]), ('--division-select-x', coords['division'][0]),
            ('--division-select-y', coords['division'][1])):
        command[command.index(flag) + 1] = str(value)
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    bound_capture(command, evidence, root / 'tranmere-manager-menu-transport.json', actual, env)
    print(dict(season=SEASON, club=club['name'], original_manager_menu_review_pending=True), flush=True)


if __name__ == '__main__':
    main()
