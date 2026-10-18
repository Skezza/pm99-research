"""Capture one exact R70 year carrier after the serialized startup batch.

This records transport only; original-image age/club/skill inspection and
independent native/pixel validation are separate mandatory delivery checks.
"""
import os
import subprocess
import time

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_cross_period_birth_years_20261010 import ROOT, RELEASE
from scripts.season_number_label_names_v2 import undecorated, literal_name


def main():
    season = '2022-23'
    release = registry.load_registered_release(season, RELEASE)
    package = pipeline.read_json_file(release.package_path)
    players = [row for row in package['players']
        if literal_name(undecorated(row['name'])) == literal_name('Ayoub Assal')]
    if len(players) != 1 or players[0]['carrier_id'] != 9590:
        raise ValueError('actual Assal carrier/uniqueness changed; inspect before search')
    plan = pipeline.read_json_file(ROOT / (season + '-plan.json'))
    if [row['carrier_id'] for row in plan['updates']] != [9590]:
        raise ValueError('actual age probe is not the accepted source-bound year repair')
    candidate = ROOT / (season + '-profile-candidate')
    candidate.mkdir(exist_ok=True)
    receipt_path = candidate / 'candidate-receipt.json'
    expected = dict(season=season, release_id=RELEASE,
        release_manifest_sha256=release.manifest_sha256,
        package_sha256=registry.sha256_file(release.package_path),
        source_plan_sha256=registry.sha256_file(ROOT / (season + '-plan.json')),
        exe_sha256=registry.sha256_file(release.game_path / 'MANAGPRE.EXE'),
        native_hashes={name: registry.sha256_file(release.game_path / 'DBDAT' / name)
            for name in ('ENT98030.FDI', 'EQ98030.FDI', 'JUG98030.FDI', 'MINIESC.PKF',
                         'MINIFOTO.PKF', 'NANOESC.PKF', 'RIDIESC.PKF')},
        scope='Actual sole Assal9590 year repair age and unchanged skills; NOT role/name/portrait/roster approval')
    if receipt_path.exists():
        if pipeline.read_json_file(receipt_path) != expected:
            raise ValueError('retained R70 profile input differs')
    else:
        pipeline.write_canonical_json(receipt_path, expected)
    game = candidate / 'game'
    if game.is_symlink():
        if game.resolve() != release.game_path.resolve():
            raise ValueError('profile helper points to another game')
    elif game.exists():
        raise ValueError('profile game helper is not a symlink')
    else:
        game.symlink_to(release.game_path, target_is_directory=True)
    recipe = candidate / 'season-package.json'
    if recipe.exists():
        if registry.sha256_file(recipe) != expected['package_sha256']:
            raise ValueError('profile helper recipe differs')
    else:
        os.link(release.package_path, recipe)
    deadline = time.monotonic() + 90 * 60
    paths = [ROOT / (f'{year}-{str(year+1)[-2:]}-startup-transport.json') for year in range(2020, 2026)]
    while not all(path.exists() for path in paths):
        if time.monotonic() >= deadline:
            raise ValueError('serialized startup batch did not finish in time')
        time.sleep(10)
    records = [pipeline.read_json_file(path) for path in paths]
    if any(row['exit_code'] not in (0, None)
            or row['exit_code'] is None and not row.get('completed_summary_recovery') for row in records):
        raise ValueError('preceding startup failed; profile not launched')
    tag = 'cross_period_assal_2022_r70a_20261010'
    evidence = ROOT / 'runtime' / tag
    if evidence.exists():
        raise ValueError('profile evidence exists; inspect instead of overwrite')
    result = subprocess.run([str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--run-tag', tag, '--local-game-dir', str(game), '--local-artifact-dir', str(evidence),
        '--player-search', 'Assal', '--player-label', 'assal',
        '--profile-name-token', 'Assal', '--profile-only',
        '--provenance-file', str(receipt_path)], check=False)
    pipeline.write_canonical_json(ROOT / 'assal-profile-transport.json', dict(
        season=season, release_id=RELEASE, exit_code=result.returncode,
        evidence=registry.relative_workspace_path(evidence), visually_approved=False, installed=False))
    if result.returncode:
        raise ValueError('cross-period year profile transport failed')
    print(dict(captured=True, visually_approved=False, installed=False), flush=True)


if __name__ == '__main__':
    main()
