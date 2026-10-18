from types import SimpleNamespace
import json

import pytest
from scripts import verify_country_only_ancestry_v1 as subject


def plan(parent='base', **changes):
    value = dict(schema=subject.v2.SCHEMA, season='2009-10', release_id=parent,
        updates=[dict(carrier_id=12, fields=['nationality'])], unresolved=[],
        targets={'12': ['nationality']})
    value.update(changes)
    return value


def release(name):
    return SimpleNamespace(season='2009-10', release_id=name, manifest_sha256=name,
        locator={'sourced_profile_assignment_plan_path': name})


@pytest.mark.parametrize('changes', [
    dict(updates=[]), dict(unresolved=['not-sourced']),
    dict(updates=[dict(carrier_id=12, fields=['birth_date'])]),
    dict(updates=[dict(carrier_id=12, fields=['nationality', 'birth_date'])]),
    dict(updates=[dict(carrier_id=12, fields=['nationality'])] * 2),
    dict(targets={'99': ['nationality']}),
])
def test_refuses_any_non_country_empty_ambiguous_or_unsourced_scope(changes):
    with pytest.raises(ValueError, match='nationality-only'):
        subject.validate_scope(plan(**changes))


def test_exact_scope_is_accepted():
    subject.validate_scope(plan())


def test_native_readback_decodes_container_before_country_field(monkeypatch):
    monkeypatch.setattr(subject.v1.original.audit, 'native_player', lambda payload, carrier: dict(name_end=2))
    entry=SimpleNamespace(payload_offset=4, decode_payload=lambda data: b'\x00'*10+bytes([111 ^ 0x61]))
    assert subject.read_country(entry,b'\x00'*20,12)==(111,14)


def test_walk_requires_explicit_each_parent_and_preserves_order(monkeypatch, tmp_path):
    actual, middle, base = [release(name) for name in ('actual', 'middle', 'base')]
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda path: plan('middle' if path.name == 'actual' else 'base'))
    monkeypatch.setattr(subject.registry, 'load_registered_release', lambda season, name: dict(middle=middle, base=base)[name])
    edges = [subject.Edge(name, name + '-replay', tmp_path) for name in ('actual', 'middle')]
    steps = subject.walk(actual, base, edges)
    assert [(parent.release_id, child.release_id) for parent, child, *_ in steps] == [('base', 'middle'), ('middle', 'actual')]
    with pytest.raises(ValueError, match='missing explicit proof'):
        subject.walk(actual, base, edges[:1])


@pytest.mark.parametrize('schema', ['roster-assignment', 'unknown-country-v3'])
def test_refuses_other_policy_ancestors(monkeypatch, tmp_path, schema):
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda path: plan(schema=schema))
    with pytest.raises(ValueError, match='non-country policy'):
        subject.walk(release('actual'), release('base'), [subject.Edge('actual', 'replay', tmp_path)])


def test_refuses_cycle(monkeypatch, tmp_path):
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda path: plan('actual'))
    with pytest.raises(ValueError, match='cycle'):
        subject.walk(release('actual'), release('base'), [subject.Edge('actual', 'replay', tmp_path)])


def test_refuses_duplicate_descriptor_or_same_game(tmp_path):
    edge = subject.Edge('actual', 'replay', tmp_path)
    with pytest.raises(ValueError, match='duplicate'):
        subject.walk(release('actual'), release('base'), [edge, edge])
    with pytest.raises(ValueError, match='distinct'):
        subject.walk(release('actual'), release('actual'), [edge])


def test_refuses_another_season_source(monkeypatch, tmp_path):
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda path: plan(season='2010-11'))
    with pytest.raises(ValueError, match='another season'):
        subject.walk(release('actual'), release('base'), [subject.Edge('actual', 'replay', tmp_path)])


def edge_fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    source=SimpleNamespace(verify=lambda parent,plan:None,filename=lambda plan:'plan.json',MODE='exact-mode')
    parent=release('base');parent.game_path=tmp_path/'base';parent.game_path.mkdir()
    (parent.game_path/'DBDAT').mkdir()
    (parent.game_path/'DBDAT/JUG98030.FDI').write_bytes(b'fixed native baseline')
    parent.package_path=parent.game_path/'package.json';parent.package_path.write_text('{}')
    children=[]
    for name in ('actual','replay'):
        child=release(name);folder=tmp_path/name;folder.mkdir()
        child.package_path=folder/'package.json';child.package_path.write_text('{}')
        saved=folder/'plan.json';saved.write_text('{}')
        child.locator={'sourced_profile_assignment_plan_path':str(saved.relative_to(tmp_path))}
        child.compiler_receipt_path=folder/'compiler.json'
        child.compiler_receipt_path.write_text(json.dumps(dict(compilation_mode=source.MODE,
            original_profile_assignment_plan_sha256=subject.registry.sha256_file(saved))))
        (folder/'role-delta-input.json').write_text(json.dumps(dict(season=parent.season,
            release_id=parent.release_id,package_sha256=subject.registry.sha256_file(parent.package_path),
            jug_sha256=subject.registry.sha256_file(parent.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[])))
        children.append(child)
    actual,replay=children
    root=tmp_path/'proofs';root.mkdir();(root/'country-plan.json').write_text('{}')
    edge=subject.Edge(actual.release_id,replay.release_id,root)
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda season,name:replay)
    return parent,actual,replay,edge,source,tmp_path/actual.locator['sourced_profile_assignment_plan_path']


def test_refuses_retained_plan_substitution(monkeypatch,tmp_path):
    parent,actual,replay,edge,source,path=edge_fixture(monkeypatch,tmp_path)
    (edge.root/'country-plan.json').write_text('{"tampered":true}')
    with pytest.raises(ValueError,match='retained build proof'):
        subject.verify_edge(parent,actual,edge,source,path,{})


@pytest.mark.parametrize('which', ['actual','replay'])
def test_refuses_actual_or_replay_compiler_binding_forgery(monkeypatch,tmp_path,which):
    parent,actual,replay,edge,source,path=edge_fixture(monkeypatch,tmp_path)
    changed=actual if which=='actual' else replay
    changed.compiler_receipt_path.write_text(json.dumps(dict(compilation_mode='factory-or-other-policy',
        original_profile_assignment_plan_sha256=subject.registry.sha256_file(path))))
    with pytest.raises(ValueError,match='SOURCE compiler or plan binding'):
        subject.verify_edge(parent,actual,edge,source,path,{})


def test_refuses_source_copy_with_another_parent(monkeypatch,tmp_path):
    parent,actual,replay,edge,source,path=edge_fixture(monkeypatch,tmp_path)
    (replay.package_path.parent/'role-delta-input.json').write_text('{"release_id":"wrong-parent"}')
    with pytest.raises(ValueError,match='SOURCE parent descriptor'):
        subject.verify_edge(parent,actual,edge,source,path,{})


def test_refuses_actual_release_reused_as_its_own_source_copy(monkeypatch,tmp_path):
    parent,actual,replay,edge,source,path=edge_fixture(monkeypatch,tmp_path)
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda season,name:actual)
    with pytest.raises(ValueError,match='actual release itself'):
        subject.verify_edge(parent,actual,edge,source,path,{})
