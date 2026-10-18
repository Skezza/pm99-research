"""Archive one unregistered failed September build; preserve current games."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import archive_retired_season_tests_20261004 as archive
from scripts.archive_retired_compile_tests_20261007 import check_references
from scripts.archive_superseded_ingress_games_20261004 import nested_strings
from scripts.season_art_transaction_v1 import _active_game

NAME = 'rc-quality-20260913-r1-failed-date-gate'


def run():
    archive.TARGETS = (NAME,)
    archive.WORKSPACE = ROOT / '.local/incomplete-season-release-builds-v1/2004-05'
    archive.RECEIPTS = ROOT / '.local/cleanup-20261010/failed-date-gate'
    archive.REMOTE = '/srv/hdd/pm99-archive/packages/failed-date-gate/20261010'
    archive.REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/failed-date-gate-20261010'
    inherited = archive.guard
    def guard(source):
        inherited(source)
        check_references(source)
        if any(p.is_symlink() for p in source.rglob('*')):
            raise ValueError('failed build contains an unresolved symbolic link')
        for exe in source.rglob('MANAGPRE.EXE'):
            if _active_game(exe.parent):
                raise ValueError('failed build contains a running game')
        for loc in (archive.registry.LOCAL_ROOT / 'releases').glob('*/*/locator.json'):
            row = json.loads(loc.read_text())
            if any(source.name in v for v in nested_strings(row)):
                raise ValueError('registered historical input references failed build')
            game = (ROOT / row.get('game_path', '.')).resolve()
            if game == source.resolve() or source.resolve() in game.parents:
                raise ValueError('registered historical game is inside failed build')
    archive.guard = guard
    try:
        print('Archive/verify/remove exact unregistered failed date-gate tree', flush=True)
        row = archive.archive(NAME, True)
        archive.save(archive.RECEIPTS / 'summary.json', row)
        print(row, flush=True)
    finally:
        archive.guard = inherited


if __name__ == '__main__':
    run()
