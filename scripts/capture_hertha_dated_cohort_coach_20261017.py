"""Queue coupled-name runtime evidence after all existing country captures."""
from pathlib import Path
import time
from scripts import build_hertha_dated_cohort_coach_20261017 as build
from scripts import build_kiraly_period_profiles_20261017 as countries
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def tag(season):return 'hertha_dated_cohort_coach_'+season.replace('-','_')+'_r142a_20261017'
def profile(season):return (2211,'hertha_kiraly','Kiraly','Kiraly')


def main(previous_pid,builders):
    wait_owned(previous_pid,'scripts.capture_kiraly_period_profiles_20261017')
    for season in countries.source.TARGETS:
        saved=countries.source.pipeline.read_json_file(countries.ROOT/season/'kiraly_hungary_keeper-profile-transport.json')
        release=countries.source.registry.load_registered_release(season,countries.RELEASE)
        if saved['exit_code']!=0 or saved['release_manifest_sha256']!=release.manifest_sha256:
            raise ValueError('country capture queue incomplete/failed; resolve it before coupled captures')
    for season,pid in builders:
        folder=build.ROOT/season
        while not (folder/'complete-SOURCE-replay.json').exists():
            try:command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
            except FileNotFoundError as exc:raise ValueError('coupled builder stopped without SOURCE; inspect, not restart') from exc
            if b'scripts.build_hertha_dated_cohort_coach_20261017' not in command:
                raise ValueError('coupled builder PID identity changed')
            time.sleep(10)
        spec_path=folder/'runtime-profile-spec.json'
        if spec_path.exists():raise ValueError('existing coupled capture must be inspected, not restarted')
        release=build.source.registry.load_registered_release(season,build.RELEASE)
        carrier,label,search,token=profile(season)
        spec=dict(carrier_id=carrier,label=label,search=search,token=token)
        retained(spec_path,dict(season=season,release_id=build.RELEASE,manifest_sha256=release.manifest_sha256,
            profiles=[spec],visual_approval=False))
        capture(0,0,folder=folder,release_id=build.RELEASE,run_tag=tag(season),season=season,profile=spec)
        print(dict(season=season,coupled_club_label_captured=True,original_visual_review_pending=True),flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-country-pid',type=int,required=True)
    parser.add_argument('--builder-2002-pid',type=int,required=True)
    parser.add_argument('--builder-2003-pid',type=int,required=True)
    args=parser.parse_args()
    main(args.previous_country_pid,[('2002-03',args.builder_2002_pid),('2003-04',args.builder_2003_pid)])
