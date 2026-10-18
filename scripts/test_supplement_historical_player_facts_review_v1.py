import pytest
from scripts import supplement_historical_player_facts_review_v1 as review


def fixture():
    player = {'id': 'p', 'name': 'Cristiano Ronaldo', 'carrier_id': 7, 'club_id': 'manu',
        'facts': {'birth_date': '1985-02-05', 'nationality': 'ENG', 'height_cm': 185, 'weight_kg': 80, 'shirt_number': 7}}
    previous = {'name': player['name'], 'carrier_id': 7, 'club_id': 'manu', 'birth_date': '1985-02-05',
        'fields': {field: {'recipe_value': value, 'source_values': []} for field, value in player['facts'].items() if field != 'birth_date'}}
    return player, previous


def test_supplement_finds_default_country_error_and_does_not_infer_shirt_number():
    player, old = fixture()
    extra = [{'club_id': 'other', 'facts': {'nationality': 'POR', 'shirt_number': 17}}]
    checks = review.refreshed_checks(player, old, extra)
    assert checks['nationality']['source_values'] == ['POR']
    assert checks['nationality']['status'] == 'conflict'
    assert checks['shirt_number']['status'] == 'no-independent-field-source'


def test_changed_fact_cannot_inherit_old_evidence():
    player, old = fixture(); player['facts']['height_cm'] = 195
    with pytest.raises(ValueError, match='fact changed'):
        review.refreshed_checks(player, old, [])


def test_existing_source_ambiguity_is_not_erased():
    player, old = fixture(); old['fields']['nationality']['source_values'] = ['POR', 'FRA']
    assert review.refreshed_checks(player, old, [])['nationality']['status'] == 'conflict-source-ambiguous'


def test_only_exact_authorised_country_amendment_can_reuse_prior_source_facts():
    player, old = fixture(); player['facts']['nationality'] = 'POR'
    old['fields']['nationality']['source_values'] = ['POR']
    amendment = {'player_id': 'p', 'carrier_id': 7, 'name': player['name'],
                 'birth_date': '1985-02-05', 'before': 'ENG', 'after': 'POR'}
    assert review.refreshed_checks(player, old, [], amendment)['nationality']['status'] == 'match'
    amendment['before'] = 'FRA'
    with pytest.raises(ValueError, match='bound amendment'):
        review.refreshed_checks(player, old, [], amendment)
