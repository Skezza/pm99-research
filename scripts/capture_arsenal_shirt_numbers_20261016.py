"""Fresh r112 ordinary startup and actual Arsenal shirt-number lineup."""
import os
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.season_tactics_formation_runtime_v1 import selector
from scripts.build_arsenal_shirt_numbers_20261016 import ROOT,SEASON,RELEASE

TAG='arsenal_shirts_2021_22_r112a_20261016'


def main():
    if not all((ROOT/name).exists() for name in ('native-byte-proof.json','complete-SOURCE-replay.json')):
        raise ValueError('actual shirt native and full SOURCE proofs required before runner')
    release=registry.load_registered_release(SEASON,RELEASE)
    package=pipeline.read_json_file(release.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==309)
    coords=selector(package,club)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for target in ('stoke','Arsenal'):
        tag=TAG+'_'+target.lower()
        command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=tag,
            compact_evidence=True,release_id=RELEASE)
        if target=='Arsenal':
            for flag,value in (('--team-name','Arsenal'),('--team-select-x',coords['team'][0]),
                ('--team-select-y',coords['team'][1]),('--division-select-x',coords['division'][0]),
                ('--division-select-y',coords['division'][1])):command[command.index(flag)+1]=str(value)
        bound_capture(command,evidence,ROOT/(target+'-startup-transport.json'),release,env)
        print(dict(target=target,actual_r112_lineup_captured=True,original_visual_review_pending=True),flush=True)


if __name__=='__main__':main()
