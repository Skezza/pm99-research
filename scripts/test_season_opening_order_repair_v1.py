import copy
import hashlib
import json

import pytest

from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import season_opening_order_repair_v1 as repair
from scripts import season_contextual_tactics_v1 as tactics
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts.test_season_package_compiler_v2 import _write_fixture_base, _copy_base


def test_repair_moves_keeper_with_deployment_preserving_facts_and_roster(tmp_path):
    base, path = _write_fixture_base(tmp_path)
    package = json.loads(path.read_text())
    club = package['clubs'][0]
    players = {p['id']: p for p in package['players']}
    # Synthetic fixture's player 1 is the goalkeeper; corrupt only the
    # selection order as observed in affected real-season recipes.
    opening = club['opening']
    xi = opening['starting_xi_player_ids']
    pos = opening['tactics_positions']
    xi[0], xi[1] = xi[1], xi[0]
    pos[0], pos[1] = pos[1], pos[0]
    before_players, before_roster = copy.deepcopy(players), list(club['roster_player_ids'])
    jug = (base / 'DBDAT/JUG98030.FDI').read_bytes()
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    row = repair.repair_club(club, players, index, jug)
    assert club['opening']['starting_xi_player_ids'][0] == 'player-01'
    assert club['opening']['tactics_positions'][0] == [114, 20, 114, 25]
    assert row['inferred_deployment']['not_independent_historical_deployment_proof']
    assert row['players'][0]['native_player_id'] == 1
    assert players == before_players
    assert club['roster_player_ids'] == before_roster
    eq = (base / 'DBDAT/EQ98030.FDI').read_bytes()
    layer = {'schema_version': repair.SCHEMA, 'clubs': [row]}
    output = repair.apply_layer(eq, jug, layer)
    assert repair.apply_layer(eq, output, layer) == output
    assert tactics.native_xi(tactics.payloads(eq)[307], output)[0][0] == 1
    bad = copy.deepcopy(layer)
    bad['clubs'][0]['carrier_id'] = 999
    with pytest.raises(ValueError, match='mode-0 club'):
        repair.apply_layer(eq, jug, bad)
    bad = copy.deepcopy(layer)
    bad['clubs'][0]['players'][0]['native_player_id'] = 999
    with pytest.raises(ValueError, match='ownership'):
        repair.apply_layer(eq, jug, bad)


def test_repair_rejects_unsourced_keeper_choice(tmp_path):
    base, path = _write_fixture_base(tmp_path)
    package = json.loads(path.read_text())
    players = {p['id']: p for p in package['players']}
    players['player-02']['facts']['primary_position'] = 'G'
    jug = (base / 'DBDAT/JUG98030.FDI').read_bytes()
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    with pytest.raises(ValueError, match='one sourced goalkeeper'):
        repair.repair_club(package['clubs'][0], players, index, jug)


def test_deployment_disagreement_is_a_warning_not_a_fact_rewrite():
    package = {'players': [{'id': 'p', 'carrier_id': 1, 'name': 'Fixture Player',
                           'facts': {'primary_position': 'F', 'fine_roles': [12]}}],
               'clubs': [{'id': 'c', 'name': 'Fixture Club', 'opening': {'tactics_context':
                          {'slots': [{'player_id': 'p', 'role': 'LCB'}]}}}]}
    before = copy.deepcopy(package)
    report = repair.deployment_review(package)
    assert report['warning_count'] == 1
    assert package == before
    package['players'][0]['facts']['fine_roles'].append(4)
    assert repair.deployment_review(package)['warning_count'] == 0


def test_durable_layer_compiler_replay_and_hash_rejection_are_atomic(tmp_path):
    base, path = _write_fixture_base(tmp_path)
    output = _copy_base(base, tmp_path / 'compiled-base')
    compiler.compile_package_to_tree(package_path=path, base_tree=base, materialisation_tree=output)
    package = json.loads(path.read_text())
    jug = (output / 'DBDAT/JUG98030.FDI').read_bytes()
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    row = repair.repair_club(package['clubs'][0], {p['id']: p for p in package['players']}, index, jug)
    layer = {'schema_version': repair.SCHEMA, 'season': '2015-16', 'clubs': [row]}
    layer_path = tmp_path / 'order.json'
    layer_path.write_text(json.dumps(layer))
    package['artifacts'].append({'id': repair.PREFIX + '2015-16', 'kind': 'season-input',
        'relative_path': 'order.json', 'sha256': hashlib.sha256(layer_path.read_bytes()).hexdigest()})
    package['artifacts'].sort(key=lambda a: a['id'])
    packages.write_canonical_package(path, package)
    second = _copy_base(base, tmp_path / 'second')
    compiler.compile_package_to_tree(package_path=path, base_tree=base, materialisation_tree=second)
    assert (second / 'DBDAT/JUG98030.FDI').read_bytes() == jug
    layer['season'] = '2014-15'
    layer_path.write_text(json.dumps(layer))
    rejected = _copy_base(base, tmp_path / 'rejected')
    before = (rejected / 'DBDAT/JUG98030.FDI').read_bytes()
    with pytest.raises(ValueError, match='hash changed'):
        compiler.compile_package_to_tree(package_path=path, base_tree=base, materialisation_tree=rejected)
    assert (rejected / 'DBDAT/JUG98030.FDI').read_bytes() == before


def test_native_owner_cache_preserves_isolation_and_binds_all_input_bytes(monkeypatch):
    from types import SimpleNamespace
    calls = []
    def read(raw):
        calls.append(raw)
        return {321: b'small'}
    monkeypatch.setattr(repair.tactics, 'payloads', read)
    monkeypatch.setattr(repair, 'parse_eq_external_team_roster_payload',
        lambda *args: SimpleNamespace(rows=[SimpleNamespace(player_record_id=1234)]))
    first = repair.native_owners(b'first image')
    first[1234].add(999)
    assert repair.native_owners(b'first image') == {1234: {321}}
    assert repair.native_owners(b'second image') == {1234: {321}}
    assert calls == [b'first image', b'second image']
    monkeypatch.setattr(repair, 'parse_eq_external_team_roster_payload', lambda *args: None)
    assert repair.native_owners(b'second image') == {}


def test_native_owner_cache_never_suppresses_unreadable_roster_rejection(monkeypatch):
    import pytest
    raw = bytearray(0x30)
    raw[0x26:0x28] = (600).to_bytes(2, 'little')
    calls = []
    def read(value):
        calls.append(value)
        return {321: bytes(raw)}
    monkeypatch.setattr(repair.tactics, 'payloads', read)
    monkeypatch.setattr(repair, 'parse_eq_external_team_roster_payload', lambda *args: None)
    for _ in range(2):
        with pytest.raises(ValueError, match='unreadable external'):
            repair.native_owners(b'unreadable')
    assert len(calls) == 2
