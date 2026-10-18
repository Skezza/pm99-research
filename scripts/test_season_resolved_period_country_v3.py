import copy
import pytest
from scripts import season_resolved_period_country_v3 as subject


def test_resolved_country_factory_path_is_explicitly_refused():
    with pytest.raises(ValueError, match='exact SOURCE'):
        subject.reject_factory_recipe(dict(artifacts=[dict(id=subject.PREFIX+'test')]))


def test_unknown_country_native_schema_is_refused_before_any_writer():
    with pytest.raises(ValueError, match='native schema'):
        subject.apply(b'', b'', dict(schema='other'))


def test_unknown_country_recipe_schema_is_refused():
    with pytest.raises(ValueError, match='recipe schema'):
        subject.bind({}, dict(schema='other'))


def test_resolved_country_scope_requires_explicit_unique_country_targets():
    with pytest.raises(ValueError, match='country-only target'):
        subject.prepare(None, None, {'1':['nationality','name']})
    with pytest.raises(ValueError, match='country-only target'):
        subject.prepare(None, None, {'1':['nationality'],'01':['nationality']})


def test_stored_country_resolution_cannot_approve_a_different_final_flag(monkeypatch):
    evidence=dict(nationality='FRA',resolution_rule='exact-target-FIFA')
    monkeypatch.setattr(subject.resolver,'resolve',lambda *args,**kwargs:evidence)
    row=dict(country_resolution_input={'original':'input'},country_resolution=evidence,nationality='FRA')
    assert subject.verify_row_resolution(row,'2016-17',index={},file_sha='source')==evidence
    wrong=copy.deepcopy(row);wrong['nationality']='CGO'
    with pytest.raises(ValueError,match='source choice changed'):
        subject.verify_row_resolution(wrong,'2016-17',index={},file_sha='source')
    wrong=copy.deepcopy(row);wrong['country_resolution']['resolution_rule']='invented'
    with pytest.raises(ValueError,match='source choice changed'):
        subject.verify_row_resolution(wrong,'2016-17',index={},file_sha='source')


def test_untyped_original_evidence_cannot_become_a_native_country_plan(monkeypatch,tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda path:dict(schema='untyped-fact-list',season='2016-17'))
    with pytest.raises(ValueError,match='original typed same-season annual plan'):
        subject.prepare(SimpleNamespace(season='2016-17'),tmp_path/'untyped.json',{'9161':['nationality']})


def test_real_imbula_private_game_is_corrected_with_one_country_byte_only():
    season='2016-17'
    path=subject.registry.ROOT/'.local/consolidated-audit-20261009/country-policy-v2-cohort-20261017/2016-17/country-plan.json'
    release_id='sourced-original-country-policy-cohort-20261017-r129a'
    if not path.exists() or not subject.registry.locator_path(season,release_id).exists():
        pytest.skip('local original private country game unavailable')
    base=subject.registry.load_registered_release(season,release_id)
    plan=subject.prepare(base,path,{'9161':['nationality']})
    assert not plan['unresolved'] and len(plan['updates'])==1
    row=plan['updates'][0]
    assert row['before_player']['facts']['nationality']=='CGO'
    assert row['nationality']=='FRA' and row['native_label']=='FRANCE'
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    changed,after_eq=subject.apply(jug,eq,plan)
    assert len(changed)==len(jug) and after_eq==eq
    assert sum(a!=b for a,b in zip(jug,changed))==1
    assert subject.apply(changed,eq,plan)==(changed,eq)
    before=subject.pipeline.read_json_file(base.package_path)
    after=subject.bind(before,plan)
    originals={p['carrier_id']:p for p in before['players']}
    for player in after['players']:
        if player['carrier_id']!=9161:
            assert player==originals[player['carrier_id']]
    actor=next(p for p in after['players'] if p['carrier_id']==9161)
    expected=copy.deepcopy(row['before_player']);expected['facts']['nationality']='FRA'
    if 'fact_fallbacks' in expected:
        expected['fact_fallbacks']=[f for f in expected['fact_fallbacks'] if f['field']!='nationality']
    assert actor==expected
    assert after['clubs']==before['clubs']
