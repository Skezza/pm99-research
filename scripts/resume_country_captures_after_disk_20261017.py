"""Resume exactly three terminal pre-launch disk refusals, preserving history.

No successful capture/build is repeated. Original exit3 receipts and launch-only
evidence remain; each new tag is distinct and the normal12GiB guard stays on.
"""
import argparse
from pathlib import Path
import subprocess
import time

from scripts import build_country_policy_v2_cohort_20261017 as old
from scripts import build_resolved_period_country_20261017 as new
from scripts.capture_country_policy_v2_cohort_20261017 import tag as old_tag
from scripts.capture_resolved_period_country_20261017 import tag as new_tag
from scripts.capture_shinnie_country_20261017 import main as capture
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts import archive_old_runner_prefix_to_pi_20261017 as archive

ROOT = new.ROOT.parent / 'country-runtime-disk-recovery-20261017'


def launch_only_disk_refusal(root, release):
    transport = pipeline.read_json_file(root / 'startup-transport.json')
    evidence = registry.ROOT / transport['evidence']
    if (transport['exit_code'] != 3 or transport['release_manifest_sha256'] != release.manifest_sha256
            or sorted(p.name for p in evidence.iterdir()) != ['control_launch.json']):
        raise ValueError('not an exact pre-launch-only disk refusal; inspect evidence instead of retrying')
    launch = pipeline.read_json_file(evidence / 'control_launch.json')
    command = launch['child_command']
    if (command[command.index('--release-manifest-sha256')+1] != release.manifest_sha256
            or Path(command[command.index('--dbdat-dir')+1]) != release.game_path / 'DBDAT'):
        raise ValueError('disk refusal original launch binds another actual game')
    return transport


def main(archive_pid):
    if ROOT.exists():
        raise ValueError('existing disk recovery needs inspection; never blind resume')
    ROOT.mkdir()
    tasks = [('2015-16',old,old_tag),('2016-17',new,new_tag),('2017-18',new,new_tag)]
    retained(ROOT/'input.json',dict(archive_controller_pid=archive_pid,
        tasks=[dict(season=s,release_id=m.RELEASE) for s,m,_ in tasks],
        no_successful_capture_or_native_build_repeated=True,automatic_visual_approval=False))
    while not (archive.ROOT/'completed.json').exists():
        try:
            cmd=Path(f'/proc/{archive_pid}/cmdline').read_bytes()
        except FileNotFoundError as exc:
            raise ValueError('runner backup stopped without verified removal; inspect before retrying captures') from exc
        if b'scripts.archive_old_runner_prefix_to_pi_20261017' not in cmd:
            raise ValueError('runner archive PID identity changed')
        time.sleep(10)
    for season,module,tag_function in tasks:
        folder=module.ROOT/season
        release=registry.load_registered_release(season,module.RELEASE)
        launch_only_disk_refusal(folder,release)
        if (folder/'startup-transport-remote-disk-refusal-v1.json').exists():
            raise ValueError('disk recovery already started for this game')
        spec=pipeline.read_json_file(folder/'runtime-profile-spec.json')
        if (spec['season'],spec['release_id'],spec['manifest_sha256'])!=(season,module.RELEASE,release.manifest_sha256):
            raise ValueError('disk recovery profile spec binds another actual game')
        if len(spec['profiles'])!=1:
            raise ValueError('explicit one-profile country recovery required')
        process=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',archive.HOST,
            "df -Pk /home/joe/pm99-runner | awk 'NR==2 {print $4}'"],
            check=True,capture_output=True,text=True)
        if int(process.stdout.strip())<12*1024**2:
            raise ValueError('remote reserve still below normal12GiB; do not retry or override')
        new_tag_value=tag_function(season)+'_disk_recovery_v1'
        retained(ROOT/(season+'-retry-admission.json'),dict(season=season,release_manifest_sha256=release.manifest_sha256,
            original_transport_sha256=registry.sha256_file(folder/'startup-transport.json'),
            original_capture_spec_sha256=registry.sha256_file(folder/'runtime-profile-spec.json'),
            original_exit_code=3,original_local_evidence_launch_only=True,new_startup_run_tag=new_tag_value,
            minimum_remote_reserve_GiB=12,safety_guard_overridden=False))
        (folder/'startup-transport.json').rename(folder/'startup-transport-remote-disk-refusal-v1.json')
        (folder/'runtime-profile-spec.json').rename(folder/'runtime-profile-spec-before-disk-recovery-v1.json')
        retained(folder/'runtime-profile-spec.json',dict(spec,startup_run_tag_override=new_tag_value))
        capture(0,0,folder=folder,release_id=module.RELEASE,run_tag=new_tag_value,
            season=season,profile=spec['profiles'][0])
        retained(ROOT/(season+'-captured.json'),dict(season=season,original_visual_review_pending=True,
            game_regenerated=False,startup_run_tag=new_tag_value))
    retained(ROOT/'completed.json',dict(captured_seasons=[s for s,_,_ in tasks],
        native_writes=0,preferred_writes=0,original_visual_review_pending=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-pid',type=int,required=True)
    main(parser.parse_args().archive_pid)
