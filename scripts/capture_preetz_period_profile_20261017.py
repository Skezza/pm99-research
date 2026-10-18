"""Capture exact final Preetz startup and country/role profile per season."""
import argparse
from scripts import build_preetz_period_profile_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

PROFILE=(12468,'preetz_germany_striker','Preetz','Preetz')


def tag(season):return 'preetz_period_profile_'+season.replace('-','_')+'_r138a_20261017'


def main(season,previous_runner_pid=0):
    folder=build.ROOT/season;path=folder/'runtime-profile-spec.json'
    if path.exists():raise ValueError('existing Preetz capture must be inspected, not restarted')
    if not (folder/'complete-SOURCE-replay.json').exists():raise ValueError('Preetz complete SOURCE proof required')
    wait_owned(previous_runner_pid,'scripts.capture_preetz_period_profile_20261017')
    actual=build.source.registry.load_registered_release(season,build.RELEASE)
    carrier,label,search,token=PROFILE;profile=dict(carrier_id=carrier,label=label,search=search,token=token)
    retained(path,dict(season=season,release_id=build.RELEASE,manifest_sha256=actual.manifest_sha256,profiles=[profile],visual_approval=False))
    capture(0,0,folder=folder,release_id=build.RELEASE,run_tag=tag(season),season=season,profile=profile)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--season',choices=build.source.TARGETS,required=True)
    parser.add_argument('--previous-runner-pid',type=int,default=0)
    args=parser.parse_args();main(args.season,args.previous_runner_pid)
