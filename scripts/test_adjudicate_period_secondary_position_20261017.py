import copy
import pytest
from scripts import adjudicate_period_secondary_position_20261017 as subject


def fixture():
    player = dict(name='#17 Dion Donohue', source_name='Dion Donohue', facts=dict(
        birth_date='1993-08-26', primary_position='D', fine_roles=[2, 9]))
    native = dict(position='D', roles=[2, 9, 98, 98, 98, 98])
    fifa = dict(long_name='Dion James Donohue', dob='1993-08-26', player_positions='LB, CM')
    annual = [dict(name='Dion Donohue', birth_date='1993-08-26', position='M')]
    return player, native, fifa, annual


def test_secondary_midfield_role_explains_warning_without_touching_left_back():
    values = fixture(); original = copy.deepcopy(values)
    result = subject.confirm(*values)
    assert result['native_changes_required'] is False
    assert result['fine_roles'] == [2, 9]
    assert result['August_ownership_or_match_deployment_approved'] is False
    assert values == original


@pytest.mark.parametrize('problem', ['birthday', 'primary', 'missing-secondary',
    'wrong-person', 'annual-birthday', 'unsupported-broad', 'no-original', 'no-conflict'])
def test_cannot_dispose_a_real_position_or_identity_problem(problem):
    player, native, fifa, annual = fixture()
    if problem == 'birthday': fifa['dob'] = '1993-08-25'
    if problem == 'primary': native['position'] = 'M'
    if problem == 'missing-secondary': native['roles'] = [2, 98, 98, 98, 98, 98]
    if problem == 'wrong-person': annual[0]['name'] = 'Michael Donohue'
    if problem == 'annual-birthday': annual[0]['birth_date'] = '1993-08-25'
    if problem == 'unsupported-broad': annual[0]['position'] = 'F'
    if problem == 'no-original': annual = []
    if problem == 'no-conflict': annual[0]['position'] = 'D'
    with pytest.raises(ValueError): subject.confirm(player, native, fifa, annual)
