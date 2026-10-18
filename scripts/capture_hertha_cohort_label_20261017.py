"""Capture final Hertha label game and a source-bound retained club player."""
import argparse
from scripts import build_hertha_cohort_label_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

TAG='hertha_cohort_label_2000_01_r137a_20261017'
PROFILE=(12468,'hertha_preetz','Preetz','Preetz')


def main(builder_pid):
    path=build.ROOT/'runtime-profile-spec.json'
    if path.exists():raise ValueError('existing Hertha capture needs inspection, not restart')
    wait_owned(builder_pid,'scripts.build_hertha_cohort_label_20261017')
    if not (build.ROOT/'complete-SOURCE-replay.json').exists():raise ValueError('Hertha builder stopped before full SOURCE proof')
    actual=build.source.registry.load_registered_release(build.SEASON,build.RELEASE)
    carrier,label,search,token=PROFILE;profile=dict(carrier_id=carrier,label=label,search=search,token=token)
    retained(path,dict(season=build.SEASON,release_id=build.RELEASE,manifest_sha256=actual.manifest_sha256,profiles=[profile],visual_approval=False))
    capture(0,0,folder=build.ROOT,release_id=build.RELEASE,run_tag=TAG,season=build.SEASON,profile=profile)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder-pid',type=int,required=True)
    main(parser.parse_args().builder_pid)
