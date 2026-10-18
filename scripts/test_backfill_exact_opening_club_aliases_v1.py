from scripts import backfill_exact_opening_club_aliases_v1 as backfill


def test_only_unique_explicit_alias_in_correct_country_is_used():
    club = {'name': 'Sparta Praha', 'full_name': 'Sparta Praha', 'carrier_id': 1452,
            'division': 'preserve-existing-mode1-membership'}
    row = {'source_selector': {'country_catalog': 'czech', 'club_name': 'Sparta Prague',
                               'transfermarkt_club_id': 197}}
    assert backfill.unique_capture(club, [row]) == row
    assert backfill.unique_capture(club, [row, row]) is None
    other = {'source_selector': dict(row['source_selector'], country_catalog='eng')}
    assert backfill.unique_capture(club, [other]) is None
    fuzzy = {'source_selector': dict(row['source_selector'], club_name='Sparta Other')}
    assert backfill.unique_capture(club, [fuzzy]) is None


def test_foreign_namespace_without_original_numeric_club_id_is_not_invented():
    club = {'name': 'Sparta Praha', 'carrier_id': 1452, 'division': 'preserve-existing-mode1-membership'}
    row = {'source_selector': {'country_catalog': 'czech', 'club_name': 'Sparta Prague', 'other_id': 197}}
    assert backfill.unique_capture(club, [row]) is None
