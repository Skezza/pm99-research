import pytest

from scripts import closeout_historical_review_v1 as closeout


def test_completed_player_review_must_match_current_recipe():
    closeout.current_audit({'season': '2000-01', 'bindings': {'package_sha256': 'current'}}, '2000-01', 'current')
    with pytest.raises(ValueError, match='current recipe'):
        closeout.current_audit({'season': '2000-01', 'bindings': {'package_sha256': 'old'}}, '2000-01', 'current')


def test_club_collisions_include_foreign_and_playable_slots():
    rows = [{'club_id': id, 'status': 'original-first-fixture-reparsed', 'evidence': {'source_club_id': source}}
            for id, source in [('club-1', 55), ('club-2', 55), ('english-club-335', 1074), ('club-3301', 1074), ('club-3', 66)]]
    assert closeout.source_collisions(rows) == {'club-1', 'club-2', 'english-club-335', 'club-3301'}


def test_unverified_claims_do_not_become_source_collision_proof():
    assert closeout.source_collisions([{'club_id': 'club-1', 'status': 'opening-source-unavailable'}]) == set()
