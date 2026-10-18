from types import SimpleNamespace
import pytest
from scripts import season_stoke_commons_number_v1 as subject


def fixture(monkeypatch):
    monkeypatch.setattr(subject, 'read_initial_order', lambda raw: SimpleNamespace(name='Kris COMMONS'))
    raw = bytearray(70); raw[2:5] = bytes.fromhex('dd6361')
    eq = bytearray(50)
    return [dict(id='p', carrier_id=27013, club_id='club', name='Kris Commons', source_name='Kris Commons',
        person_id='person-soccerbase-28633', facts=dict(birth_date='1983-08-30')),
        dict(id='club', carrier_id=375, name='Stoke City', roster_player_ids=['p']),
        raw, {27013: {375}}, {375:eq}, 24]


def test_native_family_capitals_preserved_not_mistaken_for_another_person(monkeypatch):
    subject.native_guard(*fixture(monkeypatch))


@pytest.mark.parametrize('field,value', [('person_id','person-soccerbase-28634'),
    ('source_name','Another Commons'), ('carrier_id',27012), ('club_id','different')])
def test_exact_identity_not_relaxed_with_name_case(monkeypatch, field, value):
    args = fixture(monkeypatch); args[0][field] = value
    with pytest.raises(ValueError, match='exact sourced identity'):
        subject.native_guard(*args)


@pytest.mark.parametrize('change', ['shared_owner','mode1','compact','unsourced_number','different_native_name'])
def test_foreign_layout_wrong_owners_and_unpublished_numbers_are_not_written(monkeypatch, change):
    args = fixture(monkeypatch)
    if change == 'shared_owner': args[3][27013].add(376)
    elif change == 'mode1': args[4][375][0x29] = 1
    elif change == 'compact': args[2][2:5] = bytes.fromhex('dd6360')
    elif change == 'unsourced_number': args[5] = 25
    else: monkeypatch.setattr(subject,'read_initial_order',lambda raw:SimpleNamespace(name='Wrong COMMONS'))
    with pytest.raises(ValueError, match='exact sourced identity'):
        subject.native_guard(*args)
