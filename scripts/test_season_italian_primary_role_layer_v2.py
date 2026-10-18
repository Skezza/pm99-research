"""Adversarial primary-label checks; no proprietary corpus or live runner."""
import copy
from types import SimpleNamespace

import pytest

from scripts import season_italian_opening_layer_v1 as layer
from scripts.test_season_italian_opening_layer_v1 import order_fixture, recipe_fixture


def role_fixture(monkeypatch):
    native = dict(name='Keeper', birth_date='1974-05-05', position='G')
    roles = [6, 7, 15, 98, 98, 98]
    row = dict(carrier_id=1, player_id='keep', native_name=native['name'],
               birth_date=native['birth_date'], source_position='G',
               before=6, factory_before=8, after=0,
               native_roles_before=list(roles),
               native_roles_after=[0, *roles[1:]],
               factory_roles_before=[8, *roles[1:]],
               recipe_fine_roles_before={'policy': 'preserve-existing-mode1'},
               recipe_fine_roles_after=[0, 7, 15])
    plan = dict(schema_version=layer.ROLE_SCHEMA,
                primary_role_policy=layer.ROLE_POLICY,
                starting_xi=list(range(1, 12)), primary_role_changes=[row])
    entry = SimpleNamespace(record_id=1, decode_payload=lambda raw: b'decoded')
    monkeypatch.setattr(layer.IndexedFDIFile, 'from_bytes',
                        lambda raw: SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(layer.facts, 'native_facts', lambda raw, id: native)
    monkeypatch.setattr(layer, 'read_indexed_native_roles', lambda raw, id: (12, list(roles)))
    calls = []
    def writer(raw, updates):
        calls.append(copy.deepcopy(updates))
        roles[0] = updates[1][1]
        return raw, []
    monkeypatch.setattr(layer, 'rewrite_indexed_native_primary_roles', writer)
    return plan, row, native, roles, calls


@pytest.mark.parametrize('primary', [6, 8, 0])
def test_accepts_declared_source_factory_target_primary_and_preserves_secondaries(monkeypatch, primary):
    plan, row, native, roles, calls = role_fixture(monkeypatch)
    roles[0] = primary
    before = roles[1:]
    assert layer._apply_primary_roles(b'jug', plan) == b'jug'
    assert calls == [{1: (primary, 0)}]
    assert roles == [0, *before]
    assert layer._apply_primary_roles(b'jug', plan) == b'jug'
    assert roles == [0, *before]


@pytest.mark.parametrize('problem', ['unknown-primary', 'wrong-target', 'duplicate',
    'outside-XI', 'name', 'DOB', 'broad-role', 'policy'])
def test_refuses_unbound_role_authority_before_writer(monkeypatch, problem):
    plan, row, native, roles, calls = role_fixture(monkeypatch)
    if problem == 'unknown-primary': roles[0] = 12
    if problem == 'wrong-target': row['after'] = 4
    if problem == 'duplicate': plan['primary_role_changes'].append(copy.deepcopy(row))
    if problem == 'outside-XI': plan['starting_xi'].remove(1)
    if problem == 'name': native['name'] = 'Other'
    if problem == 'DOB': native['birth_date'] = '1974-06-05'
    if problem == 'broad-role': native['position'] = 'F'
    if problem == 'policy': plan['primary_role_policy'] = 'guess'
    with pytest.raises(ValueError):
        layer._apply_primary_roles(b'jug', plan)
    assert calls == []


@pytest.mark.parametrize('slot', range(6))
def test_exact_publisher_checks_entire_source_role_window(monkeypatch, slot):
    plan, row, native, roles, calls = role_fixture(monkeypatch)
    roles[slot] = 8 if slot == 0 else 13
    with pytest.raises(ValueError, match='source window'):
        layer._apply_primary_roles(b'jug', plan, exact_before=True)
    assert calls == []


@pytest.mark.parametrize('primary', [6, 8, 0])
def test_normal_replay_refuses_unbound_secondary_role_drift(monkeypatch, primary):
    plan, row, native, roles, calls = role_fixture(monkeypatch)
    roles[0], roles[1] = primary, 13
    with pytest.raises(ValueError):
        layer._apply_primary_roles(b'jug', plan)
    assert calls == []


def test_v1_cannot_authorize_role_edit_through_order(monkeypatch):
    plan, native, rows, calls = order_fixture(monkeypatch)
    plan['primary_role_changes'] = [{'carrier_id': 1}]
    with pytest.raises(ValueError, match='v1'):
        layer.order(b'jug', b'eq', plan)
    assert calls == []


def test_v1_cannot_authorize_role_edit_through_recipe_bind(monkeypatch):
    package, plan, old = recipe_fixture()
    package['players'][0]['facts'] = {'fine_roles': [6]}
    plan['primary_role_changes'] = [dict(player_id='keep',
        recipe_fine_roles_before=[6], recipe_fine_roles_after=[0])]
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    with pytest.raises(ValueError):
        layer.bind(package, plan)


def test_binding_changes_only_primary_and_retains_declared_secondary_roles(monkeypatch):
    package, plan, old = recipe_fixture()
    package['players'][0]['facts'] = {'fine_roles': [6, 7, 15], 'birth_date': '1974-05-05'}
    original = copy.deepcopy(package)
    plan.update(schema_version=layer.ROLE_SCHEMA, primary_role_policy=layer.ROLE_POLICY,
        primary_role_changes=[dict(player_id='keep', recipe_fine_roles_before=[6, 7, 15],
                                   recipe_fine_roles_after=[0, 7, 15])])
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    result = layer.bind(package, plan)
    assert package == original
    assert result['players'][0]['facts'] == {'fine_roles': [0, 7, 15], 'birth_date': '1974-05-05'}


@pytest.mark.parametrize('position,role,target', [('D', 9, 4), ('G', 6, 0),
    ('M', 4, 9), ('F', 4, 8), ('D', 2, None), ('M', 17, None),
    ('F', 8, None), ('G', 0, None)])
def test_explicit_local_policy_and_compatible_roles(position, role, target):
    from scripts.season_tff_sourced_opening_xi_v1 import conservative_role
    assert layer.conservative_primary_role(position, role) == target
    if position == 'D' and role == 9:
        assert conservative_role(position, role) is None


def prepare_roles_fixture(monkeypatch):
    native = dict(name='Keeper', birth_date='1974-05-05', position='G')
    roles = [6, 7, 15, 98, 98, 98]
    entry = SimpleNamespace(record_id=1, decode_payload=lambda raw: raw)
    monkeypatch.setattr(layer.IndexedFDIFile, 'from_bytes',
                        lambda raw: SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(layer.facts, 'native_facts', lambda raw, id: native)
    monkeypatch.setattr(layer, 'read_indexed_native_roles',
                        lambda raw, id: (12, list(roles)))
    witness = dict(carrier_id=1, native=copy.deepcopy(native),
                   source={'position': 'G', 'birth_date': '1974-06-05'})
    players = {1: dict(id='keep', facts={'primary_position': 'G',
                          'fine_roles': {'policy': 'preserve-existing-mode1'}})}
    return native, roles, witness, players


def test_prepare_keeps_documented_source_birthday_conflict_and_native_birthday(monkeypatch):
    native, roles, witness, players = prepare_roles_fixture(monkeypatch)
    rows = layer._primary_role_changes(b'source', b'factory', [witness], players)
    assert rows[0]['birth_date'] == '1974-05-05'
    assert witness['source']['birth_date'] == '1974-06-05'
    assert rows[0]['native_roles_after'] == [0, 7, 15, 98, 98, 98]
    assert rows[0]['recipe_fine_roles_after'] == [0, 7, 15]


@pytest.mark.parametrize('problem', ['native-broad', 'recipe-broad', 'repeated-secondary'])
def test_prepare_refuses_broad_mismatch_or_unrepresentable_recipe(monkeypatch, problem):
    native, roles, witness, players = prepare_roles_fixture(monkeypatch)
    if problem == 'native-broad': native['position'] = 'F'
    if problem == 'recipe-broad': players[1]['facts']['primary_position'] = 'F'
    if problem == 'repeated-secondary': roles[1] = 0
    with pytest.raises(ValueError):
        layer._primary_role_changes(b'source', b'factory', [witness], players)


def test_prepare_does_not_touch_compatible_primary(monkeypatch):
    native, roles, witness, players = prepare_roles_fixture(monkeypatch)
    roles[0] = 0
    assert layer._primary_role_changes(b'source', b'factory', [witness], players) == []


def test_recipe_bind_refuses_unapproved_v2_role_policy(monkeypatch):
    package, plan, old = recipe_fixture()
    package['players'][0]['facts'] = {'fine_roles': [6]}
    plan.update(schema_version=layer.ROLE_SCHEMA, primary_role_policy='guess',
        primary_role_changes=[dict(player_id='keep',
            recipe_fine_roles_before=[6], recipe_fine_roles_after=[0])])
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    with pytest.raises(ValueError):
        layer.bind(package, plan)
