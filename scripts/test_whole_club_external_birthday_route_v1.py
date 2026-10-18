import pytest
from scripts import prepare_duplicate_club_disposition_v1 as subject
from scripts import season_external_soccerbase_birthday_v1 as external


def fixture():
    starting=[];raw=[]
    for index in range(11):
        url='https://example.invalid/player/'+str(index)
        bio=dict(source_player_id='soccerbase:'+str(index+1),name='Original Player'+str(index),birth_date='1985-01-01',source_profile_url=url)
        starting.append(dict(soccerbase_person=bio,transfermarkt_person=None,dated_match_position='G' if index==0 else 'D',published_match_name=bio['name']))
        raw.append(dict(url=url,path='original'+str(index),sha256='original'))
    url='https://www.soccerbase.com/players/player.sd?player_id=77024'
    bio=dict(source_player_id='soccerbase:77024',name='Lewis Noice',birth_date=None,source_profile_url=url)
    bench=dict(soccerbase_person=bio,transfermarkt_person=None,dated_match_position='G',published_match_name='L Noice')
    raw.append(dict(url=url,path='original-Noice',sha256='original'))
    actual=dict(identity_bridges=dict(starting_xi=starting,published_bench=[bench]),raw_sources=raw)
    review=dict(name='Lewis Noice',published_birth_date=None,canonical_birth_date='1995-09-27',
        canonical_source_player_id='soccerbase:77024',secondary_birthday_policy=external.POLICY)
    return actual,bio,review


def test_original_bench_identity_can_use_explicit_secondary_date_without_a_fake_TM_ID(monkeypatch):
    actual,bio,review=fixture()
    monkeypatch.setattr(external,'resolve',lambda *args:dict(bio,birth_date='1995-09-27',source_provider='soccerbase'))
    people=subject.matchday_people(actual,dict(players=[]),identity_resolutions={'soccerbase:77024':review})
    last=people[-1]
    assert len(people)==12 and last['membership']=='published_bench'
    assert last['source_person']['source_player_id']=='soccerbase:77024'
    assert last['source_player']['birth_date']=='1995-09-27'
    assert last['source_display_aliases']['published_birth_date'] is None
    assert last['source_identity_resolution']==review


def test_secondary_date_does_not_silently_override_a_conflicting_known_annual(monkeypatch):
    actual,bio,review=fixture()
    monkeypatch.setattr(external,'resolve',lambda *args:dict(bio,birth_date='1995-09-27',source_provider='soccerbase'))
    with pytest.raises(ValueError,match='annual source agreement'):
        subject.matchday_people(actual,dict(players=[dict(name='Lewis Noice',birth_date='1996-01-01')]),
            identity_resolutions={'soccerbase:77024':review})
