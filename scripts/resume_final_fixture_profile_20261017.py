"""Recover completed child evidence after terminal parent143; capture only gap.

No successful screen or native game is recreated. Parent interruption remains
explicit; child zero statuses were observed in tool session23795's final output.
"""
from datetime import UTC, datetime
import os
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_discovered_fixture_batches_20261017 import ROOT, RELEASE
from scripts.capture_discovered_fixture_batches_20261017 import tag
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def recover_completed_child(folder, release):
    receipt = folder / 'replacement_18072-profile-transport.json'
    if receipt.exists():
        raise ValueError('recovered child already receipted; never overwrite')
    if (Path('/proc') / '3327709' / 'cmdline').exists():
        raise ValueError('original controller still exists; inspect before recovery')
    target = folder / 'runtime/replacement_18072'
    summaries = list(target.rglob('summary.json'))
    if len(summaries) != 1:
        raise ValueError('one exact returned completed profile required')
    evidence = summaries[0].parent
    summary = pipeline.read_json_file(summaries[0])
    exit_path = evidence / 'remote_startup/container_exit_code.txt'
    if (exit_path.read_text().strip() != '0' or not summary.get('success')
            or summary.get('wine_debugger_detected')
            or not summary['player_profile'].get('expected_name_token_satisfied')):
        raise ValueError('returned remote profile not successful; no inferred recovery')
    if registry.sha256_file(evidence / 'input-provenance.json') != registry.sha256_file(release.compiler_receipt_path):
        raise ValueError('completed child provenance identifies another actual game')
    hashes = {line.split()[1]: line.split()[0]
        for line in (evidence / 'dbdat_override.sha256').read_text().splitlines()
        if line and not line.startswith('#')}
    for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI',
                 'MINIFOTO.PKF', 'RIDIESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF'):
        if hashes.get('DBDAT/' + name) != registry.sha256_file(release.game_path / 'DBDAT' / name):
            raise ValueError('returned completed child native inputs differ')
    screenshot = evidence / 'screens' / Path(summary['player_profile']['screenshot']).name
    if not screenshot.is_file():
        raise ValueError('completed profile original screenshot absent')
    recovery = folder / 'replacement_18072-controller-interruption-recovery.json'
    retained(recovery, dict(utc=datetime.now(UTC).isoformat(), outer_controller_pid=3327709,
        outer_controller_exit_code=143, outer_interruption_cause='not yet established',
        child_status_basis='Original tool write_stdin session23795 terminal output reports all three zeros; original shell exits RUN_STATUS after successful sync/cleanup and provenance copy.',
        observed_child_stdout='  run_status=0\n  sync_status=0\n  cleanup_status=0\n',
        independently_verified_remote_container_exit=0, original_summary=binding(summaries[0]),
        original_frame=binding(screenshot), input_provenance=binding(evidence / 'input-provenance.json'),
        native_hashes=binding(evidence / 'dbdat_override.sha256'),
        child_script=binding(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        original_source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        no_capture_repeated=True, no_game_regenerated=True, visually_approved=False))
    retained(receipt, dict(exit_code=0, evidence=registry.relative_workspace_path(target),
        release_manifest_sha256=release.manifest_sha256, visually_approved=False,
        status_scope='Recovered successful child only; interrupted outer controller143 is not declared successful',
        interruption_recovery=binding(recovery)))


def main():
    folder = ROOT / '2025-26'
    release = registry.load_registered_release('2025-26', RELEASE)
    recover_completed_child(folder, release)
    spec = pipeline.read_json_file(folder / 'runtime-profile-spec.json')
    row = next(r for r in spec['profiles'] if r['label'] == 'retained_18083')
    target = folder / 'runtime' / row['label']
    command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--worker', 'default', '--run-tag', tag('2025-26') + '_' + row['label'],
        '--local-game-dir', str(release.game_path), '--local-artifact-dir', str(target),
        '--player-search', row['search'], '--player-label', row['label'],
        '--profile-name-token', row['token'], '--profile-only',
        '--provenance-file', str(release.compiler_receipt_path)]
    env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    bound_capture(command, target, folder / (row['label'] + '-profile-transport.json'), release, env)
    retained(folder / 'runtime-capture-summary-resumed.json', dict(season='2025-26',
        original_controller_exit_code=143, already_completed_frames_reused=True,
        missing_retained_profile_captured=True, original_visual_review_pending=True))


if __name__ == '__main__':
    main()
