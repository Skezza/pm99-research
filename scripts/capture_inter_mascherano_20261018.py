"""Serial runner proof for two already-built, source-admitted corrections.

The first Colombo surname result is Roberto at Milan; select the second
visible row and still require independent exact-person visual/native review.
This script neither approves evidence nor publishes either game.
"""
import os
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture

AUDIT = registry.ROOT / '.local/consolidated-audit-20261009'


def profile(root, release, carrier, label, token, tag, env, row=None):
    package = pipeline.read_json_file(release.package_path)
    actor = next(p for p in package['players'] if p['carrier_id'] == carrier)
    target = root / 'runtime' / label
    command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--worker', 'default', '--run-tag', tag, '--local-game-dir', str(release.game_path),
        '--local-artifact-dir', str(target), '--player-search', actor['name'],
        '--player-label', label, '--profile-name-token', token, '--profile-only',
        '--provenance-file', str(release.compiler_receipt_path)]
    if row is not None:
        command += ['--player-row-click', row]
    bound_capture(command, target, root / (label + '-profile-transport.json'), release, env)
    print(dict(captured=label, carrier=carrier, exact_identity_review_pending=True), flush=True)


def main():
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0',
               PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    inter_root = AUDIT / 'Gresko2000-Inter-opening-review-v1'
    inter = registry.load_registered_release('2000-01',
        'sourced-inter-august-contract-reserve-20261018-r160a')
    if not (inter_root / 'colombo-rejected-wrong-search-result.json').exists():
        raise ValueError('preserve rejected Roberto search result before new capture')
    profile(inter_root, inter, 21373, 'colombo_inter', 'Colombo',
            'inter_contract_2000_01_r160a_20261018_colombo_second', env, '120,182,1')
    root = AUDIT / 'Mascherano2010-dated-role-v1'
    release = registry.load_registered_release('2010-11',
        'sourced-dated-mascherano-midfield-20261018-r161a')
    if not (root / 'complete-SOURCE-replay.json').exists():
        raise ValueError('complete actual SOURCE replay required before capture')
    command, evidence = capture.capture_command(season='2010-11', worker='default',
        run_tag='mascherano_midfield_2010_11_r161a_20261018',
        compact_evidence=True, release_id=release.release_id)
    bound_capture(command, evidence, root / 'startup-transport.json', release, env)
    profile(root, release, 8066, 'mascherano', 'Mascherano',
            'mascherano_midfield_2010_11_r161a_20261018_profile', env)


if __name__ == '__main__':
    main()
