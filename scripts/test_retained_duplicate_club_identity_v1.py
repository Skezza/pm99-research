from pathlib import Path
from types import SimpleNamespace
import copy
import pytest
from scripts import season_retained_duplicate_club_identity_v1 as layer


def fixture(monkeypatch):
    root=Path('/evidence');release=SimpleNamespace(season='2012-13',release_id='base',
        package_path=root/'package',game_path=root/'game')
    old={'id':'old','carrier_id':3312,'name':'Barrow'}
    retained={'id':'retained','carrier_id':3325,'name':'Aldershot Town'}
    selector={'club_name':'Barrow','country_catalog':'eng','competition_catalog':'league'}
    original={'date':'2012-08-11','starting_xi':{str(n):'name' for n in range(11)}}
    audit={'schema_version':layer.source.SCHEMA,'season':'2012-13',
        'bindings':dict(release_id='base',package_sha256='hash',eq_sha256='hash',ent_sha256='hash',
            source_row_path='pre',source_row_sha256='hash',original_capture_path='capture',original_capture_sha256='hash'),
        'clubs':[dict(status='source-supported-club-label-mismatch',after='Barrow',before='Aldershot Town',
            club_id='retained',carrier_id=3325,source_selector=selector,evidence=original)]}
    authored=dict(selector=selector,opening_fixture_date='2012-08-11',
        players=[dict(opening_xi_order=n+1,opening_source_player_id=str(n)) for n in range(11)])
    package=dict(clubs=[old,retained],players=[],artifacts=[dict(id='opening-squad-preallocation-2012-13',sha256='hash')])
    documents={root/'audit':audit,root/'package':package,root/'pre':{},
        root/'capture':{'clubs':[dict(source_selector=selector)]}}
    monkeypatch.setattr(layer.registry,'ROOT',root)
    monkeypatch.setattr(layer.registry,'relative_workspace_path',lambda p:p.name)
    monkeypatch.setattr(layer.registry,'sha256_file',lambda p:'hash')
    monkeypatch.setattr(layer.pipeline,'read_json_file',lambda p:documents[p])
    monkeypatch.setattr(layer.source,'indexed_claims',lambda p:({},{}))
    monkeypatch.setattr(layer.source,'unanimous_claim',lambda *a:(authored,None))
    monkeypatch.setattr(layer.source.opening,'verify_opening',lambda *a:copy.deepcopy(original))
    return release,old,root/'audit',audit,authored,package


def test_full_original_authority_admits_only_source_only_retained_identity(monkeypatch):
    release,old,path,audit,authored,package=fixture(monkeypatch)
    club,binding=layer.verified_retained(release,old,path)
    assert club['carrier_id']==3325 and club['name']=='Aldershot Town'
    assert 'remain pending' in binding['approval_scope']


def test_wrong_baseline_is_rejected_before_cohort_or_fixture(monkeypatch):
    release,old,path,audit,_,_=fixture(monkeypatch)
    audit['bindings']['release_id']='other'
    monkeypatch.setattr(layer.source,'unanimous_claim',lambda *a:pytest.fail('must reject earlier'))
    with pytest.raises(ValueError,match='immutable baseline'):layer.verified_retained(release,old,path)


def test_names_and_majority_are_not_complete_authored_authority(monkeypatch):
    release,old,path,*_=fixture(monkeypatch)
    monkeypatch.setattr(layer.source,'unanimous_claim',lambda *a:(None,'mixed original source clubs'))
    with pytest.raises(ValueError,match='unanimously'):layer.verified_retained(release,old,path)


def test_original_xi_numeric_disagreement_is_rejected(monkeypatch):
    release,old,path,_,authored,_=fixture(monkeypatch)
    authored['players'][0]['opening_source_player_id']='another'
    with pytest.raises(ValueError,match='independently reproduce'):layer.verified_retained(release,old,path)


def test_two_retained_candidates_are_rejected_not_selected_by_name(monkeypatch):
    release,old,path,audit,_,_=fixture(monkeypatch)
    audit['clubs'].append(dict(audit['clubs'][0]))
    with pytest.raises(ValueError,match='one exact'):layer.verified_retained(release,old,path)


def test_new_source_identity_policy_cannot_directly_publish(tmp_path):
    from scripts import prepare_duplicate_club_disposition_v1 as whole
    with pytest.raises(ValueError,match='source-only collision'):
        whole.prepare('2012-13',3312,'Wrexham',None,None,None,tmp_path/'output',
            retained_source_label_review_path=tmp_path/'audit')
    assert not (tmp_path/'output').exists()
