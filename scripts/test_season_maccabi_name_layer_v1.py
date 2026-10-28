import copy
from types import SimpleNamespace

import pytest

from app.editor_actions import _indexed_variable_name_prefix
from scripts import season_maccabi_name_layer_v1 as names
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6360_player_payload


def example(tmp_path, monkeypatch):
    # Original name capacity is specific to each carrier. All current native
    # facts are deliberately kept different from the factory facts.
    factory_rows, current_rows, updates = [], [], []
    for id, display in names.TARGETS:
        factory = _dd6360_player_payload(2)
        old_end = names._native_dd6360_role_start(factory)
        prefix = factory[:8] + _indexed_variable_name_prefix('Factory Longfamily')
        factory = prefix + factory[old_end:] + b'\x61' * 30
        current, _ = names._patch_indexed_dd6360_variable_name(factory, 'Factory Longfamily', 'Tal')
        changed = bytearray(current)
        changed[names._native_dd6360_role_start(current) + 16] = 191 ^ 0x61
        current = bytes(changed)
        restored, recovery = names.recover_compact_name_window(factory, current)
        after, _ = names._patch_indexed_dd6360_variable_name(restored, 'Factory Longfamily', display)
        fields = names._read_native_dd6360_fields(current, names._native_dd6360_role_start(current))
        person = dict(id=f'player-{id}', carrier_id=id, name='Tal', source_name='Ben-Haim, Tal', facts={'height_cm': 191})
        updates.append(dict(carrier_id=id, player_id=person['id'], before_player=person,
            display_name=display, before_payload_sha256=names.digest(current),
            after_payload_sha256=names.digest(after), recovery=recovery, native_fields=fields))
        factory_rows.append((id, '', factory))
        current_rows.append((id, '', current))
    other = (4, '', _dd6360_player_payload(4))
    factory_path = tmp_path / 'factory.fdi'
    factory_path.write_bytes(_indexed_fdi(factory_rows + [other]))
    monkeypatch.setattr(names.capacity, 'verify_bundle', lambda _: factory_path)
    jug = _indexed_fdi(current_rows + [other])
    plan = dict(schema=names.SCHEMA, season='2015-16', updates=updates,
        capacity_bundle={}, jug_sha256=names.digest(jug))
    return jug, plan


def test_names_only_preserve_every_current_native_field_and_unrelated_record(tmp_path, monkeypatch):
    jug, plan = example(tmp_path, monkeypatch)
    result = names.apply(jug, plan)
    assert names.apply(result, plan) == result
    _, before = names.records(jug)
    _, after = names.records(result)
    assert before[4].decode_payload(jug) == after[4].decode_payload(result)
    for row in plan['updates']:
        payload = after[row['carrier_id']].decode_payload(result)
        assert names.stored_case_display(payload) == row['display_name']
        assert names._read_native_dd6360_fields(payload, names._native_dd6360_role_start(payload)) == row['native_fields']


@pytest.mark.parametrize('problem', ['season', 'target', 'display', 'preimage', 'after', 'fields', 'recovery', 'whole-file'])
def test_forged_or_stale_name_only_claims_fail_closed(tmp_path, monkeypatch, problem):
    jug, plan = example(tmp_path, monkeypatch)
    if problem == 'season': plan['season'] = '2014-15'
    if problem == 'target': plan['updates'][0]['carrier_id'] = 4
    if problem == 'display': plan['updates'][0]['display_name'] = 'Other Person'
    if problem == 'preimage': plan['updates'][0]['before_payload_sha256'] = 'wrong'
    if problem == 'after': plan['updates'][0]['after_payload_sha256'] = 'wrong'
    if problem == 'fields': plan['updates'][0]['native_fields']['height_cm'] = 180
    if problem == 'recovery': plan['updates'][0]['recovery']['recovered_name_bytes'] = 1
    if problem == 'whole-file': plan['jug_sha256'] = 'wrong'
    with pytest.raises(ValueError): names.apply(jug, plan)


def test_recipe_changes_only_display_names_and_appends_exact_source_layer(tmp_path, monkeypatch):
    _, plan = example(tmp_path, monkeypatch)
    package = dict(players=[copy.deepcopy(r['before_player']) for r in plan['updates']],
        clubs=[{'untouched': True}], artifacts=[])
    monkeypatch.setattr(names.packages, 'validate_package', lambda _: None)
    result = names.bind(package, plan)
    assert result['clubs'] == package['clubs']
    for old, new, row in zip(package['players'], result['players'], plan['updates']):
        assert new == dict(old, name=row['display_name'])
    assert result['artifacts'][0]['sha256'] == names.digest(names.packages.canonical_json_bytes(plan))
    with pytest.raises(ValueError): names.bind(result, plan)
    assert package['players'][0]['name'] == 'Tal'


def test_changed_original_source_plan_is_not_accepted(monkeypatch):
    monkeypatch.setattr(names, 'prepare', lambda _: {'schema': names.SCHEMA, 'original': True})
    with pytest.raises(ValueError, match='no longer reproduces'):
        names.verify(SimpleNamespace(), {'schema': names.SCHEMA, 'original': False})


def test_2015_build_dispatches_name_reconstruction_without_factory_compilation(monkeypatch, tmp_path):
    from scripts import build_registered_quality_release_v1 as builder
    receipt = tmp_path / 'receipt.json'
    receipt.write_text('{}')
    release = SimpleNamespace(season='2015-16', locator={}, compiler_receipt_path=receipt)
    monkeypatch.setattr(builder.registry, 'load_preferred_release', lambda _: release)
    expected = {'complete_game_inventory_identical': True}
    monkeypatch.setattr(names, 'reconstruction', lambda previous, release_id: expected)
    assert builder.build('2015-16', release_id='test') == expected


def test_2015_without_explicit_name_layer_keeps_specialist_build_guard(monkeypatch, tmp_path):
    from scripts import build_registered_quality_release_v1 as builder
    receipt = tmp_path / 'receipt.json'
    receipt.write_text('{}')
    release = SimpleNamespace(season='2015-16', locator={}, compiler_receipt_path=receipt)
    monkeypatch.setattr(builder.registry, 'load_preferred_release', lambda _: release)
    monkeypatch.setattr(names, 'reconstruction', lambda previous, release_id: None)
    with pytest.raises(builder.QualityBuildError, match='manager-graph'):
        builder.build('2015-16', release_id='test')


def test_unrelated_season_does_not_touch_name_replay_inputs():
    assert names.reconstruction(SimpleNamespace(season='2000-01'), 'test') is None


def test_factory_compilation_cannot_silently_discard_name_only_layer():
    with pytest.raises(ValueError, match='must not silently discard'):
        names.reject_factory_recipe({'artifacts': [{'id': names.PREFIX + '2015-16'}]})
    names.reject_factory_recipe({'artifacts': []})


@pytest.mark.parametrize('argument', ['modern_birth_dates', 'manager_plan_path', 'trabzon_opening_plan_path', 'ownership_plan_path'])
def test_name_only_publisher_rejects_mixed_changes_before_writing(monkeypatch, argument):
    from scripts import publish_historical_role_delta_v1 as publisher
    monkeypatch.setattr(publisher.registry, 'load_preferred_release', lambda _: SimpleNamespace())
    with pytest.raises(ValueError, match='cannot mix unrelated'):
        publisher.publish('2015-16', None, release_id='test', name_only_plan_path='names.json', **{argument: True})


def test_edited_recipe_cannot_be_discarded_by_exact_name_replay(tmp_path, monkeypatch):
    _, plan = example(tmp_path, monkeypatch)
    plan['release_id'] = 'baseline'
    monkeypatch.setattr(names.packages, 'validate_package', lambda _: None)
    before = dict(players=[copy.deepcopy(r['before_player']) for r in plan['updates']], artifacts=[])
    after = names.bind(before, plan)
    before_path = tmp_path / 'before.json'
    names.pipeline.write_canonical_json(before_path, before)
    names.pipeline.write_canonical_json(tmp_path / names.FILENAME, plan)
    after['players'][0]['facts']['height_cm'] = 150
    after_path = tmp_path / 'after.json'
    names.pipeline.write_canonical_json(after_path, after)
    monkeypatch.setattr(names.registry, 'load_registered_release', lambda *a: SimpleNamespace(package_path=before_path))
    monkeypatch.setattr(names, 'verify', lambda *a: None)
    with pytest.raises(ValueError, match='no edits discarded'):
        names.reconstruction(SimpleNamespace(season='2015-16', package_path=after_path), 'replay')
