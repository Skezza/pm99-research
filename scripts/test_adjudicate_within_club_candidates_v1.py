"""Adversarial checks: a different birthday alone must never clear a duplicate."""
from scripts.adjudicate_within_club_candidates_v1 import classify


def person(birthday, verified=True, native=None):
    return {'recipe_date':birthday,'native_date':native or birthday,
            'original_squad_identity_verified':verified}


def test_different_source_and_native_identities_clear_duplicate_suspicion():
    assert classify([person('1992-07-05'),person('1999-04-20')]) == 'distinct-source-and-native-identities-not-a-duplicate'


def test_different_dates_without_original_squad_witness_remain_open():
    assert classify([person('1992-07-05'),person('1999-04-20',False)]) == 'unresolved-source-or-native-identity'


def test_recipe_source_match_with_wrong_native_birthday_remains_open():
    assert classify([person('1992-07-05'),person('1999-04-20',native='1967-04-20')]) == 'unresolved-source-or-native-identity'


def test_equal_native_dates_do_not_authorise_deletion():
    assert classify([person('1974-05-07'),person({'policy':'preserve-existing-mode1'},False,'1974-05-07')]) == 'same-name-and-native-birthday-needs-ownership-or-reserve-repair'


def test_preserved_dates_are_not_treated_as_sourced_literals():
    assert classify([person('1974-05-07'),person({'policy':'preserve-existing-mode1'},False,'1976-05-07')]) == 'unresolved-source-or-native-identity'


def test_unreadable_native_date_stays_unresolved():
    assert classify([person('1974-05-07'),{'recipe_date':'1976-05-07','native_date':None,
                    'original_squad_identity_verified':True}]) == 'unresolved-source-or-native-identity'
