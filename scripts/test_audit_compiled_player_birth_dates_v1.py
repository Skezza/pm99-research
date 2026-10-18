import copy
import pytest
from scripts import audit_compiled_player_birth_dates_v1 as module
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6361_player_payload


def fixture():
    payload = _dd6361_player_payload(2)
    native = module.roster.native_player(payload, 2)
    return {'players': [{'id': 'person', 'carrier_id': 2, 'name': native['name'],
                         'facts': {'birth_date': '1990-11-16'}}]}, payload


def test_literal_native_date_agrees():
    package, payload = fixture()
    result = module.inspect(package, _indexed_fdi([(2, '', payload)]))
    assert result['literal_players_checked'] == 1
    assert result['failure_count'] == 0


@pytest.mark.parametrize('problem', ['birthday', 'invalid-native-leap-day', 'wrong-native-name', 'missing-record'])
def test_wrong_or_unreadable_native_fact_is_not_called_valid(problem):
    package, payload = fixture()
    if problem == 'birthday': package['players'][0]['facts']['birth_date'] = '2000-11-16'
    if problem == 'wrong-native-name': package['players'][0]['name'] = 'Another Person'
    if problem == 'invalid-native-leap-day':
        payload = bytearray(payload)
        end = module.roster.native_player(bytes(payload), 2)['name_end']
        payload[end+12] = 29 ^ 0x61; payload[end+13] = 2 ^ 0x61
        payload = bytes(payload)
    records = [] if problem == 'missing-record' else [(2, '', payload)]
    assert module.inspect(package, _indexed_fdi(records))['failure_count'] == 1


def test_preserved_birth_date_is_a_gap_not_a_success():
    package, payload = fixture()
    package['players'][0]['facts']['birth_date'] = {'policy': 'preserve-existing-mode1'}
    before = copy.deepcopy(package)
    result = module.inspect(package, _indexed_fdi([(2, '', payload)]))
    assert result['preserved_date_gaps'] == 1
    assert result['literal_players_checked'] == 0
    assert package == before
