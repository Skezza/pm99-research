"""A new sourced striker must not inherit a displaced defender's fine role."""
import copy

import pytest

from scripts import season_authored_country_delta_v2 as delta
from scripts.test_season_authored_country_delta_v2_defender_repair import _case, _integrated


def case(old_roles=(1,), new_roles=(12,)):
    args = _case(old_roles, new_roles, old_position='F', new_position='F')
    args[0]['person_id'] = 'displaced'
    args[1]['person_id'] = 'sourced-forward'
    return args


def test_only_new_forward_identity_can_replace_incompatible_seed_role():
    args = case()
    before = copy.deepcopy(args)
    assert delta._static_identity_roles(*args, repair_forward=True) == [12]
    assert args == before


@pytest.mark.parametrize('old_roles', [(12,), (1, 11), (), (255,), (True,)])
def test_forward_opt_in_cannot_discard_compatible_or_unknown_roles(old_roles):
    with pytest.raises(ValueError, match='new source-backed forward'):
        delta._static_identity_roles(*case(old_roles), repair_forward=True)


@pytest.mark.parametrize('new_roles', [(8,), (15,), (12, 15), (), (True,), (98,)])
def test_forward_exception_only_admits_generic_twelve(new_roles):
    with pytest.raises(ValueError, match='generic F/12'):
        delta._static_identity_roles(*case(new_roles=new_roles), repair_forward=True)


@pytest.mark.parametrize('identity', ['displaced', None, ''])
def test_existing_or_absent_identity_cannot_use_forward_exception(identity):
    args = case()
    args[1]['person_id'] = identity
    with pytest.raises(ValueError, match='new source-backed forward'):
        delta._static_identity_roles(*args, repair_forward=True)


def test_default_and_defender_exception_do_not_admit_forward_repair():
    with pytest.raises(ValueError, match='preserve matching native roles'):
        delta._static_identity_roles(*case())
    with pytest.raises(ValueError, match='compatible D role'):
        delta._static_identity_roles(*case(), repair_defender=True)
    with pytest.raises(ValueError, match='must not overlap'):
        delta._static_identity_roles(*case(), repair_defender=True, repair_forward=True)


@pytest.mark.parametrize('grade', ['reviewed-editorial', None])
def test_forward_requires_source_receipt(grade):
    args = case()
    args[1]['proof']['grade'] = grade
    with pytest.raises(ValueError, match='source-backed'):
        delta._static_identity_roles(*args, repair_forward=True)


@pytest.mark.parametrize('repairs', [[True], [101, 101], [999], {'101': True}])
def test_forward_request_cannot_expand_selected_actor_scope(monkeypatch, tmp_path, repairs):
    base, request, _ = _integrated(monkeypatch, tmp_path)
    request['static_forward_fine_role_repairs'] = repairs
    with pytest.raises(ValueError, match='static forward repairs'):
        delta._reconstruct(base, request)


@pytest.mark.parametrize('corruption', [None, 'order', 'position', 'role', 'source'])
def test_compiled_forward_repair_preserves_closed_native_controls(monkeypatch, tmp_path, corruption):
    from types import SimpleNamespace
    base, request, changed = _integrated(monkeypatch, tmp_path)
    original_read = delta.p.read_json_file
    def documents(path):
        doc = copy.deepcopy(original_read(path))
        if path.name in ('parent.json', 'child.json'):
            actor = doc['players'][0]
            actor['facts']['primary_position'] = 'F'
            actor['person_id'] = 'old' if path.name == 'parent.json' else 'new'
            if path.name == 'child.json':
                actor['facts']['fine_roles'] = [12]
        if corruption == 'source' and path.name == 'authoring.json':
            doc['source_bindings'] = []
        return doc
    monkeypatch.setattr(delta.p, 'read_json_file', documents)
    monkeypatch.setattr('scripts.season_historical_roster_audit_v1.native_player',
        lambda payload, _carrier: {'roles': [
            (15 if corruption == 'role' else 12) if payload == b'compiled-actor' else 1,
            98, 98, 98, 98, 98],
            'position': 'D' if corruption == 'position' and payload == b'compiled-actor' else 'F'})
    monkeypatch.setattr(delta, 'read_initial_order', lambda payload: SimpleNamespace(
        order=6 if corruption == 'order' and payload == b'compiled-actor' else 5))
    request.pop('static_defender_fine_role_repairs')
    request['static_forward_fine_role_repairs'] = [101]
    request['static_native_openings'] = {'1': delta.static_native_opening_snapshot(
        (base.game_path/'DBDAT/EQ98030.FDI').read_bytes(),
        (base.game_path/'DBDAT/JUG98030.FDI').read_bytes(), 1)}
    delta._CACHE.clear()
    if corruption:
        with pytest.raises(ValueError, match='startup controls or roles|hash-bound source input'):
            delta._reconstruct(base, request)
    else:
        result = delta._reconstruct(base, request)
        assert result['jug'] == changed
        assert result['eq'] == (base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
        assert result['ent'] == b'ENT'
