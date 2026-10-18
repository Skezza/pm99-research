import copy
import pytest
from scripts import season_cross_club_reserve_repair_v1 as source


def pair():
    a = dict(carrier_id=1, club_id='city', id='p1', name='Andrei Kanchelskis',
        facts=dict(birth_date='1969-01-23'))
    b = dict(a, carrier_id=2, club_id='rangers', id='p2')
    first = dict(name='Andrei KANCHELSKIS', birth_date='1969-01-23', position='M', startup_order=16)
    second = dict(first, startup_order=5)
    return [a, b, first, second, {1: {311}, 2: {1251}},
        dict(carrier_id=311, roster_player_ids=['p1']),
        dict(carrier_id=1251, roster_player_ids=['p2'])]


def test_exact_cross_club_reserve_copy_and_unchanged_retained_starter_are_allowed():
    args = pair(); before = copy.deepcopy(args)
    source.guard_pair(*args)
    assert args == before


@pytest.mark.parametrize('field,value', [('startup_order', 1), ('startup_order', 11), ('position', 'G')])
def test_never_replace_a_starting_player_or_keeper(field, value):
    args = pair(); args[2][field] = value
    with pytest.raises(ValueError, match='starter or keeper'):
        source.guard_pair(*args)


@pytest.mark.parametrize('index,field,value', [(1, 'club_id', 'city'), (1, 'carrier_id', 1),
    (6, 'carrier_id', 311)])
def test_within_club_and_shared_carriers_are_not_a_cross_club_disposition(index, field, value):
    args = pair(); args[index][field] = value
    with pytest.raises(ValueError, match='distinct'):
        source.guard_pair(*args)


@pytest.mark.parametrize('changed', ['recipe-date', 'native-date', 'native-name', 'source-name',
    'shared-owner', 'wrong-owner', 'missing-declaration', 'duplicate-declaration'])
def test_identity_and_physical_ownership_proofs_cannot_be_waived(changed):
    args = pair()
    if changed == 'recipe-date': args[1]['facts'] = dict(birth_date='1968-01-23')
    if changed == 'native-date': args[3]['birth_date'] = '1968-01-23'
    if changed == 'native-name': args[2]['name'] = 'Another Player'
    if changed == 'source-name': args[1]['source_name'] = 'A. Kanchelskis'
    if changed == 'shared-owner': args[4][1].add(1251)
    if changed == 'wrong-owner': args[4][1] = {1251}
    if changed == 'missing-declaration': args[5]['roster_player_ids'] = []
    if changed == 'duplicate-declaration': args[5]['roster_player_ids'].append('p1')
    with pytest.raises(ValueError): source.guard_pair(*args)


def test_cross_club_dispatch_does_not_use_the_generic_transfer_policy(monkeypatch):
    from scripts import season_duplicate_ownership_delta_v1 as delta
    calls = []
    monkeypatch.setattr(source, 'verify_plan', lambda release, plan: calls.append((release, plan)))
    doc = dict(schema_version=source.SCHEMA)
    delta.verify_plan('release', doc)
    assert calls == [('release', doc)]
