import pytest
from scripts import refresh_historical_opening_club_labels_v1 as refresh


def test_renamed_cohort_uses_its_own_dated_source_not_the_old_labels_evidence():
    club = {'id': 'club-403', 'carrier_id': 403, 'name': 'Werder Bremen', 'roster_player_ids': []}
    old = {'club_id': 'club-403', 'carrier_id': 403, 'club': 'Hannover 96', 'status': 'opening-source-unavailable'}
    proof = {'manager': 'Thomas Schaaf', 'raw_sources': [], 'starting_xi': {}, 'substitutes': {}}
    update = {'club_id': 'club-403', 'carrier_id': 403, 'after': 'Werder Bremen', 'evidence': proof}
    rows, duplicates, counts = refresh.refreshed_rows([club], [], [old], [update], {403: (1930, 'Thomas Schaaf', 1)}, lambda x: None)
    assert rows[0]['evidence'] == proof
    assert rows[0]['club'] == 'Werder Bremen'
    assert rows[0]['manager_status'] == 'match'
    assert rows[0]['full_opening_roster_verified'] is False
    assert old['status'] == 'opening-source-unavailable'
    assert counts['manager:match'] == 1


def test_unplanned_club_change_cannot_inherit_the_previous_source_proof():
    with pytest.raises(ValueError, match='another club'):
        refresh.refreshed_rows([{'id': 'club-403', 'carrier_id': 403, 'name': 'Bremen'}], [],
            [{'club_id': 'club-403', 'carrier_id': 403, 'club': 'Hannover', 'status': 'opening-source-unavailable'}],
            [], {}, lambda x: None)
