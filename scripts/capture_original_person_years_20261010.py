"""Serialize candidate startups and a representative leap-day age profile."""
import os
import subprocess
import time

from scripts import capture_registered_season_runtime_v1 as capture
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_original_person_years_20261010 import ROOT, RELEASE, SEASONS


def wait_for(path, deadline):
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise ValueError('bounded native proof wait expired: ' + str(path))
        time.sleep(10)
    return pipeline.read_json_file(path)


def main():
    deadline = time.monotonic() + 30 * 60
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for season in SEASONS:
        proof = wait_for(ROOT / (season + '-independent-proof.json'), deadline)
        replay = wait_for(ROOT / (season + '-complete-replay-proof.json'), deadline)
        if (not proof['all_other_native_bytes_identical'] or not proof['all_other_recipe_facts_ratings_identical']
                or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
            raise ValueError('candidate lacks independent bytes/recipe/full replay proof')
        release = registry.load_registered_release(season, RELEASE)
        tag = 'original_person_year_r77a_' + season.replace('-', '_') + '_20261010'
        command, evidence = capture.capture_command(season=season, worker='default',
            run_tag=tag, compact_evidence=True, release_id=RELEASE)
        transport = ROOT / (season + '-startup-transport.json')
        if transport.exists():
            retained = pipeline.read_json_file(transport)
            if retained['exit_code'] != 0 or retained['release_manifest_sha256'] != release.manifest_sha256:
                raise ValueError('retained startup failed or binds another game')
            continue
        if evidence.exists():
            raise ValueError('unreceipted startup exists; inspect rather than overwrite')
        result = subprocess.run(command, check=False, env=env)
        pipeline.write_canonical_json(transport, dict(season=season, release_id=RELEASE,
            release_manifest_sha256=release.manifest_sha256, exit_code=result.returncode,
            evidence=registry.relative_workspace_path(evidence), visually_approved=False, installed=False))
        if result.returncode:
            raise ValueError('original-person startup transport failed')
        print(dict(season=season, captured=True, visually_approved=False, installed=False), flush=True)

    season = '2021-22'
    release = registry.load_registered_release(season, RELEASE)
    plan = pipeline.read_json_file(ROOT / (season + '-plan.json'))
    if not any(row['carrier_id'] == 9166 and row['birth_date'] == '2000-02-29' for row in plan['updates']):
        raise ValueError('actual Ferran leap-day correction absent')
    candidate = ROOT / 'ferran-2021-profile-candidate'
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
        scope='Actual Ferran9166 leap-day year repair age and unchanged skills; not roster or artwork approval')
    if receipt_path.exists():
        if pipeline.read_json_file(receipt_path) != expected:
            raise ValueError('retained profile input changed')
    else:
        pipeline.write_canonical_json(receipt_path, expected)
    game = candidate / 'game'
    if game.is_symlink():
        if game.resolve() != release.game_path.resolve():
            raise ValueError('profile helper points to another game')
    elif game.exists():
        raise ValueError('profile game helper must be a symlink')
    else:
        game.symlink_to(release.game_path, target_is_directory=True)
    recipe = candidate / 'season-package.json'
    if recipe.exists():
        if registry.sha256_file(recipe) != expected['package_sha256']:
            raise ValueError('profile helper recipe differs')
    else:
        os.link(release.package_path, recipe)
    transport = ROOT / 'ferran-profile-transport.json'
    if transport.exists():
        if pipeline.read_json_file(transport)['exit_code'] != 0:
            raise ValueError('retained Ferran profile failed')
        return
    tag = 'original_person_ferran_2021_r77a_20261010'
    evidence = ROOT / 'runtime' / tag
    if evidence.exists():
        raise ValueError('profile evidence exists; inspect rather than overwrite')
    result = subprocess.run([str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--worker', 'default', '--run-tag', tag, '--local-game-dir', str(game),
        '--local-artifact-dir', str(evidence), '--player-search', 'Ferran', '--player-label', 'ferran',
        '--profile-name-token', 'Ferran', '--profile-only', '--provenance-file', str(receipt_path)],
        check=False, env=env)
    pipeline.write_canonical_json(transport, dict(season=season, release_id=RELEASE,
        exit_code=result.returncode, evidence=registry.relative_workspace_path(evidence),
        visually_approved=False, installed=False))
    if result.returncode:
        raise ValueError('original-person Ferran profile transport failed')


if __name__ == '__main__':
    main()
