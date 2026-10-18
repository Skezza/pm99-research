"""Retire only the full copied game from the completed independent replay.

Original inputs, replay recipe/receipts/scripts and installed releases stay
local. Restore the game from the Pi receipt if the archived evidence itself
needs reinspection; normal builds reconstruct from registered source inputs.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import archive_retired_season_tests_20261004 as archive
from scripts import season_pipeline_v2 as pipeline


def run(stage='native'):
    proof = ROOT / '.local/consolidated-audit-20261009/boreham-triple-full-rebuild-proof-v1.json'
    document = pipeline.read_json_file(proof)
    if not document.get('complete_game_inventory_identical'):
        raise ValueError('completed independent full-game rebuild proof required')
    names = {'native':'boreham-retirement-triple-native-replay-v2',
             'complete':'boreham-triple-exact-replay-complete-v1'}
    if stage not in names:
        raise ValueError('only independently proved private replay stages may be retired')
    name = names[stage]
    archive.WORKSPACE = ROOT / '.local/consolidated-audit-20261009' / name
    archive.TARGETS = ('game',)
    archive.RECEIPTS = ROOT / '.local/cleanup-20261010/boreham-private-replay' / stage
    # Preserve the first completed receipt's original location.
    if stage == 'native':archive.RECEIPTS = archive.RECEIPTS.parent
    archive.REMOTE = '/srv/hdd/pm99-archive/packages/private-replay-games/20261010/' + name
    if stage == 'native':archive.REMOTE = '/srv/hdd/pm99-archive/packages/private-replay-games/20261010/boreham-triple-native-replay-v2'
    archive.REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/' + name + '-20261010'
    if stage == 'native':archive.REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/boreham-triple-native-replay-v2-20261010'
    print(archive.archive('game', True), flush=True)


if __name__ == '__main__':
    run()
