"""Archive two unregistered 2008 build-plan tests, with current-reference guards."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import archive_retired_season_tests_20261004 as archive
from scripts.archive_retired_compile_tests_20261007 import check_references

NAMES=('2008-09-build-plan-20260907-r1-game',
       '2008-09-build-plan-calendar-20260907-r1-game')


def run():
    archive.TARGETS=NAMES
    archive.RECEIPTS=ROOT/'.local/cleanup-20261009/retired-buildplan-games'
    archive.REMOTE='/srv/hdd/pm99-archive/packages/retired-buildplan-games/20261009'
    archive.REMOTE_RECEIPTS='/srv/hdd/pm99-archive/receipts/retired-buildplan-games-20261009'
    inherited_guard=archive.guard
    def guard(source):
        inherited_guard(source)
        check_references(source)
    archive.guard=guard
    try:
        rows=[]
        for name in NAMES:
            print(name,'archive/verify/remove exact retired test',flush=True)
            row=archive.archive(name,True)
            rows.append(row)
            archive.save(archive.RECEIPTS/'summary.json',{'rows':rows})
            print(row,flush=True)
    finally:
        archive.guard=inherited_guard


if __name__=='__main__':
    run()
