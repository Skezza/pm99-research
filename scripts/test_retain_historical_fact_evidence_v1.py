import copy
import pytest
from scripts import retain_historical_fact_evidence_v1 as retain


def row(club='Old Club'):
    return {'player_id': 'p1', 'name': 'Player', 'carrier_id': 1, 'birth_date': '1990-01-01', 'club_id': 'c1', 'club': club,
        'same_club_season_identity_match': False, 'evidence': [],
        'fields': {field: {'recipe_value': 'NED' if field == 'nationality' else 7, 'source_values': []}
            for field in retain.facts.FIELDS}}


def test_retains_exact_identity_country_but_not_old_club_shirt_number():
    old, new = row(), row('Restored Club')
    old['fields']['nationality']['source_values'] = ['NED']
    old['fields']['shirt_number']['source_values'] = [7]
    old['same_club_season_identity_match'] = True
    before = copy.deepcopy((old, new)); result = retain.merge(old, new)
    assert result['fields']['nationality']['status'] == 'match'
    assert result['fields']['shirt_number']['source_values'] == []
    assert result['same_club_season_identity_match'] is False
    assert (old, new) == before


def test_changed_fact_or_identity_cannot_inherit_a_prior_comparison():
    old, new = row(), row()
    new['birth_date'] = '1991-01-01'
    with pytest.raises(ValueError, match='identity'): retain.merge(old, new)
    new = row(); new['fields']['height_cm']['recipe_value'] = 180
    with pytest.raises(ValueError, match='changed fact'): retain.merge(old, new)
