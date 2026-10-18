"""Shared stock player retirement must not become a global deletion shortcut."""
import copy

import pytest

from scripts import review_factory_fallthrough_duplicate_v1 as review


def fixture():
    person = dict(id='player-4092', carrier_id=4092, club_id='target', policy='preserve-existing-mode1')
    clubs = [dict(id='target', carrier_id=221, roster_player_ids=['player-4092']),
             dict(id='other', carrier_id=250, roster_player_ids=['player-4092'],
                  shared_preserve_player_ids=['player-4092'])]
    return {'clubs': clubs}, person


@pytest.mark.parametrize('problem', [None, 'third-owner', 'missing-native-owner',
    'wrong-policy', 'hidden-row', 'repeated-row', 'missing-shared-declaration', 'absent-target'])
def test_shared_fallback_requires_exact_two_declared_visible_native_owners(monkeypatch, problem):
    package, person = fixture()
    owners = {4092: {221, 250}}
    rows = [(4092, 0)]
    target = 221
    if problem == 'third-owner': owners[4092].add(251)
    if problem == 'missing-native-owner': owners[4092].remove(250)
    if problem == 'wrong-policy': person['policy'] = 'authored'
    if problem == 'hidden-row': rows = [(4092, 1)]
    if problem == 'repeated-row': rows *= 2
    if problem == 'missing-shared-declaration': package['clubs'][1]['shared_preserve_player_ids'] = []
    if problem == 'absent-target': target = 999
    monkeypatch.setattr(review.source.ownership, 'native_owners', lambda eq: owners)
    monkeypatch.setattr(review.source.native, 'roster_rows', lambda eq, id: (None, None, rows))
    before = copy.deepcopy(package)
    if problem:
        with pytest.raises(ValueError): review.shared_fallback_membership(package, b'eq', person, target)
    else:
        result = review.shared_fallback_membership(package, b'eq', person, target)
        assert result['surviving_club_id'] == 'other'
        assert result['native_owners_before'] == [221, 250]
    assert package == before


def test_an_unreviewed_shared_carrier_is_not_retired_on_other_club_presence(monkeypatch):
    package = {'players': [{'carrier_id': 999, 'name': 'Someone'}]}
    monkeypatch.setattr(review.source.ownership, 'native_owners', lambda eq: {999: {221, 250}})
    monkeypatch.setattr(review.source.native, 'roster_rows', lambda eq, id: (None, None, [(999, 0)]))
    monkeypatch.setattr(review.source.facts, 'native_facts', lambda jug, id: {'birth_date': '1977-02-08'})
    from types import SimpleNamespace
    with pytest.raises(ValueError, match='unreviewed shared'):
        review.shared_other_club_retirements(SimpleNamespace(season='2001-02'), package,
            {'carrier_id': 221}, {}, None, {}, {}, b'jug', b'eq', b'factory', None, {})
