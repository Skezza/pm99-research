"""Static-native opening witnesses preserve a starter's existing slot controls."""
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts import season_authored_country_delta_v2 as delta
from scripts import season_duplicate_ownership_delta_v1 as native_players


class _Entry:
    def __init__(self, record_id, payload):
        self.record_id = record_id
        self.payload_offset = 0
        self.payload_length = len(payload)
        self._payload = payload

    def decode_payload(self, _data):
        return self._payload


class _Index:
    def __init__(self, entries):
        self.entries = entries


def _native_fixture(monkeypatch, *, flag=0, mode=1, duplicate=False,
                    compiled_order=5):
    eq = b'EQ-native-parent'
    jug = b'JUG-native-parent'
    changed_jug = b'JUG-compiled-change'
    rows = [SimpleNamespace(player_record_id=101, flag=flag)]
    if duplicate:
        rows.append(SimpleNamespace(player_record_id=101, flag=flag))
    roster = SimpleNamespace(mode_byte=mode, rows=rows)

    def indexed(raw):
        if raw.startswith(b'EQ'):
            return _Index([_Entry(1, raw)])
        if raw.startswith(b'JUG'):
            payload = b'compiled-actor' if raw == changed_jug else b'actor-profile'
            return _Index([_Entry(101, payload)])
        raise AssertionError('unexpected FDI fixture')

    monkeypatch.setattr(delta.IndexedFDIFile, 'from_bytes', indexed)
    monkeypatch.setattr('app.eq_jug_linked.parse_eq_external_team_roster_payload',
        lambda _raw, _names: roster)
    monkeypatch.setattr('scripts.season_historical_roster_audit_v1.native_player',
        lambda _payload, _carrier: {'roles': [2, 98, 98, 98, 98, 98], 'position': 1})
    monkeypatch.setattr(delta, 'read_initial_order',
        lambda payload: SimpleNamespace(order=6 if payload == b'compiled-actor' else compiled_order))
    return eq, jug, changed_jug


def _request_harness(monkeypatch, tmp_path, *, static=None, kind='players-only',
                     role=2, position=1, compiled_jug=None, order=5,
                     opaque_parent=False, parent_fine_roles=None):
    eq, jug, changed_jug = _native_fixture(monkeypatch, compiled_order=order)

    game = tmp_path / 'game'
    dbdat = game / 'DBDAT'
    dbdat.mkdir(parents=True, exist_ok=True)
    for name, raw in [('EQ98030.FDI', eq), ('JUG98030.FDI', jug),
                      ('ENT98030.FDI', b'ENT'), ('TEXTOS.PKF', b'TEXTOS')]:
        (dbdat / name).write_bytes(raw)
    base = SimpleNamespace(game_path=game, package_path=tmp_path / 'parent.json')
    base.package_path.write_text('{}')
    parent_roles = parent_fine_roles if parent_fine_roles is not None else (
        {'policy': 'preserve-existing-mode1'} if opaque_parent else [role])
    before = {
        'players': [{'id': 'person', 'carrier_id': 101, 'club_id': 'club',
                     'facts': {'fine_roles': parent_roles, 'primary_position': position}}],
        'clubs': [{'id': 'club', 'carrier_id': 1, 'opening': {'starting_xi_player_ids': ['person']}}],
    }
    after = {
        'players': [{'id': 'person', 'carrier_id': 101, 'club_id': 'club',
                     'facts': {'fine_roles': [role], 'primary_position': position}}],
        'clubs': [{'id': 'club', 'carrier_id': 1, 'opening': {'starting_xi_player_ids': ['person']}}],
    }
    authoring = {'country': 'England', 'child_recipe_sha256': 'child-hash', 'source_bindings': []}
    docs = {'authoring.json': authoring, 'parent.json': before, 'child.json': after}
    monkeypatch.setattr(delta, '_parent', lambda _base: {'parent': 'pinned'})
    monkeypatch.setattr(delta, '_bound', lambda row: tmp_path / row['path'])
    monkeypatch.setattr(delta.r, 'sha256_file', lambda _path: 'child-hash')
    monkeypatch.setattr(delta.p, 'read_json_file', lambda path: docs[Path(path).name])
    monkeypatch.setattr(delta, 'verify_recipe_mask', lambda *_args: (set(), {'person'}, set()))
    monkeypatch.setattr(delta, 'prepare_name_capacity', lambda raw, _request, _ids: raw)
    monkeypatch.setattr(delta.compiler, '_extract_country_codes_from_textos', lambda _path: {})
    monkeypatch.setattr(native_players, 'compile_players',
        lambda _old, _new, _people, _codes, **_kw: changed_jug if compiled_jug == 'changed' else jug)
    monkeypatch.setattr('scripts.season_opening_order_repair_v1.native_owners',
        lambda _eq: {101: {1}})
    snapshot = delta.static_native_opening_snapshot(eq, jug, 1)
    request = {
        'schema': delta.SCHEMA + '-input', 'country': 'England',
        'parent': {'parent': 'pinned'}, 'child_recipe': {'path': 'child.json', 'sha256': 'x'},
        'authoring_receipt': {'path': 'authoring.json', 'sha256': 'x'},
        'selection_kind': kind, 'club_carrier_ids': [], 'player_ids': ['person'],
        'complete_order_carriers': {},
    }
    if static is not None:
        request['static_native_openings'] = static(snapshot)
    delta._CACHE.clear()
    return base, request, snapshot, changed_jug


def test_snapshot_records_complete_static_native_rows(monkeypatch):
    eq, jug, _ = _native_fixture(monkeypatch)
    actual = delta.static_native_opening_snapshot(eq, jug, 1)
    assert actual == {
        'eq_payload_sha256': delta.digest(eq),
        'rows': [{'carrier_id': 101, 'order': 5,
                  'roles': [2, 98, 98, 98, 98, 98], 'position': 1}],
        'policy': 'preserve-current-native-controls-not-a-historical-fixture',
    }


@pytest.mark.parametrize(('flag', 'mode'), [(1, 1), (0, 0)])
def test_snapshot_rejects_invisible_or_non_mode1_roster(monkeypatch, flag, mode):
    eq, jug, _ = _native_fixture(monkeypatch, flag=flag, mode=mode)
    with pytest.raises(ValueError, match='mode1 rows'):
        delta.static_native_opening_snapshot(eq, jug, 1)


def test_snapshot_rejects_duplicate_native_rows(monkeypatch):
    eq, jug, _ = _native_fixture(monkeypatch, duplicate=True)
    with pytest.raises(ValueError, match='repeated carriers'):
        delta.static_native_opening_snapshot(eq, jug, 1)


def test_starter_identity_change_passes_only_with_exact_static_witness(monkeypatch, tmp_path):
    base, request, _snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': snapshot})
    result = delta._reconstruct(base, request)
    assert result['selected_players'] == [101]
    assert result['selected_clubs'] == []
    assert result['eq'] == (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()


def test_starter_identity_change_without_witness_is_rejected(monkeypatch, tmp_path):
    base, request, _snapshot, _changed = _request_harness(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match='native nonstarter'):
        delta._reconstruct(base, request)


def test_static_witness_scope_and_selection_kind_are_closed(monkeypatch, tmp_path):
    base, request, snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'999': snapshot})
    with pytest.raises(ValueError, match='outside selected actors'):
        delta._reconstruct(base, request)
    base, request, snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': snapshot}, kind='players-and-openings')
    with pytest.raises(ValueError, match='restricted to unchanged player-only'):
        delta._reconstruct(base, request)


@pytest.mark.parametrize(('role', 'position'), [(3, 1), (2, 2)])
def test_static_identity_replacement_must_keep_recipe_roles_and_position(monkeypatch, tmp_path, role, position):
    base, request, snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': snapshot}, role=role, position=position)
    with pytest.raises(ValueError, match='preserve matching native roles'):
        delta._reconstruct(base, request)
    base, request, snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': snapshot},
        parent_fine_roles=[2, 3], role=2)
    with pytest.raises(ValueError, match='preserve matching native roles'):
        delta._reconstruct(base, request)


def test_opaque_parent_roles_are_allowed_only_when_new_recipe_matches_native(monkeypatch, tmp_path):
    base, request, snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': snapshot}, opaque_parent=True)
    assert delta._reconstruct(base, request)['selected_players'] == [101]
    base, request, snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': snapshot},
        opaque_parent=True, role=3)
    with pytest.raises(ValueError, match='preserve matching native roles'):
        delta._reconstruct(base, request)


def test_postimage_checks_startup_order_after_native_compile(monkeypatch, tmp_path):
    base, request, snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': snapshot}, compiled_jug='changed')
    with pytest.raises(ValueError, match='changed native startup controls or roles'):
        delta._reconstruct(base, request)


def test_static_witness_must_exactly_match_parent_snapshot(monkeypatch, tmp_path):
    base, request, _snapshot, _changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': {**snapshot, 'rows': []}})
    with pytest.raises(ValueError, match='differs from the complete native parent'):
        delta._reconstruct(base, request)
