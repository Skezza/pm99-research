"""Capture actual corrected games sequentially on the single remote lane."""
import argparse
from pathlib import Path
import time
from scripts import build_kiraly_period_profiles_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def tag(season):return 'kiraly_period_profile_'+season.replace('-','_')+'_r141a_20261017'
def profile(season):
    # Native surname is accented in 2004 onward; PM99 search is accent-sensitive.
    search='KIRÁLY' if int(season[:4])>=2004 else 'Kiraly'
    return (build.source.TARGETS[season],'kiraly_hungary_keeper',search,'Kiraly')


def one(season,builder_pid):
    folder=build.ROOT/season;path=folder/'runtime-profile-spec.json'
    if path.exists():raise ValueError('existing Kiraly capture must be inspected, not restarted')
    while not (folder/'complete-SOURCE-replay.json').exists():
        command=Path('/proc')/str(builder_pid)/'cmdline'
        try:raw=command.read_bytes()
        except FileNotFoundError as exc:raise ValueError('builder not live and complete SOURCE missing; inspect partial state') from exc
        if b'scripts.build_kiraly_period_profiles_20261017' not in raw:
            raise ValueError('expected country builder PID identity changed')
        time.sleep(10)
    actual=build.source.registry.load_registered_release(season,build.RELEASE)
    carrier,label,search,token=profile(season);spec=dict(carrier_id=carrier,label=label,search=search,token=token)
    retained(path,dict(season=season,release_id=build.RELEASE,manifest_sha256=actual.manifest_sha256,profiles=[spec],visual_approval=False))
    capture(0,0,folder=folder,release_id=build.RELEASE,run_tag=tag(season),season=season,profile=spec)
    print(dict(season=season,actual_country_keeper_profile_captured=True,original_visual_review_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seasons',nargs='+',choices=build.source.TARGETS,required=True)
    parser.add_argument('--builder-pid',type=int,default=0);parser.add_argument('--previous-runner-pid',type=int,default=0)
    parser.add_argument('--previous-runner-module',default='scripts.hertha2001_cohort_label_20261017')
    args=parser.parse_args()
    if len(args.seasons)!=len(set(args.seasons)):parser.error('unique explicit capture seasons required')
    wait_owned(args.previous_runner_pid,args.previous_runner_module)
    for season in args.seasons:one(season,args.builder_pid)
