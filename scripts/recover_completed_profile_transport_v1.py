"""Receipt a proven successful child after an interrupted outer controller.

No capture is launched. Explicit terminal-tool observations, returned remote
exit0, provenance and all native/asset hashes are required. Outer143 remains a
failure; only the completed child receives a recovered transport receipt.
"""
import argparse
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def binding(path):
    return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def validate_observation(observed):
    if (observed.get('outer_controller_exit_code')!=143
            or observed.get('tool_terminal_output_observed') is not True
            or observed.get('observed_child_statuses')!=dict(run_status=0,sync_status=0,cleanup_status=0)
            or not observed.get('tool_session_id')
            or not observed.get('outer_controller_pid') or not observed.get('child_pid')):
        raise ValueError('recovery needs explicit terminal143 and observed successful child statuses')
    for key in ('outer_controller_pid','child_pid'):
        if (Path('/proc')/str(observed[key])/'cmdline').exists():
            raise ValueError('original controller/child PID still exists; inspect before recovery')


def verify_mirrored_native_child(release, evidence):
    """Use original exited-container and native-input records, not inferred shell status.

    The compiler receipt is normally copied only after local sync. Its absence
    does not require another game run when the original remote native hashes,
    source root, exited lease and successful profile are all retained.
    """
    lease = pipeline.read_json_file(evidence / 'remote_startup/lease.json')
    summary = pipeline.read_json_file(evidence / 'summary.json')
    if (lease.get('status') != 'exited' or lease.get('exit_code') != 0
            or lease.get('launcher') != 'run_stars_player_offer_probe_direct.sh'
            or (evidence / 'remote_startup/container_exit_code.txt').read_text().strip() != '0'
            or summary.get('success') is not True or summary.get('wine_debugger_detected')
            or summary.get('crash_detected')
            or not summary.get('player_profile', {}).get('expected_name_token_satisfied')):
        raise ValueError('original remote profile child is not proven exited successfully')
    text = (evidence / 'dbdat_override.sha256').read_text()
    if '# source_root=' + str(release.game_path) not in text.splitlines():
        raise ValueError('original profile input belongs to another game root')
    hashes = {line.split()[1]: line.split()[0] for line in text.splitlines()
              if line and not line.startswith('#')}
    required = ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF',
                'RIDIESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF', 'BIGCAMP.PKF', 'BIGESC.PKF')
    for name in required:
        if hashes.get('DBDAT/' + name) != registry.sha256_file(release.game_path / 'DBDAT' / name):
            raise ValueError('original mirrored child native input differs')
    frame = evidence / 'screens' / Path(summary['player_profile']['screenshot']).name
    if not frame.is_file():
        raise ValueError('original completed frame missing')
    return dict(release_manifest_sha256=release.manifest_sha256,
        evidence=binding(evidence / 'summary.json'), lease=binding(evidence / 'remote_startup/lease.json'),
        original_hashes=binding(evidence / 'dbdat_override.sha256'), frame=binding(frame),
        original_container_exit=0, native_inputs_verified=True,
        outer_controller_exit_code=None, original_local_sync_status=None,
        status_scope='Original remote child only. Missing outer-controller/sync results are unknown, not declared successful.',
        compiler_provenance_file_reconstructed=False, no_capture_repeated=True)


def main(folder,season,release_id,label,observation):
    observed=pipeline.read_json_file(observation);validate_observation(observed)
    release=registry.load_registered_release(season,release_id)
    spec=pipeline.read_json_file(folder/'runtime-profile-spec.json')
    if (spec['season'],spec['release_id'],spec['manifest_sha256'])!=(season,release_id,release.manifest_sha256):
        raise ValueError('recovered profile spec binds another actual game')
    if len([r for r in spec['profiles'] if r['label']==label])!=1:
        raise ValueError('recovered profile label is not an exact selected carrier')
    target=folder/'runtime'/label
    receipt=folder/(label+'-profile-transport.json')
    if receipt.exists():raise ValueError('existing transport must not be overwritten/recovered twice')
    summaries=list(target.rglob('summary.json'))
    if len(summaries)!=1:raise ValueError('one exact returned completed original profile required')
    evidence=summaries[0].parent;summary=pipeline.read_json_file(summaries[0])
    exit_path=evidence/'remote_startup/container_exit_code.txt'
    if (exit_path.read_text().strip()!='0' or summary.get('success') is not True
            or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or not summary['player_profile'].get('expected_name_token_satisfied')):
        raise ValueError('returned original remote child did not succeed')
    if registry.sha256_file(evidence/'input-provenance.json')!=registry.sha256_file(release.compiler_receipt_path):
        raise ValueError('recovered original child compiler provenance differs')
    hashes={line.split()[1]:line.split()[0] for line in (evidence/'dbdat_override.sha256').read_text().splitlines()
        if line and not line.startswith('#')}
    for name in ('JUG98030.FDI','EQ98030.FDI','ENT98030.FDI','MINIFOTO.PKF','RIDIESC.PKF','MINIESC.PKF','NANOESC.PKF'):
        if hashes.get('DBDAT/'+name)!=registry.sha256_file(release.game_path/'DBDAT'/name):
            raise ValueError('recovered original child native/asset input differs')
    screenshot=evidence/'screens'/Path(summary['player_profile']['screenshot']).name
    if not screenshot.is_file():raise ValueError('original completed child frame missing')
    recovery=folder/(label+'-controller-interruption-recovery.json')
    retained(recovery,dict(original_terminal_observation=binding(observation),
        outer_controller_exit_code=143,outer_interruption_cause='not established',
        status_scope='Completed child only; interrupted outer controller is NOT declared successful.',
        independently_verified_remote_container_exit=0,original_summary=binding(summaries[0]),
        original_frame=binding(screenshot),input_provenance=binding(evidence/'input-provenance.json'),
        native_hashes=binding(evidence/'dbdat_override.sha256'),
        child_script=binding(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
        no_capture_repeated=True,no_game_regenerated=True,visually_approved=False))
    retained(receipt,dict(exit_code=0,evidence=registry.relative_workspace_path(target),
        release_manifest_sha256=release.manifest_sha256,visually_approved=False,
        status_scope='Recovered successful child only; interrupted outer controller143 is not declared successful',
        interruption_recovery=binding(recovery)))
    print(dict(completed_child_recovered=True,outer_controller_exit=143,repeated_captures=0),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--season',required=True)
    parser.add_argument('--release-id',required=True);parser.add_argument('--label',required=True)
    parser.add_argument('--observation',type=Path,required=True)
    args=parser.parse_args();main(args.folder,args.season,args.release_id,args.label,args.observation)
