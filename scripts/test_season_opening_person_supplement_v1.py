import copy
from types import SimpleNamespace
import pytest
from scripts import season_opening_person_supplement_v1 as supplement


def inputs():
    clubs = [{'id': 'c', 'name': 'Example', 'carrier_id': 300, 'division': 'Premier League'}]
    evidence = {'c': {'starting_xi': {'42': 'Retired Player'}, 'substitutes': {}}}
    captures = [{'club_name': 'Example', 'country_catalog': 'eng',
                 'players': [{'name': 'Retired Player', 'birth_date': '1960-01-02'}]}]
    verifier = SimpleNamespace(verify=lambda _: {'status': 'raw-source-reparsed'})
    return {}, clubs, evidence, captures, verifier


def test_missing_retired_person_can_be_joined_without_inventing_transfer_history():
    args = inputs()
    original = copy.deepcopy(args[:-1])
    index, report = supplement.extend(*args)
    assert index[('retiredplayer', '1960-01-02')][42]['source_player_id'] == 42
    assert report['ownership_established'] is False
    assert len(report['added_identities']) == 1
    assert args[:-1] == original


def test_existing_transliteration_rules_are_shared_with_pinned_person_lookup():
    people, clubs, evidence, captures, verifier = inputs()
    evidence['c']['starting_xi']['42'] = 'Michał Example'
    captures[0]['players'][0]['name'] = 'Michal Example'
    index, _ = supplement.extend(people, clubs, evidence, captures, verifier)
    player = {'name': 'Michal Example', 'facts': {'birth_date': '1960-01-02'}}
    assert supplement.transfer.unique_person(player, index)['source_player_id'] == 42


def test_independently_sourced_name_variants_keep_one_published_person_record():
    people, clubs, evidence, captures, verifier = inputs()
    evidence['c']['substitutes']['42'] = 'Alternative Fullname'
    captures[0]['players'].append({'name': 'Alternative Fullname', 'birth_date': '1960-01-02'})
    index, report = supplement.extend(people, clubs, evidence, captures, verifier)
    assert len(report['added_identities']) == 2
    assert index[('alternativefullname', '1960-01-02')][42] == index[('retiredplayer', '1960-01-02')][42]


@pytest.mark.parametrize('problem', ['initial', 'wrong-club', 'wrong-country', 'unverified',
                                   'different-DOB', 'different-ID', 'two-published-IDs', 'two-source-DOBs'])
def test_ambiguous_or_unpublished_identity_is_never_added(problem):
    people, clubs, evidence, captures, verifier = inputs()
    if problem == 'initial': captures[0]['players'][0]['name'] = 'R Player'
    if problem == 'wrong-club': captures[0]['club_name'] = 'Other'
    if problem == 'wrong-country': captures[0]['country_catalog'] = 'italy'
    if problem == 'unverified': verifier.verify = lambda _: {'status': 'raw-capture-disagrees'}
    if problem in ('different-DOB', 'different-ID'):
        id = 42 if problem == 'different-DOB' else 99
        people[('retiredplayer', '1960-01-02')] = {id: {
            'source_player_id': id, 'name': 'Retired Player',
            'birth_date': '1970-01-02' if problem == 'different-DOB' else '1960-01-02'}}
    if problem == 'two-published-IDs': evidence['c']['substitutes']['43'] = 'Retired Player'
    if problem == 'two-source-DOBs': captures[0]['players'].append({'name': 'Retired Player', 'birth_date': '1970-01-02'})
    _, report = supplement.extend(people, clubs, evidence, captures, verifier)
    assert report['added_identities'] == []
