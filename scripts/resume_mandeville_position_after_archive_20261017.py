"""Continue only the known unbuilt reserve stop, then capture the real game."""
import argparse
from pathlib import Path
import time

from scripts import season_release_registry_v1 as registry
from scripts import build_exact_position_batch_20261017 as build
from scripts.capture_exact_position_batch_20261017 import main as capture
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ARCHIVE=registry.ROOT/'.local/cleanup-20261017/cold-transfer-reviews-to-pi/completed.json'
ROOT=build.ROOT/'position-resume-after-archive'


def main(archive_pid):
    if ROOT.exists():raise ValueError('existing position resume needs inspection, not restart')
    ROOT.mkdir()
    retained(ROOT/'input.json',dict(archive_pid=archive_pid,season='2017-18',target_carrier=10683,
        previous_build_tool_session=29307,previous_build_terminal_exit=1,
        native_build_previously_started=False,no_completed_game_regeneration=True))
    while not ARCHIVE.exists():
        try:command=Path(f'/proc/{archive_pid}/cmdline').read_bytes()
        except FileNotFoundError as exc:
            raise ValueError('cold report archive stopped without completion; inspect instead of bypassing reserve') from exc
        if b'scripts.archive_cold_transfer_reviews_to_pi_20261017' not in command:
            raise ValueError('cold report archive PID identity changed')
        time.sleep(10)
    input_plan=registry.ROOT/'.local/consolidated-audit-20261009/2017-visible-followups-20261017/10683-position-plan.json'
    build.main('2017-18','sourced-resolved-period-country-20261017-r130a',[10683],input_plan,resume_source_only=True)
    capture('2017-18',0)
    retained(ROOT/'completed.json',dict(actual_position_game_and_SOURCE_complete=True,
        original_startup_and_changed_profile_captured=True,original_ROOT_review_pending=True,
        preferred_writes=0,source_admission_not_repeated_as_new_progress=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-pid',type=int,required=True)
    main(parser.parse_args().archive_pid)
