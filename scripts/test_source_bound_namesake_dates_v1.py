import copy
from types import SimpleNamespace

import pytest

from scripts import season_source_bound_namesake_dates_v1 as layer


def recipe():
    person = dict(id='person', carrier_id=1, facts={'birth_date':'1985-08-18', 'fine_roles':[9]}, ratings={'handling':9})
    package = dict(players=[person, {'id':'other','carrier_id':2}], clubs=[{'roster_player_ids':['person','other']}],
                   portraits=[{'player_id':'person'}], artifacts=[])
    plan = dict(schema=layer.SCHEMA, season='2006-07',
        package_canonical_sha256=layer.digest(layer.packages.canonical_json_bytes(package)),
        updates=[dict(carrier_id=1, before_player=copy.deepcopy(person),birth_date='1986-07-29')])
    return package, plan


def test_only_exact_birthday_changes_both_namesakes_and_other_facts_retained(monkeypatch):
    package, plan = recipe(); original=copy.deepcopy(package)
    monkeypatch.setattr(layer.packages,'validate_package',lambda p:None)
    result=layer.bind(package,plan)
    assert package==original
    expected=copy.deepcopy(original['players']);expected[0]['facts']['birth_date']='1986-07-29'
    assert result['players']==expected
    for key in ('clubs','portraits'):assert result[key]==original[key]
    assert result['artifacts'][0]['sha256']==layer.digest(layer.packages.canonical_json_bytes(plan))


@pytest.mark.parametrize('problem',['unrelated-edit','person-preimage','duplicate-carrier','duplicate-layer','schema'])
def test_recipe_guard_does_not_discard_edits_or_approve_wrong_person(monkeypatch,problem):
    package,plan=recipe()
    if problem=='unrelated-edit':package['edited']='x'
    if problem=='person-preimage':plan['updates'][0]['before_player']['facts']['birth_date']='1985-08-19'
    if problem=='duplicate-carrier':plan['updates']*=2
    if problem=='duplicate-layer':package['artifacts']=[{'id':layer.PREFIX+plan['season']}];plan['package_canonical_sha256']=layer.digest(layer.packages.canonical_json_bytes(package))
    if problem=='schema':plan['schema']='wrong'
    monkeypatch.setattr(layer.packages,'validate_package',lambda p:None)
    with pytest.raises(ValueError):layer.bind(package,plan)


def test_native_accepts_only_whole_baseline_or_whole_postimage(tmp_path,monkeypatch):
    db=tmp_path/'DBDAT';db.mkdir();(db/'JUG98030.FDI').write_bytes(b'before')
    monkeypatch.setattr(layer.registry,'load_registered_release',lambda *a:SimpleNamespace(game_path=tmp_path))
    monkeypatch.setattr(layer,'rewrite_indexed_native_birth_dates',lambda *a:(b'after',[]))
    plan=dict(schema=layer.SCHEMA,season='2006-07',release_id='base',jug_sha256=layer.digest(b'before'),
              eq_sha256=layer.digest(b'eq'),updates=[{'carrier_id':1}])
    for jug in (b'before',b'after'):assert layer.apply(jug,b'eq',plan)==(b'after',b'eq')
    for jug,eq in [(b'partial',b'eq'),(b'before',b'edited eq')]:
        with pytest.raises(ValueError):layer.apply(jug,eq,plan)
    plan['updates']*=2
    with pytest.raises(ValueError,match='duplicate'):layer.apply(b'before',b'eq',plan)


def test_verify_reparses_original_fixture_and_profiles_not_receipt_only(monkeypatch):
    plan=dict(original_profile_root='cache',original_profile_receipt={'path':'receipt','sha256':'hash'},fixed_case={})
    monkeypatch.setattr(layer.registry,'sha256_file',lambda *a:'hash')
    monkeypatch.setattr(layer,'prepare',lambda *a:copy.deepcopy(plan))
    layer.verify('base',plan)
    changed=dict(plan,updates=[{'birth_date':'wrong'}])
    with pytest.raises(ValueError):layer.verify('base',changed)


def test_normal_builder_dispatches_dates_not_reserve_pruning(tmp_path,monkeypatch):
    from scripts import season_profile_assignment_pruning_layer_v1 as reserve
    path=tmp_path/'plan.json'
    monkeypatch.setattr(reserve.pipeline,'read_json_file',lambda p:{'schema':layer.SCHEMA} if p==path else {})
    monkeypatch.setattr(layer,'reconstruction',lambda *a:{'birthday_replay':True})
    previous=SimpleNamespace(package_path=tmp_path/'package',locator={'sourced_profile_assignment_plan_path':str(path)})
    assert reserve.reconstruction(previous,'replay')=={'birthday_replay':True}


def test_literal_source_removes_only_stale_birthday_fallback(monkeypatch):
    package,plan=recipe()
    package['players'][0]['fact_fallbacks']=[{'field':'birth_date'},{'field':'height_cm'}]
    plan['updates'][0]['before_player']=copy.deepcopy(package['players'][0])
    plan['package_canonical_sha256']=layer.digest(layer.packages.canonical_json_bytes(package))
    monkeypatch.setattr(layer.packages,'validate_package',lambda p:None)
    result=layer.bind(package,plan)
    assert result['players'][0]['fact_fallbacks']==[{'field':'height_cm'}]


def test_factory_refuses_birthday_layer_before_any_native_io(monkeypatch):
    from scripts import season_package_compiler_v2 as compiler
    monkeypatch.setattr(compiler,'_load_native_package',lambda p:({'artifacts':[{'id':layer.PREFIX+'2006-07'}]},'hash'))
    monkeypatch.setattr(compiler,'_ensure_clean_database_inputs',lambda **k:pytest.fail('must refuse before writes'))
    with pytest.raises(compiler.SeasonCompilerError,match='must not discard'):
        compiler.compile_package_to_tree(package_path='recipe',base_tree='base',materialisation_tree='output')
