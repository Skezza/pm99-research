"""Wait for the preceding runner batch, then serialize exact factual checks."""
import os
import subprocess
import time

from scripts import capture_registered_season_runtime_v1 as capture
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_original_secondary_facts_20261010 import ROOT, CASES

PROFILES = {'2021-22': ('Ferran', 'ferran', 9166), '2025-26': ('Otegbayo', 'otegbayo', 10249)}


def main(*, root=ROOT, cases=CASES, profiles=PROFILES, preceding=None,
         proof_suffix='-independent-proof-v2.json',profile_tokens=None):
    preceding = preceding or root.parent / 'additional-original-person-birth-years-v1/apter-profile-transport.json'
    deadline = time.monotonic() + 30 * 60
    while not preceding.exists():
        if time.monotonic() > deadline:
            raise ValueError('bounded preceding runner wait expired')
        time.sleep(10)
    if pipeline.read_json_file(preceding)['exit_code'] != 0:
        raise ValueError('preceding runner failed; inspect before launching another batch')
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for season, case in cases.items():
        proof_path = root / (season + proof_suffix)
        replay_path = root / (season + '-complete-replay-proof.json')
        while not proof_path.exists() or not replay_path.exists():
            if time.monotonic() > deadline:
                raise ValueError('bounded independent readback wait expired')
            time.sleep(10)
        proof = pipeline.read_json_file(proof_path)
        replay = pipeline.read_json_file(replay_path)
        if (not proof['all_other_native_bytes_identical'] or not proof['all_other_game_files_identical']
                or not proof['all_other_recipe_facts_identical'] or not replay['complete_game_inventory_identical']
                or not replay['complete_recipe_identical']):
            raise ValueError('secondary-fact source/native/full replay proof incomplete')
        release = registry.load_registered_release(season, case['release'])
        tag = 'original_secondary_' + season.replace('-', '_') + '_' + case['release'].split('-')[-1] + '_20261010'
        command, evidence = capture.capture_command(season=season, worker='default', run_tag=tag,
            compact_evidence=True, release_id=case['release'])
        transport = root / (season + '-startup-transport.json')
        if transport.exists():
            retained = pipeline.read_json_file(transport)
            if retained['exit_code'] != 0 or retained['release_manifest_sha256'] != release.manifest_sha256:
                raise ValueError('retained secondary-fact startup failed or binds another release')
        else:
            if evidence.exists():
                raise ValueError('unreceipted secondary-fact startup exists: inspect instead of overwrite')
            completed = subprocess.run(command, env=env, check=False)
            pipeline.write_canonical_json(transport, dict(season=season, release_id=case['release'],
                release_manifest_sha256=release.manifest_sha256, exit_code=completed.returncode,
                evidence=registry.relative_workspace_path(evidence), visually_approved=False, installed=False))
            if completed.returncode:
                raise ValueError('secondary-fact startup transport failed')
        search, label, carrier = profiles[season]
        candidate = root / (label + '-profile-candidate')
        candidate.mkdir(exist_ok=True)
        expected = dict(season=season, release_id=case['release'],
            release_manifest_sha256=release.manifest_sha256, player_carrier_id=carrier,
            package_sha256=registry.sha256_file(release.package_path),
            source_plan_sha256=registry.sha256_file(root / (season + '-plan.json')),
            exe_sha256=registry.sha256_file(release.game_path / 'MANAGPRE.EXE'),
            native_hashes={n: registry.sha256_file(release.game_path / 'DBDAT' / n) for n in
                ('ENT98030.FDI', 'EQ98030.FDI', 'JUG98030.FDI', 'MINIESC.PKF', 'MINIFOTO.PKF', 'NANOESC.PKF', 'RIDIESC.PKF')},
            scope='Exact factual repair and unchanged skills/kit; no global historical quality approval')
        receipt = candidate / 'candidate-receipt.json'
        if receipt.exists():
            if pipeline.read_json_file(receipt) != expected:
                raise ValueError('retained secondary-fact profile helper changed')
        else:
            pipeline.write_canonical_json(receipt, expected)
        game = candidate / 'game'
        if game.is_symlink():
            if game.resolve() != release.game_path.resolve():
                raise ValueError('secondary-fact profile points to another game')
        elif game.exists():
            raise ValueError('secondary-fact profile game must be a symlink')
        else:
            game.symlink_to(release.game_path, target_is_directory=True)
        recipe = candidate / 'season-package.json'
        if recipe.exists():
            if registry.sha256_file(recipe) != expected['package_sha256']:
                raise ValueError('secondary-fact profile recipe differs')
        else:
            os.link(release.package_path, recipe)
        profile_transport = root / (label + '-profile-transport.json')
        if profile_transport.exists():
            if pipeline.read_json_file(profile_transport)['exit_code'] != 0:
                raise ValueError('retained secondary-fact profile failed')
            continue
        profile_tag = tag + '_' + label
        profile_evidence = root / 'runtime' / profile_tag
        if profile_evidence.exists():
            raise ValueError('unreceipted secondary-fact profile exists: inspect rather than repeat')
        completed = subprocess.run([str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker', 'default', '--run-tag', profile_tag, '--local-game-dir', str(game),
            '--local-artifact-dir', str(profile_evidence), '--player-search', search, '--player-label', label,
            '--profile-name-token', (profile_tokens or {}).get(season,search), '--profile-only', '--provenance-file', str(receipt)], env=env, check=False)
        pipeline.write_canonical_json(profile_transport, dict(season=season, release_id=case['release'],
            exit_code=completed.returncode, evidence=registry.relative_workspace_path(profile_evidence),
            visually_approved=False, installed=False))
        if completed.returncode:
            raise ValueError('secondary-fact profile transport failed')
        print(dict(season=season, normal_startup_and_profile_captured=True,
            visually_approved=False, installed=False), flush=True)


if __name__ == '__main__':
    main()
