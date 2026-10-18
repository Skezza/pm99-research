import json
from pathlib import Path
import pytest
from scripts import capture_duplicate_missing_soccerbase_openings_v1 as capture


@pytest.fixture(autouse=True)
def no_real_capture_cache(tmp_path,monkeypatch):
    monkeypatch.setattr(capture,'ROOT',tmp_path)


def target():return {'season':'2021-22','club':'Boreham Wood','native_club_ids':['club-3323'],
    'provider_team_id':None,'provider_identity_candidates':[]}


class Cache:
    def __init__(self,raw):self.raw=raw;self.urls=[];self.root=Path('/not-written')
    def get(self,url,key):self.urls.append(url);return self.raw


def test_original_provider_search_uses_exact_scoped_alias_not_substring():
    c=Cache('<h1>Boreham W Club details</h1><link rel="canonical" href="https://www.soccerbase.com/teams/team.sd?team_id=364">')
    id,proof=capture.resolve_provider(target(),c)
    assert id==364 and proof['published_name']=='Boreham W'
    assert len(c.urls)==1 and 'search=Boreham+Wood' in c.urls[0]
    c.raw=c.raw.replace('Boreham W Club','Boreham Wood Reserves Club')
    with pytest.raises(ValueError):capture.resolve_provider(target(),c)


@pytest.mark.parametrize('href',['https://evil.example/teams/team.sd?team_id=364',
    '/players/player.sd?team_id=364','/teams/team.sd?team_id=364&team_id=365'])
def test_provider_identity_rejects_foreign_host_endpoint_or_ambiguous_ids(href):
    c=Cache(f'<h1>Boreham W Club details</h1><link rel="canonical" href="{href}">')
    with pytest.raises(ValueError):capture.resolve_provider(target(),c)


def test_existing_identity_conflict_cannot_be_replaced_by_a_fresh_search():
    t=target();t['provider_identity_candidates']=[364,999]
    c=Cache('')
    with pytest.raises(ValueError,match='conflict'):capture.resolve_provider(t,c)
    assert c.urls==[]


def test_historical_conference_label_and_explicit_short_names_only():
    assert 'Football Conference' in capture.LEAGUES
    assert capture.provider_matches('Norwich','Norwich City')
    assert not capture.provider_matches('Norwich United','Norwich City')
    assert not capture.provider_matches('Oxford City','Oxford United')
    t=dict(target(),club='Norwich City')
    c=Cache('<h1>Norwich Club details</h1><link rel="canonical" href="https://www.soccerbase.com/teams/team.sd?team_id=1855">')
    assert capture.resolve_provider(t,c)[0]==1855


def test_primary_numeric_catalogue_fallback_is_exact_not_reserve_or_old_club():
    class OriginalCache(Cache):
        def get(self,url,key):
            self.urls.append(url)
            if key=='club-search.html':return '<h1>Teams - Search results</h1>'
            return 'soccer.autocomplete.teamsData = [["West Ham",2802],["West Ham U21",6538],["West Ham Women",7344]];'
    c=OriginalCache('');t=dict(target(),club='West Ham United')
    id,proof=capture.resolve_provider(t,c)
    assert id==2802 and proof['published_names']==['West Ham']
    assert 'numeric-catalogue' in proof['method']
    assert len(c.urls)==2


def test_scope_is_only_missing_english_opening_candidates_and_retains_ambiguity(tmp_path,monkeypatch):
    monkeypatch.setattr(capture,'ROOT',tmp_path)
    root=tmp_path/'.local/season-2021-22';root.mkdir(parents=True)
    (root/'opening-lineup-source-v1.json').write_text(json.dumps({'clubs':[{
        'source_selector':{'club_name':'Boreham W','soccerbase_team_id':364}}]}))
    queue=[{'season':'2021-22','reason':'an-affected-club-lacks-a-verified-opening-source',
        'candidates':[{'club_id':'club-3323','club':'Boreham Wood'},{'club_id':'club-204','club':'Lazio'}]},
        {'season':'2021-22','reason':'other-reason','candidates':[{'club_id':'club-3325','club':'Aldershot'}]}]
    result=capture.discover_targets(queue)
    assert len(result)==1 and result[0]['provider_team_id']==364
    assert result[0]['native_club_ids']==['club-3323']
    (root/'opening-lineup-conflict.json').write_text(json.dumps({'selector':{
        'club_name':'Boreham Wood','soccerbase_team_id':999}}))
    result=capture.discover_targets(queue)
    assert result[0]['provider_team_id'] is None and result[0]['provider_identity_candidates']==[364,999]
