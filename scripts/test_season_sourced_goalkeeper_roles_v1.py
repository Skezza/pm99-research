import copy
import pytest
from scripts import season_sourced_goalkeeper_roles_v1 as module


def fixture():
    return {'players': [{'name': 'Real Goalkeeper', 'birth_date': '1980-02-03', 'position': 'G'}]}


def test_literal_G_full_identity_and_DOB_authorize_goalkeeper_role_not_a_side_guess():
    capture = fixture()
    before = copy.deepcopy(capture)
    assert module.original_keeper(capture, 'Real GOALKEEPER', '1980-02-03') == capture['players'][0]
    assert capture == before


@pytest.mark.parametrize('problem', ['initial', 'different-person', 'wrong-DOB', 'missing-DOB', 'outfielder', 'duplicate'])
def test_uncertain_identity_or_nonkeeper_is_not_authorized(problem):
    capture, name, birthday = fixture(), 'Real Goalkeeper', '1980-02-03'
    if problem == 'initial': name = 'R. Goalkeeper'
    if problem == 'different-person': name = 'Other Goalkeeper'
    if problem == 'wrong-DOB': birthday = '1981-02-03'
    if problem == 'missing-DOB': capture['players'][0]['birth_date'] = None
    if problem == 'outfielder': capture['players'][0]['position'] = 'M'
    if problem == 'duplicate': capture['players'].append(dict(capture['players'][0]))
    assert module.original_keeper(capture, name, birthday) is None


def test_case_accents_do_not_expand_a_shortened_name():
    capture = fixture(); capture['players'][0]['name'] = 'José Keeper'
    assert module.original_keeper(capture, 'José KEEPER', '1980-02-03') is not None
    assert module.original_keeper(capture, 'J. Keeper', '1980-02-03') is None
