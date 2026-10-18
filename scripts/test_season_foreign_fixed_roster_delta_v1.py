from types import SimpleNamespace

import pytest

from scripts import season_foreign_fixed_roster_delta_v1 as foreign


@pytest.mark.parametrize('season,year', [('2004-05', '2004'), ('2015-16', '2015'), ('2014-15', '2014')])
def test_kit_proof_identifies_actual_source_period(season, year):
    catalogue = {'period': season, 'source': 'original-photo'}
    artifact = foreign.kit_source_artifact(season, catalogue)
    assert artifact['id'] == ('tachira' if season == '2014-15' else 'ofk') + '-reviewed-period-kit-' + year
    import hashlib
    assert artifact['sha256'] == hashlib.sha256(
        foreign.pipeline.canonical_json_bytes(catalogue) + b'\n').hexdigest()


def test_unknown_kit_period_refused():
    with pytest.raises(ValueError, match='unsupported'):
        foreign.kit_source_artifact('2006-07', {})


def test_sartid_kit_fallback_is_not_labelled_as_ofk_evidence():
    artifact=foreign.kit_source_artifact('2000-01',{})
    assert artifact['id']=='sartid-reviewed-editorial-kit-2000'
    assert artifact['relative_path']=='sartid-editorial-kit-source-2000.json'


def test_jedinstvo_source_period_has_distinct_kit_artifact():
    artifact=foreign.kit_source_artifact('2005-06',{})
    assert artifact['id']=='jedinstvo-reviewed-period-kit-2005'
    assert artifact['relative_path']=='jedinstvo-period-kit-source-2005.json'


def test_borac_source_period_has_distinct_kit_artifact():
    artifact = foreign.kit_source_artifact('2003-04', {})
    assert artifact['id'] == 'borac-reviewed-period-kit-2003'
    assert artifact['relative_path'] == 'borac-period-kit-source-2003.json'


def test_monagas_2003_kit_does_not_overwrite_delivered_borac_source():
    borac = foreign.kit_source_artifact('2003-04', {})
    monagas = foreign.kit_source_artifact('2003-04', {}, carrier=2953)
    assert monagas['id'] == 'monagas-reviewed-period-kit-2003'
    assert monagas['relative_path'] == 'monagas-period-kit-source-2003.json'
    assert monagas['id'] != borac['id']
    assert monagas['relative_path'] != borac['relative_path']


def test_monagas_2002_kit_does_not_overwrite_delivered_hajduk_source():
    hajduk = foreign.kit_source_artifact('2002-03', {})
    monagas = foreign.kit_source_artifact('2002-03', {}, carrier=2953)
    assert monagas['id'] == 'monagas-reviewed-period-kit-2002'
    assert monagas['relative_path'] == 'monagas-period-kit-source-2002.json'
    assert monagas['id'] != hajduk['id']
    assert monagas['relative_path'] != hajduk['relative_path']


def test_italchacao_source_period_has_distinct_kit_artifact():
    artifact = foreign.kit_source_artifact('2001-02', {})
    assert artifact['id'] == 'italchacao-reviewed-period-kit-2001'
    assert artifact['relative_path'] == 'italchacao-period-kit-source-2001.json'


def test_factory_accepts_unrelated_recipe():
    foreign.reject_factory_recipe({'artifacts': [{'id': 'other-input'}]})


def test_factory_refuses_source_bound_recipe():
    with pytest.raises(ValueError, match='discard'):
        foreign.reject_factory_recipe({'artifacts': [{'id': foreign.PREFIX + '2004-05'}]})


@pytest.mark.parametrize('plan', [{}, {'schema_version': foreign.SCHEMA},
    {'schema_version': foreign.SCHEMA, 'source_adapter': 'invented-source'}])
def test_unsupported_adapter_refused_before_native_write(plan):
    with pytest.raises(ValueError, match='unsupported'):
        foreign.verify_plan(plan)


def test_unrelated_compiler_not_misclassified(tmp_path):
    path = tmp_path / 'compiler.json'
    foreign.pipeline.write_canonical_json(path, {'compilation_mode': 'other'})
    assert foreign.reconstruction(SimpleNamespace(compiler_receipt_path=path), 'test') is None


def test_edited_recipe_refused_without_creating_replay(tmp_path, monkeypatch):
    path = tmp_path / 'compiler.json'
    package = tmp_path / 'season-package.json'
    plan = tmp_path / foreign.FILENAME
    foreign.pipeline.write_canonical_json(package, {'edited': True})
    foreign.pipeline.write_canonical_json(plan, {})
    foreign.pipeline.write_canonical_json(path, {'compilation_mode': foreign.MODE,
        'foreign_plan_sha256': foreign.registry.sha256_file(plan), 'season_package_sha256': 'old'})
    monkeypatch.setattr(foreign, 'materialise', lambda *a: pytest.fail('must not write an edited replay'))
    with pytest.raises(ValueError, match='no edits discarded'):
        foreign.reconstruction(SimpleNamespace(compiler_receipt_path=path, package_path=package), 'test')


def test_second_same_season_club_gets_distinct_kit_source_path():
    old=foreign.kit_source_artifact('2015-16',{})
    new=foreign.kit_source_artifact('2015-16',{},carrier=2953)
    assert old['id']=='ofk-reviewed-period-kit-2015'
    assert new['id']=='tachira-reviewed-period-kit-2015'
    assert old['relative_path']!=new['relative_path']


def test_previous_source_plan_retained_not_overwritten(tmp_path):
    original=tmp_path/foreign.FILENAME
    foreign.pipeline.write_canonical_json(original,{'source_adapter':foreign.COUPLED_ADAPTER})
    digest=foreign.registry.sha256_file(original)
    recipe={'artifacts':[dict(id=foreign.PREFIX+'2015-16',relative_path=foreign.FILENAME,sha256=digest)],
        'clubs':[{'proof':{'artifact_id':foreign.PREFIX+'2015-16'}}]}
    paths={}
    foreign.preserve_inherited_plan(recipe,tmp_path,paths)
    artifact=recipe['artifacts'][0]
    assert artifact['id']==recipe['clubs'][0]['proof']['artifact_id']
    assert artifact['sha256']==digest
    assert artifact['relative_path']!=foreign.FILENAME
    assert paths[artifact['relative_path']]==original
    assert foreign.registry.sha256_file(original)==digest


@pytest.mark.parametrize('count',[0,2])
def test_ambiguous_inherited_plan_refused(tmp_path,count):
    recipe={'artifacts':[dict(id=foreign.PREFIX+'2015-16',relative_path=foreign.FILENAME)]*count}
    with pytest.raises(ValueError,match='one explicit'):
        foreign.preserve_inherited_plan(recipe,tmp_path,{})


def test_modified_inherited_source_plan_refused(tmp_path):
    foreign.pipeline.write_canonical_json(tmp_path/foreign.FILENAME,{'edited':True})
    with pytest.raises(ValueError):
        foreign.preserve_inherited_plan({'artifacts':[dict(id=foreign.PREFIX+'2015-16',relative_path=foreign.FILENAME,sha256='0'*64)]},tmp_path,{})


def test_first_source_plan_keeps_delivered_identifier(tmp_path):
    plan = dict(season='2002-03', source_adapter=foreign.HAJDUK_2002_ADAPTER,
                native_club_carrier_id=706)
    result = foreign.next_source_plan_artifact({'artifacts': []}, plan, tmp_path, {})
    assert result['id'] == foreign.PREFIX + '2002-03'
    assert result['relative_path'] == foreign.FILENAME


def test_second_2002_club_preserves_first_source_plan_and_proofs(tmp_path):
    original = tmp_path / foreign.FILENAME
    foreign.pipeline.write_canonical_json(original, {'source_adapter': foreign.HAJDUK_2002_ADAPTER})
    digest = foreign.registry.sha256_file(original)
    prior_id = foreign.PREFIX + '2002-03'
    recipe = {'artifacts': [dict(id=prior_id, relative_path=foreign.FILENAME, sha256=digest)],
              'players': [{'proof': {'artifact_id': prior_id}}]}
    paths = {}
    plan = dict(season='2002-03', source_adapter='future-source-adapter', native_club_carrier_id=2953)
    result = foreign.next_source_plan_artifact(recipe, plan, tmp_path, paths)
    assert result['id'].startswith(prior_id + '-club-2953-')
    assert recipe['players'][0]['proof']['artifact_id'] == prior_id
    assert recipe['artifacts'][0]['id'] == prior_id
    assert recipe['artifacts'][0]['sha256'] == digest
    assert paths[recipe['artifacts'][0]['relative_path']] == original
    assert foreign.registry.sha256_file(original) == digest


def test_delivered_2015_second_plan_identifier_does_not_change(tmp_path):
    original = tmp_path / foreign.FILENAME
    foreign.pipeline.write_canonical_json(original, {'source_adapter': foreign.COUPLED_ADAPTER})
    recipe = {'artifacts': [dict(id=foreign.PREFIX + '2015-16', relative_path=foreign.FILENAME,
                               sha256=foreign.registry.sha256_file(original))]}
    plan = dict(season='2015-16', source_adapter=foreign.TACHIRA_2015_ADAPTER, native_club_carrier_id=2953)
    result = foreign.next_source_plan_artifact(recipe, plan, tmp_path, {})
    assert result['id'] == foreign.PREFIX + '2015-16-club-2953'


def test_ambiguous_second_plan_fails_without_an_artifact(tmp_path):
    recipe = {'artifacts': [dict(id=foreign.PREFIX + '2002-03', relative_path=foreign.FILENAME)] * 2}
    plan = dict(season='2002-03', source_adapter='future-source-adapter', native_club_carrier_id=2953)
    with pytest.raises(ValueError, match='one explicit'):
        foreign.next_source_plan_artifact(recipe, plan, tmp_path, {})
