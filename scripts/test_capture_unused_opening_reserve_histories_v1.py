import pytest
from scripts import capture_unused_opening_reserve_histories_v1 as reserve


@pytest.mark.parametrize('problem', ['unknown-DOB', 'unknown-position', 'already-used', 'already-queried', 'homonym'])
def test_query_candidates_refuse_missing_facts_repeated_people_and_ambiguity(problem):
    raw = {'name': 'Real Player', 'birth_date': '1980-01-01', 'position': 'D'}
    person = {'source_player_id': 10, 'name': raw['name'], 'birth_date': raw['birth_date']}
    people = {('realplayer', '1980-01-01'): {10: person}}
    used, known = set(), set()
    if problem == 'unknown-DOB': raw['birth_date'] = None
    if problem == 'unknown-position': raw['position'] = 'unknown'
    if problem == 'already-used': used.add(10)
    if problem == 'already-queried': known.add(10)
    if problem == 'homonym': people[('realplayer', '1980-01-01')][11] = dict(person, source_player_id=11)
    assert reserve.candidate_person(raw, people, used, known) is None


def test_exact_unused_published_person_can_be_queried_without_approving_membership():
    raw = {'name': 'Real Player', 'birth_date': '1980-01-01', 'position': 'M'}
    person = {'source_player_id': 10, 'name': raw['name'], 'birth_date': raw['birth_date']}
    assert reserve.candidate_person(raw, {('realplayer', raw['birth_date']): {10: person}}, set(), set()) == person
