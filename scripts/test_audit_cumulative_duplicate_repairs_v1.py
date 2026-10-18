import pytest
from scripts import audit_cumulative_duplicate_repairs_v1 as ledger


def test_cumulative_slot_count_is_not_a_sum_of_repeated_closeouts(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger.registry, 'relative_workspace_path', str)
    path = tmp_path / 'plan.json'
    path.write_text('{}')
    first = {'season': '2005-06', 'carrier_id': 1, 'player_id': 'p1', 'name': 'First', 'birth_date': '1980-01-01'}
    second = {'season': '2006-07', 'updates': [{'carrier_id': 1, 'player_id': 'p1',
        'replacement': {'source_player': {'name': 'Second', 'birth_date': '1980-01-01'}}}]}
    slots = ledger.merge_slots({'players': [first]}, [(path, second)])
    assert len(slots) == 2
    assert slots[('2005-06', 1)]['name'] == 'First'
    assert slots[('2006-07', 1)]['name'] == 'Second'


def test_repeat_correction_cannot_be_counted_as_another_fixed_slot(tmp_path):
    first = {'season': '2005-06', 'carrier_id': 1, 'player_id': 'p1', 'name': 'First', 'birth_date': '1980-01-01'}
    repeat = {'season': '2005-06', 'updates': [{'carrier_id': 1}]}
    with pytest.raises(ValueError, match='repeated correction'):
        ledger.merge_slots({'players': [first]}, [(tmp_path, repeat)])


def test_explicit_chained_correction_retains_history_without_inflating_slot_count():
    first = {'season': '2005-06', 'carrier_id': 1, 'player_id': 'p1',
        'name': 'First', 'birth_date': '1980-01-01'}
    allocation = {'carrier_id': 1, 'player_id': 'p1', 'before_recipe': {
        'carrier_id': 1, 'id': 'p1', 'name': 'F. First', 'source_name': 'First',
        'facts': {'birth_date': '1980-01-01'}},
        'replacement': {'source_player': {'name': 'Second', 'birth_date': '1981-01-01'}}}
    slots = ledger.merge_chained_slots({'players': [first]}, '2005-06', [allocation], {'sha256': 'bound'})
    assert len(slots) == 1
    updated = slots[('2005-06', 1)]
    assert updated['name'] == 'Second'
    assert updated['chained_disposition']['previous_corrected_identity']['name'] == 'First'
    retained = ledger.merge_slots({'players': [updated]}, [])
    assert retained[('2005-06', 1)]['chained_disposition'] == updated['chained_disposition']
    allocation['before_recipe']['source_name'] = 'Unrelated'
    with pytest.raises(ValueError, match='prior corrected identity'):
        ledger.merge_chained_slots({'players': [first]}, '2005-06', [allocation], {})


def test_chained_correction_rejects_repeated_or_misbound_slots():
    row = {'carrier_id': 1, 'player_id': 'p1', 'before_recipe': {
        'carrier_id': 1, 'id': 'p1', 'name': 'First', 'facts': {'birth_date': '1980-01-01'}},
        'replacement': {'source_player': {'name': 'Second', 'birth_date': '1981-01-01'}}}
    with pytest.raises(ValueError, match='repeats a carrier'):
        ledger.merge_chained_slots({'players': []}, '2005-06', [row, row], {})
    row['before_recipe']['carrier_id'] = 2
    with pytest.raises(ValueError, match='another native slot'):
        ledger.merge_chained_slots({'players': []}, '2005-06', [row], {})
