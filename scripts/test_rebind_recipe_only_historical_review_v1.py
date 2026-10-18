import copy
import pytest
from scripts.rebind_recipe_only_historical_review_v1 import assert_review_inputs_unchanged


def package():
    return {'players': [{'id': 'p1', 'facts': {'birth_date': '1990-01-01'}}],
            'clubs': [{'id': 'c1', 'name': 'Club', 'manager_id': 'old', 'roster_player_ids': ['p1']}],
            'managers': [{'id': 'old'}], 'artifacts': [], 'proofs': [], 'calendar': {'start_year': 2015}}


def test_manager_reference_only_change_can_reuse_unchanged_player_comparisons():
    before = package(); after = copy.deepcopy(before)
    after['clubs'][0]['manager_id'] = 'new'
    after['managers'] = [{'id': 'new'}]
    assert_review_inputs_unchanged(before, after)


@pytest.mark.parametrize('change', ['dob', 'club_name', 'roster', 'calendar', 'shape'])
def test_changed_player_or_club_inputs_cannot_inherit_a_prior_review(change):
    before = package(); after = copy.deepcopy(before)
    if change == 'dob': after['players'][0]['facts']['birth_date'] = '1991-01-01'
    if change == 'club_name': after['clubs'][0]['name'] = 'Different Club'
    if change == 'roster': after['clubs'][0]['roster_player_ids'] = ['p2']
    if change == 'calendar': after['calendar']['start_year'] = 2016
    if change == 'shape': after['extra'] = True
    with pytest.raises(ValueError, match='changed'):
        assert_review_inputs_unchanged(before, after)
