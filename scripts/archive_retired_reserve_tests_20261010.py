"""Archive exact unregistered old tests, verifying every file before removal."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import archive_retired_season_tests_20261004 as archive
from scripts.archive_retired_compile_tests_20261007 import check_references

NAMES = ('2015-16-kit-factory-template-v4-native-hem-contour-game',
         '2000-01-canonical-compile-20260911-r10-game')


def run():
    archive.TARGETS = NAMES
    archive.RECEIPTS = ROOT / '.local/cleanup-20261010/retired-reserve-tests'
    archive.REMOTE = '/srv/hdd/pm99-archive/packages/retired-reserve-tests/20261010'
    archive.REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/retired-reserve-tests-20261010'
    inherited_guard = archive.guard
    def guard(source):
        inherited_guard(source)
        check_references(source)
    archive.guard = guard
    try:
        rows = []
        for name in NAMES:
            print(name, 'archive/verify/remove exact retired test', flush=True)
            row = archive.archive(name, True)
            rows.append(row)
            archive.save(archive.RECEIPTS / 'summary.json', {'rows': rows})
            print(row, flush=True)
    finally:
        archive.guard = inherited_guard


if __name__ == '__main__':
    run()
