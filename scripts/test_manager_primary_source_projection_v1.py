"""A transcribed first-fixture source must not claim a parsed manager tenure."""
import copy

import pytest

from scripts import publish_historical_role_delta_v1 as publisher


def fixture():
    package = dict(players=[], clubs=[dict(id='club-1701', carrier_id=1701,
        manager_id='manager-2062')], managers=[dict(id='manager-2062',
        carrier_id=2062, name='Nyilasi', policy='preserve-existing-mode1')],
        artifacts=[], proofs=[])
    descriptor = dict(season='2000-01', updates=[])
    plan = dict(source_method='dated-original-newspaper-first-fixture-manager-v1',
        native_name_projection='explicit-published-family-name-v1', updates=[dict(
        manager_id='manager-2062', club_id='club-1701', carrier_id=2062,
        club_carrier_id=1701, before='Nyilasi', before_policy='preserve-existing-mode1',
        native_after='Csank', after='János Csank')])
    return package, descriptor, plan


def test_transcribed_source_keeps_full_name_and_family_display_without_tenure_claim(monkeypatch):
    package, descriptor, plan = fixture()
    original = copy.deepcopy(package)
    monkeypatch.setattr(publisher.package_v2, 'validate_package', lambda _: None)
    result = publisher.updated_package(package, descriptor, manager_plan=plan)
    manager = result['managers'][0]
    assert manager['name'] == 'János Csank'
    assert manager['native_names'] == dict(surname='Csank', display_name='Csank')
    assert result['proofs'][0]['covers'] == [
        'visually-transcribed-contemporary-first-fixture-manager-name',
        'original-source-and-native-owner-bound']
    assert package == original
    assert result['clubs'] == original['clubs']


def test_legacy_manager_plan_does_not_gain_new_alias_or_proof(monkeypatch):
    package, descriptor, plan = fixture()
    del plan['source_method']
    del plan['native_name_projection']
    monkeypatch.setattr(publisher.package_v2, 'validate_package', lambda _: None)
    result = publisher.updated_package(package, descriptor, manager_plan=plan)
    assert 'native_names' not in result['managers'][0]
    assert result['proofs'][0]['covers'] == ['raw-reparsed-first-fixture-manager-names']


def test_wrong_manager_owner_is_refused(monkeypatch):
    package, descriptor, plan = fixture()
    package['clubs'][0]['manager_id'] = 'another-manager'
    monkeypatch.setattr(publisher.package_v2, 'validate_package', lambda _: None)
    with pytest.raises(ValueError, match='identity/ownership'):
        publisher.updated_package(package, descriptor, manager_plan=plan)
