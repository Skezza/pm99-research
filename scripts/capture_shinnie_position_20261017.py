"""Capture the actual midfield game after the existing country evidence job."""
import argparse

from scripts import build_shinnie_position_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture

TAG = 'shinnie_exact_midfield_2021_22_r126a_20261017'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-runner-pid', type=int, required=True)
    args = parser.parse_args()
    if not (build.ROOT/'complete-SOURCE-replay.json').exists():
        raise ValueError('actual midfield native/SOURCE game required before capture')
    capture(0, args.previous_runner_pid, folder=build.ROOT, release_id=build.RELEASE, run_tag=TAG,
        previous_runner_module='scripts.capture_shinnie_country_20261017')
