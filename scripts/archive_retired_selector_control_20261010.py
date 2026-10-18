"""Retire one obsolete, unregistered August selector test after Pi verification."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import archive_retired_season_tests_20261004 as archive
from scripts.archive_retired_compile_tests_20261007 import check_references

NAME='selector-variable-team-control'


def run():
    archive.WORKSPACE=ROOT/'.local'
    archive.TARGETS=(NAME,)
    archive.RECEIPTS=ROOT/'.local/cleanup-20261010/retired-selector-control'
    archive.REMOTE='/srv/hdd/pm99-archive/packages/retired-selector-control/20261010'
    archive.REMOTE_RECEIPTS='/srv/hdd/pm99-archive/receipts/retired-selector-control-20261010'
    original=archive.guard
    def guard(source):
        original(source)
        check_references(source)
        if not (source/'game').is_dir() or (source/'game').is_symlink() or archive._active_game(source/'game'):
            raise ValueError('old selector game missing, symlinked or active')
        for path in (archive.registry.LOCAL_ROOT/'releases').glob('*/*/locator.json'):
            value=json.loads(path.read_text()).get('game_path')
            if value and (ROOT/value).resolve().is_relative_to(source.resolve()):
                raise ValueError('registered historical game lies inside selector test')
    archive.guard=guard
    try:
        print(archive.archive(NAME,True),flush=True)
    finally:
        archive.guard=original


if __name__=='__main__':
    run()
