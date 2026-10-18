"""Capture seven private birthday candidates without promoting or approving them."""
import os
import subprocess

from scripts import capture_registered_season_runtime_v1 as capture
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/biographic-birth-years-v1'
RELEASE = 'sourced-biographic-birth-years-20261010-r67a'


def main():
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0',
               PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for path in sorted(ROOT.glob('*-plan.json')):
        plan = pipeline.read_json_file(path)
        season = plan['season']
        # The builder must have finished both independent native readback and replay.
        replay = pipeline.read_json_file(ROOT / (season + '-complete-replay-proof.json'))
        if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
            raise ValueError('private complete replay is not proved')
        release = registry.load_registered_release(season, RELEASE)
        tag = 'birth_year_r67a_' + season.replace('-', '_') + '_20261010'
        command, evidence = capture.capture_command(season=season, worker='tiny-m73',
            run_tag=tag, compact_evidence=True, release_id=RELEASE)
        output = ROOT / (season + '-startup-transport.json')
        if output.exists():
            previous = pipeline.read_json_file(output)
            if previous['release_manifest_sha256'] != release.manifest_sha256 or previous['exit_code']:
                raise ValueError('retained capture binding differs or failed')
            print(dict(season=season, retained=True, visually_approved=False), flush=True)
            continue
        if evidence.exists():
            raise ValueError('unreceipted runner evidence exists; inspect instead of overwrite')
        process = subprocess.run(command, env=env, check=False)
        pipeline.write_canonical_json(output, dict(season=season, release_id=RELEASE,
            release_manifest_sha256=release.manifest_sha256,
            evidence=registry.relative_workspace_path(evidence), exit_code=process.returncode,
            visually_approved=False, installed=False))
        if process.returncode:
            raise ValueError('private startup transport failed')
        print(dict(season=season, captured=True, visually_approved=False, installed=False), flush=True)


if __name__ == '__main__':
    main()
