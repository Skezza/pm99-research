from scripts.season_cached_manager_repairs_20261016 import exclusive_source_clubs


def row(id,source,playable=False):
    return dict(club_id=id,status='original-first-fixture-reparsed',playable=playable,
        evidence=dict(source_club_id=source))


def test_foreign_duplicates_are_not_arbitrarily_assigned():
    assert exclusive_source_clubs([row('a',1),row('b',1)])==set()


def test_exclusive_club_and_one_playable_carrier_are_unambiguous():
    assert exclusive_source_clubs([row('a',1),row('b',2),row('c',2,True)])=={'a','c'}


def test_two_playable_representations_are_not_tie_broken():
    assert exclusive_source_clubs([row('a',1,True),row('b',1,True)])==set()


def test_absent_original_manager_proof_never_confers_exclusivity():
    absent=row('a',1);absent['status']='opening-source-unavailable'
    assert exclusive_source_clubs([absent])==set()
