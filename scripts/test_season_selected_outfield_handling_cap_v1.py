import copy,json
from types import SimpleNamespace
import pytest
from scripts import season_selected_outfield_handling_cap_v1 as cap
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'ROOT',tmp_path)
    game=tmp_path/'game';(game/'DBDAT').mkdir(parents=True)
    for name in ['JUG98030.FDI','EQ98030.FDI']:(game/'DBDAT'/name).write_bytes(b'input')
    (tmp_path/'scripts').mkdir();(tmp_path/'scripts/season_editorial_ratings_v1.py').write_text('original model')
    skills={key:50 for key in ['aggression','dribbling','handling','heading','passing','quality','shooting','speed','stamina','tackling']};skills['handling']=52
    actor={'id':'actor','carrier_id':77,'club_id':'club','name':'Example Person','source_name':'Example Person',
           'facts':{'birth_date':'1973-06-14','primary_position':'M'},
           'ratings':{'profile':'pm99-visible-skills-v1','values':skills,
                      'provenance':{'method':'original','source_ids':['original'],'proof_grade':'reviewed-editorial'}}}
    package={'players':[actor],'clubs':[{'id':'club','carrier_id':335}]}
    path=tmp_path/'package.json';path.write_text(json.dumps(package))
    base=SimpleNamespace(season='2003-04',release_id='parent',manifest_sha256='a'*64,package_path=path,game_path=game)
    selection={'carrier_id':77,'name':'Example Person','birth_date':'1973-06-14','club_carrier_id':335,'before_handling':52}
    request={'schema':cap.INPUT_SCHEMA,'policy':cap.POLICY,'season':base.season,'release_id':base.release_id,
             'parent_manifest_sha256':base.manifest_sha256,'changes':[selection]}
    req=tmp_path/'request.json';req.write_text(json.dumps(request))
    monkeypatch.setattr(cap.ownership,'native_owners',lambda raw:{77:{335}})
    monkeypatch.setattr(cap,'native_facts',lambda *args:{'name':'Example Person','birth_date':'1973-06-14','position':'M'})
    monkeypatch.setattr(cap.identity,'skills',lambda *args:copy.deepcopy(skills))
    return base,req,request,actor


def test_selected_cap_preserves_all_other_nine_values_and_original_provenance(tmp_path,monkeypatch):
    base,path,_,actor=fixture(tmp_path,monkeypatch)
    before=copy.deepcopy(actor);rows,bindings=cap.rows(base,path)
    assert actor==before and len(rows)==1 and rows[0]['before']==before
    updated=rows[0]['ratings']['values'];assert updated['handling']==20
    assert {k:v for k,v in updated.items() if k!='handling'}=={k:v for k,v in before['ratings']['values'].items() if k!='handling'}
    assert rows[0]['ratings']['provenance']['source_ids']==['original',bindings['source_id']]
    assert bindings['source_id'].startswith(cap.SOURCE_ID+'-')
    assert bindings['source_input']['sha256']==registry.sha256_file(path)
    assert bindings['historical_ability_claim'] is False


@pytest.mark.parametrize('change',[{'before_handling':51},{'name':'Another Person'},{'club_carrier_id':336}])
def test_selected_cap_rejects_wrong_preimage_identity_or_owner(tmp_path,monkeypatch,change):
    base,path,request,_=fixture(tmp_path,monkeypatch)
    request['changes'][0].update(change);path.write_text(json.dumps(request))
    with pytest.raises(ValueError):cap.rows(base,path)


def test_selected_cap_cannot_touch_a_goalkeeper(tmp_path,monkeypatch):
    base,path,_,_=fixture(tmp_path,monkeypatch)
    package=json.loads(base.package_path.read_text());package['players'][0]['facts']['primary_position']='G';base.package_path.write_text(json.dumps(package))
    with pytest.raises(ValueError,match='native outfield'):cap.rows(base,path)
