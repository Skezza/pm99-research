"""Capture final alias+shirt game, not its intermediate predecessor."""
import argparse
from scripts import capture_stoke_original_alias_reserve_20261016 as capture
from scripts.build_stoke_commons_number_20261016 import ROOT, RELEASE


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait-manager-sweep-pid', type=int)
    args = parser.parse_args()
    capture.ROOT = ROOT
    capture.RELEASE = RELEASE
    capture.TAG = 'stoke_commons_number_2001_02_r118a_20261016'
    capture.main(args.wait_manager_sweep_pid)
