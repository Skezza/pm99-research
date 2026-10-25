"""Regression cases for the additive v2 full-cohort selector/collision policy.

Install this alongside the existing v2 test module after reviewing the adjacent
canonical patch. The synthetic setup is reused from that focused module.
"""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import season_historical_club_label_full_cohort_optin_v2 as optin
from scripts import season_duplicate_ownership_plan_v1 as ownership_layers
from scripts.test_season_historical_club_label_full_cohort_optin_v2 import _create, _synthetic_case


def _allow_native_identity(case, monkeypatch):
    (case['release'].game_path / 'DBDAT/JUG98030.FDI').write_bytes(b'synthetic indexed JUG placeholder')
    rows = {int(p['carrier_id']): {'name':p['name'], 'self_id':int(p['carrier_id']),
        'payload_sha256':'f' * 64} for p in case['package']['players']}
    monkeypatch.setattr(optin, '_native_jug_identity_index', lambda _data, _ids:rows)
    monkeypatch.setattr(optin.registry, 'load_registered_release', lambda _season, _release_id:case['release'])
    monkeypatch.setattr(optin, '_reparse_source_cohort', lambda season, selector, source: {
        'method':'test-bound-raw-reparse','season':season,
        'source_selector_sha256':optin._selector_identity(selector),'raw_sha256':'a' * 64})


def test_nonnumeric_selector_and_no_existing_old_label_carrier(tmp_path, monkeypatch):
    case = _synthetic_case(tmp_path, monkeypatch)
    _allow_native_identity(case, monkeypatch)
    target = case['target_selector']
    target['source_path'] = 'portugal/2000-2001/PO1/fc-alverca.txt'
    case['preallocation']['source_clubs'][0]['selector'] = target
    pre_path = case['source_root'] / '2000-01/opening-squad-preallocation.json'
    pre_path.write_text(json.dumps(case['preallocation'], sort_keys=True, separators=(',', ':')))
    package = case['package']
    package['artifacts'][0]['sha256'] = hashlib.sha256(pre_path.read_bytes()).hexdigest()
    package['clubs'][0]['name'] = package['clubs'][0]['full_name'] = 'Old team label'
    case['release'].package_path.write_text(json.dumps(package, sort_keys=True, separators=(',', ':')))
    monkeypatch.setattr(optin, '_native_owner_index', lambda _data: (SimpleNamespace(entries=[]), case['owners']))
    monkeypatch.setattr(optin, '_reparse_source_cohort', lambda season, selector, source: {
        'method': 'test-bound-raw-reparse', 'season': season,
        'source_selector_sha256': optin._selector_identity(selector), 'raw_sha256': 'a' * 64})

    witness = optin.create_witness(season='2000-01', source_root=case['source_root'],
        carrier_id=623, expected_source_selector=target)

    assert witness['target_provider_club_id'] is None
    assert witness['target_source_selector_identity_sha256'] == optin._selector_identity(target)
    assert witness['prior_label_collision_present'] is False
    assert witness['distinct_old_label_carrier'] is None
    assert witness['prior_roster_bindings'] == []
    assert witness['raw_source_reparse']['method'] == 'test-bound-raw-reparse'
    assert optin.verify_witness(witness, source_root=case['source_root']) == witness


def test_desired_target_name_duplicate_in_package_is_refused(tmp_path, monkeypatch):
    case = _synthetic_case(tmp_path, monkeypatch)
    _allow_native_identity(case, monkeypatch)
    monkeypatch.setattr(optin, '_carrier_country_group', lambda _package, _carrier: 'portugal')
    case['package']['clubs'].append({'id': 'club-999', 'carrier_id': 999,
        'name': 'FC Alverca', 'full_name': 'FC Alverca',
        'division': 'preserve-existing-mode1-membership', 'roster_player_ids': []})
    case['release'].package_path.write_text(json.dumps(case['package'], sort_keys=True, separators=(',', ':')))
    monkeypatch.setattr(optin, '_native_owner_index', lambda _data: (SimpleNamespace(entries=[]), case['owners']))
    monkeypatch.setattr(optin, '_reparse_source_cohort', lambda season, selector, source: {
        'method': 'test-bound-raw-reparse', 'season': season,
        'source_selector_sha256': optin._selector_identity(selector), 'raw_sha256': 'a' * 64})
    with pytest.raises(ValueError, match='package-layer club'):
        optin.create_witness(season='2000-01', source_root=case['source_root'], carrier_id=623,
            expected_source_selector=case['target_selector'])


def test_legacy_numeric_collision_witness_keeps_its_existing_shape(tmp_path, monkeypatch):
    case = _synthetic_case(tmp_path, monkeypatch)
    monkeypatch.setattr(optin, '_native_owner_index', lambda _data: (SimpleNamespace(entries=[]), case['owners']))
    witness = _create(case)
    assert 'target_source_selector_identity_sha256' not in witness
    assert 'prior_source_selector_identity_sha256' not in witness
    assert 'raw_source_reparse' not in witness
    assert 'prior_raw_source_reparse' not in witness
    assert 'prior_label_collision_present' not in witness


def test_desired_target_name_duplicate_in_english_overlay_is_refused(tmp_path, monkeypatch):
    case = _synthetic_case(tmp_path, monkeypatch)
    _allow_native_identity(case, monkeypatch)
    case['target_selector']['country_catalog'] = 'eng'
    pre_path = case['source_root'] / '2000-01/opening-squad-preallocation.json'
    pre_path.write_text(json.dumps(case['preallocation'], sort_keys=True, separators=(',', ':')))
    case['package']['artifacts'][0]['sha256'] = hashlib.sha256(pre_path.read_bytes()).hexdigest()
    case['release'].package_path.write_text(json.dumps(case['package'], sort_keys=True, separators=(',', ':')))
    monkeypatch.setattr(optin, 'club_group', lambda _club: 'england')
    overlay = {'clubs':[{'id':'english-club-999','carrier_id':999,'name':'FC Alverca',
        'full_name':'FC Alverca'}]}
    monkeypatch.setattr(ownership_layers,'package_layers',lambda _release:[
        ('main',case['package'],case['release'].package_path),('english',overlay,None)])
    monkeypatch.setattr(optin, '_native_owner_index', lambda _data: (SimpleNamespace(entries=[]), case['owners']))
    monkeypatch.setattr(optin, '_reparse_source_cohort', lambda season, selector, source: {
        'method':'test-bound-raw-reparse','season':season,
        'source_selector_sha256':optin._selector_identity(selector),'raw_sha256':'a'*64})
    with pytest.raises(ValueError, match='package-layer club'):
        optin.create_witness(season='2000-01',source_root=case['source_root'],carrier_id=623,
            expected_source_selector=case['target_selector'])


@pytest.mark.parametrize(('other_group', 'should_refuse'), [
    ('argentina', False),
    ('portugal', True),
])
def test_native_eq_name_collision_is_country_scoped(tmp_path, monkeypatch, other_group, should_refuse):
    case = _synthetic_case(tmp_path, monkeypatch)
    _allow_native_identity(case, monkeypatch)
    entry = SimpleNamespace(record_id=999, decode_payload=lambda _data: b'xx\xdd\x63\x61xxx')
    monkeypatch.setattr(optin, '_native_owner_index', lambda _data: (
        SimpleNamespace(entries=[entry]), case['owners']))
    monkeypatch.setattr(optin, '_read_eq_inline_string', lambda _payload, _offset: ('FC Alverca', 0, 0))
    monkeypatch.setattr(optin, '_carrier_country_group', lambda _package, _carrier: other_group)
    if should_refuse:
        with pytest.raises(ValueError, match='another native EQ carrier'):
            optin.create_witness(season='2000-01', source_root=case['source_root'], carrier_id=623,
                expected_source_selector=case['target_selector'])
    else:
        witness = optin.create_witness(season='2000-01', source_root=case['source_root'], carrier_id=623,
            expected_source_selector=case['target_selector'])
        assert witness['target']['after'] == 'FC Alverca'


def test_package_duplicate_with_unknown_country_fails_closed(tmp_path, monkeypatch):
    from scripts import season_duplicate_ownership_plan_v1 as ownership_layers
    case = _synthetic_case(tmp_path, monkeypatch)
    _allow_native_identity(case, monkeypatch)
    unknown = {'id': 'unknown-club', 'carrier_id': 999, 'name': 'FC Alverca', 'full_name': 'FC Alverca'}
    case['package']['clubs'].append(unknown)
    monkeypatch.setattr(ownership_layers, 'package_layers', lambda _release: [
        ('main', case['package'], case['release'].package_path)])
    monkeypatch.setattr(optin, '_carrier_country_group', lambda _package, _carrier: None)
    with pytest.raises(ValueError, match='unknown country'):
        optin.create_witness(season='2000-01', source_root=case['source_root'], carrier_id=623,
            expected_source_selector=case['target_selector'])
