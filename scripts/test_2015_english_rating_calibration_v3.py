"""The English exception must not leak a carrier or mutate non-rating data."""
import copy
from types import SimpleNamespace
import pytest
from scripts import season_2015_english_rating_calibration_v3 as english
from scripts import season_quality_only_delta_v1 as quality
from scripts import season_package_v2 as packages

@pytest.fixture
def example(monkeypatch):
    player=dict(carrier_id=9260,id='afellay',name='Ibrahim Afellay',club_id='stoke',
        facts=dict(primary_position='M',birth_date='1986-04-02'),ratings=dict(values=dict(handling=81)))
    document=dict(players=[player],clubs=[dict(id='stoke',name='Stoke City',roster_player_ids=['afellay'])],
        artifacts=[],sources=[],opening='unchanged')
    monkeypatch.setattr(english,'overlay',lambda base:(document,None))
    monkeypatch.setattr(english.registry,'load_registered_release',lambda season,release:SimpleNamespace())
    monkeypatch.setattr(packages,'validate_package',lambda document:None)
    ratings=dict(values=dict(handling=8),provenance=dict(source_ids=[english.SOURCE_ID]))
    row=dict(carrier_id=9260,layer='english',before_sha256=quality.digest(packages.canonical_json_bytes(player)),ratings=ratings)
    plan=dict(kind=english.KIND,season='2015-16',release_id='baseline',transaction_id='test',updates=[row])
    return document,plan

def test_only_English_ratings_changed_and_input_not_mutated(example):
    document,plan=example;before=copy.deepcopy(document)
    result=english.updated_english(plan)
    assert document==before
    assert result['players'][0]['ratings']['values']['handling']==8
    assert {k:v for k,v in result['players'][0].items() if k!='ratings'}=={k:v for k,v in before['players'][0].items() if k!='ratings'}
    assert result['clubs']==document['clubs'] and result['opening']==document['opening']
    assert result['sources'][-1]['id']==english.SOURCE_ID

def test_foreign_main_players_untouched_with_bound_overlay_hash(example):
    document,plan=example
    main=dict(players=[dict(carrier_id=1790,name='Lionel Messi',ratings={'quality':94})],
        artifacts=[dict(id=english.ARTIFACT,relative_path='english-season-package.json',sha256='old')],
        sources=['unchanged'],clubs=['unchanged'],tactics=['unchanged'])
    original=copy.deepcopy(main);result=english.bind(main,plan)
    assert main==original
    for key in ('players','sources','clubs','tactics'):assert result[key]==original[key]
    artifact=next(a for a in result['artifacts'] if a['id']==english.ARTIFACT)
    assert artifact['sha256']==quality.digest(packages.canonical_json_bytes(english.updated_english(plan)))

def test_changed_English_identity_refuses(example):
    document,plan=example;document['players'][0]['name']='Wrong Person'
    with pytest.raises(ValueError,match='identity/preimage'):english.updated_english(plan)

def test_mixed_English_main_row_refuses(example):
    _,plan=example;plan['updates'][0]['layer']='main'
    with pytest.raises(ValueError,match='mixed English/main'):english.updated_english(plan)

def test_wrong_English_policy_refuses(example):
    _,plan=example;plan['kind']='season-rating-calibration-v3'
    with pytest.raises(ValueError,match='not an English'):english.updated_english(plan)
