import copy
import hashlib
from types import SimpleNamespace
import pytest
from scripts import season_duplicate_layered_packages_v1 as layered
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_package_v2 as package_v2
from scripts.test_season_duplicate_ownership_delta_v1 import fixture
from scripts.test_season_package_compiler_v2 import _indexed_fdi,_dd6361_player_payload


def test_compiler_view_does_not_discard_or_overwrite_other_layer_ids():
    a={'players':[{'id':'a'}],'clubs':[{'id':'ca'}]}
    b={'players':[{'id':'b'}],'clubs':[{'id':'cb'}]}
    assert layered.compiler_view(a,b)=={'players':a['players']+b['players'],'clubs':a['clubs']+b['clubs']}
    b['players'][0]['id']='a'
    with pytest.raises(ValueError):layered.compiler_view(a,b)
    b['players'][0]['id']='b';b['clubs'][0]['id']='ca'
    with pytest.raises(ValueError):layered.compiler_view(a,b)


def test_previous_main_only_lane_keeps_exact_outputs(monkeypatch):
    main,plan=fixture('dd6361');original=_indexed_fdi([(2,'',_dd6361_player_payload(2))])
    before=copy.deepcopy(main)
    expected=delta.updated_package(main,plan);aliases=delta.fit_display_names(original,expected,plan)
    result,english,view,actual_aliases=layered.prepare(None,plan,original,main)
    assert result==expected and english is None and actual_aliases==aliases
    assert view=={'players':result['players'],'clubs':result['clubs']}
    assert main==before


def test_unknown_layer_refused():
    main,plan=fixture();plan['updates'][0]['layer']='other'
    with pytest.raises(ValueError,match='unsupported'):layered.prepare(None,plan,b'',main)


def test_English_without_optin_refused_before_any_native_write(monkeypatch):
    main,plan=fixture('dd6361');plan['updates'][0]['layer']='english'
    monkeypatch.setattr(layered.overlay.planner,'package_layers',lambda r:[])
    with pytest.raises(ValueError):layered.prepare(SimpleNamespace(season='2015-16'),plan,b'',main)


def test_bound_English_repair_changes_only_its_layer_and_main_artifact_hash(tmp_path,monkeypatch):
    from scripts.test_season_duplicate_english_overlay_v1 import fixture as bound
    release,plan,english,_=bound(tmp_path,monkeypatch)
    base,_=fixture('dd6361')
    identifiers={row['id']:'main-'+row['id'] for key in
        ('artifacts','sources','proofs','managers','clubs','players') for row in base[key]}
    def rename(value):
        if isinstance(value,str):return identifiers.get(value,value)
        if isinstance(value,list):return [rename(v) for v in value]
        if isinstance(value,dict):return {k:rename(v) for k,v in value.items()}
        return value
    main=rename(base)
    for key in ('players','clubs','managers'):
        for row in main[key]:row['carrier_id']+=5000
    artifact={'id':layered.overlay.ARTIFACT,'kind':'season-input','media_type':'application/json',
        'relative_path':'english.json','sha256':plan['bindings']['english_overlay']['sha256']}
    main['artifacts']=sorted(main['artifacts']+[artifact],key=lambda a:a['id'])
    layers=[('main',main,tmp_path/'main.json'),('english',english,tmp_path/'english.json')]
    monkeypatch.setattr(layered.planner,'package_layers',lambda r:layers)
    before=copy.deepcopy((main,english,plan))
    original=_indexed_fdi([(1,'',_dd6361_player_payload(1)),(2,'',_dd6361_player_payload(2))])
    result,updated,view,aliases=layered.prepare(release,plan,original,main)
    assert (main,english,plan)==before
    expected_main=copy.deepcopy(main)
    changed=next(a for a in expected_main['artifacts'] if a['id']==layered.overlay.ARTIFACT)
    changed['sha256']=hashlib.sha256(package_v2.canonical_json_bytes(updated)).hexdigest()
    assert result==expected_main
    assert updated['clubs']==english['clubs'] and updated['managers']==english['managers']
    assert updated['players'][0]==english['players'][0]
    assert updated['players'][1]['source_name']=='Alex King'
    assert delta.plan_filename(plan) in [a.get('relative_path') for a in updated['artifacts']]
    selected={plan['updates'][0]['player_id']}
    written=delta.compile_players(original,view,selected,{'ENGLAND':30,'XXX':0})
    assert delta.compile_players(written,view,selected,{'ENGLAND':30,'XXX':0})==written


def test_recipe_layer_switch_is_never_silently_inferred():
    main,plan=fixture('dd6361');plan['updates'][0]['layer']='english'
    with pytest.raises(ValueError,match='explicitly bound'):
        delta.updated_package(main,plan,selected_layer='english')
