"""Capture corrected actual Haladas keeper without a full-squad approval."""
import argparse
from scripts import build_haladas2000_opening_keeper_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

TAG='haladas2000_opening_keeper_r139a_20261017'
PROFILE=(8507,'haladas_kurucsai','Kurucsai','Kurucsai')
PROFILES=[PROFILE,(2211,'hertha_kiraly_retained','Kiraly','Kiraly')]


def main(previous_runner_pid,builder_pid=0):
    path=build.ROOT/'runtime-profile-spec.json'
    if path.exists():raise ValueError('existing Haladas runner capture needs inspection, not restart')
    wait_owned(builder_pid,'scripts.build_haladas2000_opening_keeper_20261017')
    if not (build.ROOT/'complete-SOURCE-replay.json').exists():raise ValueError('Haladas native and complete SOURCE proof required')
    wait_owned(previous_runner_pid,'scripts.capture_preetz_period_profile_20261017')
    actual=build.source.registry.load_registered_release('2000-01',build.RELEASE)
    profiles=[dict(carrier_id=carrier,label=label,search=search,token=token) for carrier,label,search,token in PROFILES]
    retained(path,dict(season='2000-01',release_id=build.RELEASE,manifest_sha256=actual.manifest_sha256,profiles=profiles,visual_approval=False))
    for index,profile in enumerate(profiles):
        capture(0,0,folder=build.ROOT,release_id=build.RELEASE,run_tag=TAG,season='2000-01',profile=profile,capture_startup=index==0)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--previous-runner-pid',type=int,default=0)
    parser.add_argument('--builder-pid',type=int,default=0)
    args=parser.parse_args();main(args.previous_runner_pid,args.builder_pid)
