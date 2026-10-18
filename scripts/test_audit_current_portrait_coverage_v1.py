import pytest
from scripts import audit_current_portrait_coverage_v1 as audit


def test_native_playable_mode_wins_over_recipe_label():
    assert audit.ownership_group([1, 2], {1: 0, 2: 1}, {}) == 'playable'


def test_non_playable_english_is_not_overseas():
    clubs = {3300: {'carrier_id': 3300, 'division': 'preserve-existing-mode1-membership'}}
    assert audit.ownership_group([3300], {3300: 1}, clubs) == 'non-playable-english'


def test_non_playable_italian_club_is_overseas():
    clubs = {200: {'carrier_id': 200, 'division': 'preserve-existing-mode1-membership'}}
    assert audit.ownership_group([200], {200: 1}, clubs) == 'non-playable-overseas'


def test_unknown_owners_are_not_silently_called_overseas():
    assert audit.ownership_group([999], {999: 1}, {}) == 'non-playable-unclassified'


def test_existing_coverage_receipt_is_not_overwritten(tmp_path):
    path = tmp_path / 'receipt.json'
    path.write_text('{}')
    with pytest.raises(ValueError, match='immutable'):
        audit.run(path)
