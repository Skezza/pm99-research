"""Serialize fresh startup proofs for completed, unpromoted fixed-window names."""
import os
import subprocess
import time

from scripts import capture_registered_season_runtime_v1 as capture
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_original_number_labels_20261010 import ROOT, RELEASE


def wait_for(path, deadline):
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise ValueError('bounded private proof wait expired: ' + str(path))
        time.sleep(10)
    return pipeline.read_json_file(path)


def main():
    deadline = time.monotonic() + 60 * 60
    # Do not overlap the direct named-profile run with a different worker name
    # sharing the same physical host/display. Completion is source-bound below.
    wait_for(registry.ROOT / '.local/consolidated-audit-20261009/release-delivery-checklist-v14.json', deadline)
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for year in range(2018, 2026):
        season = f'{year}-{str(year+1)[-2:]}'
        proof = wait_for(ROOT / (season + '-independent-proof.json'), deadline)
        replay = wait_for(ROOT / (season + '-complete-replay-proof.json'), deadline)
        if not proof['all_visible_skills_and_role_ratings_identical'] or not replay['complete_game_inventory_identical']:
            raise ValueError('fixed-window name candidate lacks semantic/native/replay proof')
        release = registry.load_registered_release(season, RELEASE)
        tag = 'number_labels_r69a_' + season.replace('-', '_') + '_20261010'
        command, evidence = capture.capture_command(season=season, worker='tiny-m73',
            run_tag=tag, compact_evidence=True, release_id=RELEASE)
        transport = ROOT / (season + '-startup-transport.json')
        if transport.exists():
            retained = pipeline.read_json_file(transport)
            if retained['exit_code'] or retained['release_manifest_sha256'] != release.manifest_sha256:
                raise ValueError('retained name startup failed or belongs to another release')
            continue
        if evidence.exists():
            raise ValueError('unreceipted name startup exists; inspect instead of overwrite')
        result = subprocess.run(command, check=False, env=env)
        pipeline.write_canonical_json(transport, dict(season=season, release_id=RELEASE,
            release_manifest_sha256=release.manifest_sha256, exit_code=result.returncode,
            evidence=registry.relative_workspace_path(evidence), visually_approved=False, installed=False))
        if result.returncode:
            raise ValueError('name candidate startup transport failed')
        print(dict(season=season, captured=True, visually_approved=False, installed=False), flush=True)


if __name__ == '__main__':
    main()
