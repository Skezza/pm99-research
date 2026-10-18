"""One genuine startup plus targeted keeper, birthday and position profiles."""
import argparse
from scripts import build_morecambe_owned_opening_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

TAG='morecambe_owned_opening_2000_01_r135a_20261017'
PROFILES=[(11002,'mark_smith','Mark Smith','Smith'),
    (10992,'kenny_takano','Kenny Takano','Takano'),
    (10995,'john_norman','John Norman','Norman'),
    (10996,'andy_banks','Andy Banks','Banks')]


def main(builder_pid):
    spec=build.ROOT/'runtime-profile-spec.json'
    if spec.exists():raise ValueError('existing Morecambe captures require inspection, not restart')
    wait_owned(builder_pid,'scripts.build_morecambe_owned_opening_20261017')
    if not (build.ROOT/'complete-SOURCE-replay.json').exists():
        raise ValueError('Morecambe builder stopped before complete SOURCE; no intermediate capture')
    release=build.source.registry.load_registered_release(build.SEASON,build.RELEASE)
    retained(spec,dict(season=build.SEASON,release_id=build.RELEASE,manifest_sha256=release.manifest_sha256,
        profiles=[dict(carrier_id=n,label=l,search=s,token=t) for n,l,s,t in PROFILES],visual_approval=False))
    for index,(carrier,label,search,token) in enumerate(PROFILES):
        capture(0,0,folder=build.ROOT,release_id=build.RELEASE,run_tag=TAG,season=build.SEASON,
            profile=dict(carrier_id=carrier,label=label,search=search,token=token),capture_startup=index==0)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder-pid',type=int,required=True)
    main(parser.parse_args().builder_pid)
