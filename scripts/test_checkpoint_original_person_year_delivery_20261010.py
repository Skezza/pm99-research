"""Adversarial frozen-identity accounting before any preferred mutation."""
import copy
import pytest
from scripts.checkpoint_original_person_year_delivery_20261010 import validate_frozen_birthdays


def fixture():
    result = {'work_items': [{'id': 'birthdays', 'frozen_baseline': {'count': 247},
        'verified_repairs': [{'season': '2025-26', 'carrier_id': i} for i in range(205)]}]}
    updates = [{'season': '2025-26', 'carrier_id': i} for i in range(205, 218)]
    original = {'seasons': [{'season': '2025-26', 'failures': [{'carrier_id': i} for i in range(247)]}]}
    after = [{'season': '2025-26', 'failure_count': 29,
        'failures': [{'carrier_id': i} for i in range(218, 247)]}]
    return result, after, updates, original


def test_exact_frozen_identity_reduction():
    assert validate_frozen_birthdays(*fixture()) == 29


@pytest.mark.parametrize('mutation', ['new-case', 'swapped-case', 'duplicate-count', 'false-counter', 'denominator'])
def test_equal_or_attractive_numbers_cannot_mask_drift(mutation):
    result, after, updates, original = copy.deepcopy(fixture())
    if mutation == 'new-case':
        after[0]['failures'][-1]['carrier_id'] = 999999
    elif mutation == 'swapped-case':
        after[0]['failures'][-1]['carrier_id'] = 0
    elif mutation == 'duplicate-count':
        updates.append(copy.deepcopy(updates[-1]))
    elif mutation == 'false-counter':
        after[0]['failure_count'] = 28
    else:
        result['work_items'][0]['frozen_baseline']['count'] = 246
    with pytest.raises(ValueError, match='frozen birthday'):
        validate_frozen_birthdays(result, after, updates, original)
