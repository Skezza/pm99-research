import copy
import pytest
from scripts import season_stoke_original_alias_reserve_v1 as subject


def args():
    return ['2001-02', dict(id='club', name='Stoke City', carrier_id=375, roster_player_ids=['a', 'b']),
        dict(id='a', club_id='club', carrier_id=27013, name='Siarhei Shtaniuk'),
        dict(id='b', club_id='club', carrier_id=27002, name='Sergey Shtanyuk'),
        dict(name='Siarhei Shtaniuk', birth_date='1972-01-11', startup_order=22, position='D'),
        dict(name='Sergey Shtanyuk', birth_date='1973-08-13', startup_order=3, position='D'),
        {27013: {375}, 27002: {375}}, set(range(10)) | {27002}]


def test_specific_original_proofs_admit_false_DOB_without_relaxing_equal_DOB_policy():
    subject.pair_guard(*args())


@pytest.mark.parametrize('index,key,value', [(1, 'carrier_id', 376), (2, 'name', 'Another Shtaniuk'),
    (2, 'carrier_id', 27014), (4, 'birth_date', '1973-08-13'), (4, 'position', 'G'),
    (4, 'startup_order', 11), (5, 'position', 'M')])
def test_unreviewed_pair_or_changed_native_preimage_refused(index, key, value):
    values = args(); values[index][key] = value
    with pytest.raises(ValueError):
        subject.pair_guard(*values)


def test_shared_owner_refused():
    values = args(); values[6][27013].add(376)
    with pytest.raises(ValueError, match='exclusive'):
        subject.pair_guard(*values)


def test_actual_starting_member_refused_even_with_late_order_byte():
    values = args(); values[7].remove(0); values[7].add(27013)
    with pytest.raises(ValueError, match='starter'):
        subject.pair_guard(*values)


def test_no_stoke2002_shortcut_with_third_foreign_copy():
    values = args(); values[0] = '2002-03'
    with pytest.raises(ValueError):
        subject.pair_guard(*values)


def test_dispatch_replays_sources_instead_of_trusting_schema(monkeypatch):
    from scripts import season_duplicate_ownership_delta_v1 as delta
    calls = []
    monkeypatch.setattr(subject, 'prepare', lambda base: calls.append(base) or {'schema_version': subject.SCHEMA})
    plan = {'schema_version': subject.SCHEMA}
    delta.verify_plan('fixture-parent', plan)
    assert calls == ['fixture-parent']
    with pytest.raises(ValueError, match='reproduce'):
        delta.verify_plan('fixture-parent', dict(plan, injected='unreviewed edit'))
