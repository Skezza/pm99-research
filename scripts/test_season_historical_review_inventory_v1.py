from scripts.season_historical_review_inventory_v1 import unresolved


def test_all_positive_whole_season_checks_are_still_not_august_certification():
    row = {'same_club_season_identity_match': True, 'august_ownership_verified': False,
           'fields': {'nationality': {'status': 'match'}}}
    assert unresolved(row) == ['opening-squad-ownership-unverified']


def test_ambiguity_and_missing_sources_are_not_hidden():
    row = {'same_club_season_identity_match': False, 'august_ownership_verified': False,
           'fields': {'nationality': {'status': 'compatible-but-source-ambiguous'},
                      'height_cm': {'status': 'no-independent-field-source'}}}
    assert 'nationality:compatible-but-source-ambiguous' in unresolved(row)
    assert 'height_cm:no-independent-field-source' in unresolved(row)
    assert 'club-season-identity-unverified' in unresolved(row)
