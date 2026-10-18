"""Check one renamed native carrier after the serialized R69 startup batch.

The helper lives outside the immutable game, and binds the exact native input
hashes. Transport completion is not a visual/name/age/skill approval.
"""
import os
import subprocess
import time

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_original_number_labels_20261010 import ROOT, RELEASE


def main():
    release = registry.load_registered_release('2018-19', RELEASE)
    candidate = ROOT / '2018-19-profile-candidate'
    candidate.mkdir(exist_ok=True)
    receipt_path = candidate / 'candidate-receipt.json'
    expected = dict(season='2018-19', release_id=RELEASE,
        release_manifest_sha256=release.manifest_sha256,
        package_sha256=registry.sha256_file(release.package_path),
        source_plan_sha256=registry.sha256_file(ROOT / '2018-19-plan.json'),
        exe_sha256=registry.sha256_file(release.game_path / 'MANAGPRE.EXE'),
        native_hashes={name: registry.sha256_file(release.game_path / 'DBDAT' / name)
            for name in ('ENT98030.FDI', 'EQ98030.FDI', 'JUG98030.FDI', 'MINIESC.PKF',
                         'MINIFOTO.PKF', 'NANOESC.PKF', 'RIDIESC.PKF')},
        scope='Actual renamed Callum Styles9580/Bury age and unchanged skills; not squad/role/portrait approval')
    if receipt_path.exists():
        if pipeline.read_json_file(receipt_path) != expected:
            raise ValueError('retained fixed-window profile candidate differs')
    else:
        pipeline.write_canonical_json(receipt_path, expected)
    game = candidate / 'game'
    if game.is_symlink():
        if game.resolve() != release.game_path.resolve():
            raise ValueError('retained profile game points to another release')
    elif game.exists():
        raise ValueError('profile game helper already exists and is not a symlink')
    else:
        game.symlink_to(release.game_path, target_is_directory=True)
    package = candidate / 'season-package.json'
    if package.exists():
        if registry.sha256_file(package) != expected['package_sha256']:
            raise ValueError('profile recipe helper differs')
    else:
        os.link(release.package_path, package)
    deadline = time.monotonic() + 60 * 60
    paths = [ROOT / (f'{year}-{str(year+1)[-2:]}-startup-transport.json') for year in range(2018, 2026)]
    while not all(path.exists() for path in paths):
        if time.monotonic() >= deadline:
            raise ValueError('serialized R69 startup batch did not finish in time')
        time.sleep(10)
    if any(pipeline.read_json_file(path)['exit_code'] for path in paths):
        raise ValueError('preceding startup failed; named profile not launched')
    for name, sha in expected['native_hashes'].items():
        if registry.sha256_file(game / 'DBDAT' / name) != sha:
            raise ValueError('native input changed before profile launch')
    tag = 'fixed_window_styles_2018_r69a_20261010'
    evidence = ROOT / 'runtime' / tag
    if evidence.exists():
        raise ValueError('profile evidence exists; inspect instead of overwrite')
    result = subprocess.run([str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--run-tag', tag, '--local-game-dir', str(game), '--local-artifact-dir', str(evidence),
        '--player-search', 'Styles', '--player-label', 'styles',
        '--profile-name-token', 'Styles', '--profile-only',
        '--provenance-file', str(receipt_path)], check=False)
    pipeline.write_canonical_json(ROOT / 'styles-profile-transport.json', dict(
        season='2018-19', release_id=RELEASE, exit_code=result.returncode,
        evidence=registry.relative_workspace_path(evidence), visually_approved=False, installed=False))
    if result.returncode:
        raise ValueError('fixed-window profile transport failed')
    print(dict(captured=True, visually_approved=False, installed=False), flush=True)


if __name__ == '__main__':
    main()
