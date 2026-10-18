import copy
import pytest
from scripts import plan_source_repaired_club_roster_v1 as plan


def fixture():
    player = {'id': 'p1', 'carrier_id': 20, 'club_id': 'club1',
        'name': 'A. PLAYER', 'source_name': 'Actual Player',
        'facts': {'birth_date': '1994-11-09'}}
    person = {'source_player_id': 99, 'name': 'Actual Player', 'birth_date': '1995-09-20'}
    return {'p1': player}, {99: person}


def test_full_source_name_conflict_is_exposed_without_approving_a_dob_waiver_or_mutating():
    players, people = fixture()
    before = copy.deepcopy((players, people))
    result = plan.local_dob_conflicts(players, 'club1', {99}, people, set())
    assert result[99]['player_id'] == 'p1'
    assert result[99]['after'] == '1995-09-20'
    assert result[99]['approved_for_native_write'] is False
    assert (players, people) == before


@pytest.mark.parametrize('problem', ['opponent', 'other-club', 'abbreviated-source-name',
    'no-source-name', 'same-DOB', 'two-local-players', 'two-public-people'])
def test_ambiguous_or_unbound_names_cannot_turn_into_existing_person_dob_repairs(problem):
    players, people = fixture()
    excluded = {'p1'} if problem == 'opponent' else set()
    if problem == 'other-club': players['p1']['club_id'] = 'club2'
    if problem == 'abbreviated-source-name': players['p1']['source_name'] = 'A. Player'
    if problem == 'no-source-name': players['p1'].pop('source_name')
    if problem == 'same-DOB': players['p1']['facts']['birth_date'] = people[99]['birth_date']
    if problem == 'two-local-players': players['p2'] = dict(players['p1'], id='p2', carrier_id=21)
    if problem == 'two-public-people': people[100] = dict(people[99], source_player_id=100)
    assert not plan.local_dob_conflicts(players, 'club1', set(people), people, excluded)
