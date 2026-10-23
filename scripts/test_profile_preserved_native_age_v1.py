from types import SimpleNamespace

import pytest

from scripts.verify_profile_skill_digits_v1 import expected_profile_age
from scripts import season_within_club_reserve_repair_v1 as native


def test_recipe_date_remains_the_default_age_basis():
    release = SimpleNamespace(season='2000-01')
    player = {'carrier_id': 1, 'facts': {'birth_date': '1974-07-12'}}
    assert expected_profile_age(release, player) == {'expected_age': 26, 'basis': 'recipe-birthday'}


def test_preserve_is_not_silently_approved():
    player = {'carrier_id': 1, 'facts': {'birth_date': {'policy': 'preserve-existing-mode1'}}}
    with pytest.raises(ValueError, match='explicit native-preserve'):
        expected_profile_age(SimpleNamespace(season='2000-01'), player)


def test_explicit_preserve_checks_native_age_without_certifying_history(tmp_path, monkeypatch):
    (tmp_path/'DBDAT').mkdir()
    (tmp_path/'DBDAT/JUG98030.FDI').write_bytes(b'synthetic immutable input')
    monkeypatch.setattr(native, 'native_facts', lambda raw, carrier:
        {'birth_date': '1974-07-12'} if (raw, carrier) == (b'synthetic immutable input', 1) else {})
    player = {'carrier_id': 1, 'facts': {'birth_date': {'policy': 'preserve-existing-mode1'}}}
    result = expected_profile_age(SimpleNamespace(season='2000-01', game_path=tmp_path),
        player, allow_preserved_native_birthdate=True)
    assert result['expected_age'] == 26 and result['native_birth_date'] == '1974-07-12'
    assert result['historical_birthday_certified'] is False


@pytest.mark.parametrize('value', [None, 42, {}, {'policy': 'guess'},
    {'policy': 'preserve-existing-mode1', 'unexpected': True}])
def test_malformed_values_are_not_native_preserve_permission(value):
    with pytest.raises(ValueError):
        expected_profile_age(SimpleNamespace(season='2000-01'),
            {'carrier_id': 1, 'facts': {'birth_date': value}},
            allow_preserved_native_birthdate=True)


@pytest.mark.parametrize('opt_in', ['false', 'true', 1, None, [], {}])
def test_preserve_permission_must_be_literal_true(opt_in):
    with pytest.raises(ValueError, match='explicit native-preserve'):
        expected_profile_age(SimpleNamespace(season='2000-01'),
            {'carrier_id': 1, 'facts': {'birth_date': {'policy': 'preserve-existing-mode1'}}},
            allow_preserved_native_birthdate=opt_in)
