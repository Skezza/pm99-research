"""Serialize fresh R70 startup captures after R69 delivery and native proofs."""
import os
import subprocess
import time

from scripts import capture_registered_season_runtime_v1 as capture
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_cross_period_birth_years_20261010 import ROOT, RELEASE


def wait_for(path, deadline):
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise ValueError('bounded cross-period native proof wait expired: ' + str(path))
        time.sleep(10)
    return pipeline.read_json_file(path)


def main():
    deadline = time.monotonic() + 90 * 60
    wait_for(ROOT.parent / 'release-delivery-checklist-v15.json', deadline)
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for year in range(2020, 2026):
        season = f'{year}-{str(year+1)[-2:]}'
        plan = wait_for(ROOT / (season + '-plan.json'), deadline)
        if not plan['updates']:
            continue
        proof = wait_for(ROOT / (season + '-independent-proof.json'), deadline)
        semantic = wait_for(ROOT / (season + '-skill-and-all-file-proof.json'), deadline)
        replay = wait_for(ROOT / (season + '-complete-replay-proof.json'), deadline)
        if (not proof['all_other_native_bytes_identical'] or not semantic['all_visible_skills_and_role_ratings_identical']
                or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
            raise ValueError('cross-period candidate lacks native/semantic/replay proof')
        release = registry.load_registered_release(season, RELEASE)
        tag = 'cross_period_year_r70a_' + season.replace('-', '_') + '_20261010'
        command, evidence = capture.capture_command(season=season, worker='tiny-m73',
            run_tag=tag, compact_evidence=True, release_id=RELEASE)
        transport = ROOT / (season + '-startup-transport.json')
        if transport.exists():
            retained = pipeline.read_json_file(transport)
            if (retained['exit_code'] not in (0, None)
                    or retained['exit_code'] is None and not retained.get('completed_summary_recovery')
                    or retained['release_manifest_sha256'] != release.manifest_sha256):
                raise ValueError('retained cross-period startup belongs to another candidate or failed')
            if retained['exit_code'] is None:
                saved = registry.ROOT / retained['evidence'] / 'summary.json'
                summary = pipeline.read_json_file(saved)
                if (registry.sha256_file(saved) != retained.get('summary_sha256')
                        or summary.get('success') is not True
                        or summary.get('phase_reached') != 'return_from_line_up'
                        or summary.get('release_manifest_sha256') != release.manifest_sha256
                        or summary.get('output_inventory_fingerprint') != release.locator['game_inventory_fingerprint']):
                    raise ValueError('recovered completed runner summary does not prove the exact candidate')
            continue
        if evidence.exists():
            raise ValueError('unreceipted cross-period startup exists; inspect instead of overwrite')
        result = subprocess.run(command, check=False, env=env)
        pipeline.write_canonical_json(transport, dict(season=season, release_id=RELEASE,
            release_manifest_sha256=release.manifest_sha256, exit_code=result.returncode,
            evidence=registry.relative_workspace_path(evidence), visually_approved=False, installed=False))
        if result.returncode:
            raise ValueError('cross-period startup transport failed')
        print(dict(season=season, captured=True, visually_approved=False, installed=False), flush=True)


if __name__ == '__main__':
    main()
