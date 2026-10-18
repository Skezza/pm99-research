"""Capture only the new final country game and its affected player."""
import argparse
from scripts import build_takano_period_country_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

TAG='takano_period_country_2000_01_r136a_20261017'
PROFILE=(10992,'takano_japan','Kenny Takano','Takano')


def main(builder_pid):
    path=build.ROOT/'runtime-profile-spec.json'
    if path.exists():raise ValueError('existing Takano country capture needs inspection, not restart')
    wait_owned(builder_pid,'scripts.build_takano_period_country_20261017')
    if not (build.ROOT/'complete-SOURCE-replay.json').exists():raise ValueError('country builder stopped before complete SOURCE proof')
    actual=build.source.registry.load_registered_release(build.SEASON,build.RELEASE)
    carrier,label,search,token=PROFILE
    profile=dict(carrier_id=carrier,label=label,search=search,token=token)
    retained(path,dict(season=build.SEASON,release_id=build.RELEASE,manifest_sha256=actual.manifest_sha256,profiles=[profile],visual_approval=False))
    capture(0,0,folder=build.ROOT,release_id=build.RELEASE,run_tag=TAG,season=build.SEASON,profile=profile)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder-pid',type=int,required=True)
    main(parser.parse_args().builder_pid)
