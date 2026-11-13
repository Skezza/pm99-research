"""Archive reviewed superseded October 4 generated reports, with recovery ledger."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import json_storage_io_v1 as storage_io
from scripts import archive_retired_season_tests_20261004 as archive
from scripts.archive_retired_compile_tests_20261007 import check_references
from scripts.archive_superseded_ingress_games_20261004 import nested_strings

NAME = 'historical-player-facts-audit-20261004-r1'


def run(name=NAME):
    if name not in (NAME, 'historical-roster-audit-20261004-r1', 'historical-roster-audit-20261004-r6',
                    'historical-roster-audit-20261004-r8'):
        raise ValueError('not an explicitly reviewed superseded generated-report target')
    archive.TARGETS = (name,)
    archive.WORKSPACE = ROOT / '.local'
    archive.RECEIPTS = ROOT / '.local/cleanup-20261010/superseded-fact-reports' / (name if name != NAME else '')
    archive.REMOTE = '/srv/hdd/pm99-archive/packages/superseded-fact-reports/20261010'
    archive.REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/superseded-fact-reports-20261010' + ('/' + name if name != NAME else '')
    inherited = archive.guard

    def guard(source):
        inherited(source)
        check_references(source)
        suffixes = ('.json', '.csv') if name.startswith('historical-roster-audit-') else ('.json',)
        if any(p.is_symlink() or (storage_io.is_file(p) and p.suffix not in suffixes and not p.name.endswith('.json.zst'))
               for p in storage_io.glob(source, '*', recursive=True)):
            raise ValueError('superseded report tree contains non-report data or symlinks')
        for loc in storage_io.glob(archive.registry.LOCAL_ROOT / 'releases', '*/*/locator.json'):
            if any(name in v for v in nested_strings(json.loads(storage_io.read_text(loc)))):
                raise ValueError('registered historical release references these reports')
        roots = [ROOT / '.local' / name for name in (
            'historical-role-deltas-v1', 'season-release-registry-v1',
            'critical-path-repairs-20261007', 'editorial-closeout-20261008',
            'consolidated-audit-20261009')]
        reference = storage_io.find_json_reference(roots, name)
        if reference is not None:
            raise ValueError('report reference scan found a retained reference: '+str(reference))

    archive.guard = guard
    try:
        print('Archive/verify/remove superseded generated fact reports only', flush=True)
        row = archive.archive(name, True)
        archive.save(archive.RECEIPTS / 'summary.json', row)
        print(row, flush=True)
    finally:
        archive.guard = inherited


if __name__ == '__main__':
    run()
