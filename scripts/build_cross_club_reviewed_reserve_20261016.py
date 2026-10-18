"""Build the reviewed winger/current-model candidate, not the generic trial."""
from scripts import advance_cross_club_reserves_20261016 as build
from scripts.cross_club_replacement_output_v1 import POLICY

ROOT = build.registry.ROOT / '.local/consolidated-audit-20261009/cross-club-reserves-20261016-v2'
SEASON = build.SEASON
RELEASE = 'sourced-reviewed-cross-club-reserves-20261016-r107a'
REPLAY = 'replayed-reviewed-cross-club-reserves-20261016-r107b'
TAG = 'cross_club_city_2000_r107a_20261016'


if __name__ == '__main__':
    build.main(root=ROOT, release_id=RELEASE, replay_id=REPLAY, output_review=POLICY)
