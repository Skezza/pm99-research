"""Capture genuine startup and restored non-playable club identity."""
import argparse
from scripts import build_original_carrier_label_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture, wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

TAG = 'original_carrier_label_2000_01_r134a_20261017'
PROFILE = dict(carrier_id=10987, label='morecambe_label', search='John Hardiker', token='Hardiker')


def main(builder_pid):
    folder = build.ROOT/build.SEASON
    if (folder/'runtime-profile-spec.json').exists():
        raise ValueError('existing club label capture needs inspection, not restart')
    if builder_pid:
        wait_owned(builder_pid, 'scripts.build_original_carrier_label_20261017')
    if not (folder/'complete-SOURCE-replay.json').exists():
        raise ValueError('actual label SOURCE proof incomplete; do not launch an intermediate')
    release = build.source.registry.load_registered_release(build.SEASON, build.RELEASE)
    retained(folder/'runtime-profile-spec.json', dict(season=build.SEASON, release_id=build.RELEASE,
        manifest_sha256=release.manifest_sha256, profiles=[PROFILE], visual_approval=False))
    capture(0, 0, folder=folder, release_id=build.RELEASE, run_tag=TAG,
        season=build.SEASON, profile=PROFILE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder-pid', type=int, default=0)
    main(parser.parse_args().builder_pid)
