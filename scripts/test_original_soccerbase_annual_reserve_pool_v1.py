import hashlib
import json
import pytest
from scripts import season_original_soccerbase_reserves_v1 as reserves


def fixture(tmp_path, monkeypatch, start='17 Oct, 02'):
    monkeypatch.setattr(reserves.registry,'ROOT',tmp_path)
    root=tmp_path/'.local/season-2003-04/soccerbase-august-cache-v1/player'
    root.mkdir(parents=True)
    path=root/'21.html'
    path.write_text('<table><tr><td><a href="/teams/team.sd?team_id=2847">Woking</a></td>'
        f'<td>{start}</td><td>30 Jun, 07</td><td>100</td></tr></table>')
    path.with_suffix('.html.source.json').write_text(json.dumps({
        'url':'https://www.soccerbase.com/players/player.sd?player_id=21',
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
    facts=dict(name='Neil Smith',birth_date='1971-09-30',position='M')
    monkeypatch.setattr(reserves.source,'player_profile',lambda *a,**k:dict(facts))
    capture=dict(source_path='soccerbase/team/2847/august',players=[])
    actual=dict(source_capture=dict(source_path=capture['source_path']),fixture=dict(date='2003-08-09'))
    annual=dict(players=[dict(facts)])
    return capture,actual,annual


def test_annual_discovers_nonappearing_reserve_but_original_club_date_still_controls(tmp_path,monkeypatch):
    capture,actual,annual=fixture(tmp_path,monkeypatch)
    assert reserves.candidates('2003-04',capture,actual,[])==[]
    rows=reserves.candidates('2003-04',capture,actual,[],annual=annual)
    assert len(rows)==1
    assert rows[0]['source_person']['source_player_id']=='soccerbase:21'
    assert rows[0]['original_provider_career_interval']['from_date']=='2002-10-17'
    assert rows[0]['membership']=='positive-original-provider-dated-opening-reserve'
    assert reserves.verify_reserve(rows[0],actual)==rows[0]


def test_whole_season_annual_cannot_admit_a_later_transfer(tmp_path,monkeypatch):
    capture,actual,annual=fixture(tmp_path,monkeypatch,start='17 Oct, 03')
    assert reserves.candidates('2003-04',capture,actual,[],annual=annual)==[]


@pytest.mark.parametrize('field,value',[('birth_date','1970-09-30'),('position','F'),('name','Other Smith')])
def test_annual_discovery_requires_exact_original_full_name_dob_and_role(tmp_path,monkeypatch,field,value):
    capture,actual,annual=fixture(tmp_path,monkeypatch)
    annual['players'][0][field]=value
    assert reserves.candidates('2003-04',capture,actual,[],annual=annual)==[]


def test_annual_candidate_is_not_inserted_twice_or_merged_with_namesake(tmp_path,monkeypatch):
    capture,actual,annual=fixture(tmp_path,monkeypatch)
    assert reserves.candidates('2003-04',capture,actual,[dict(source_player=dict(name='Neil Smith',position='M'))],annual=annual)==[]
    annual['players'].append(dict(annual['players'][0],birth_date='1980-09-30'))
    with pytest.raises(ValueError,match='repeats a full name'):
        reserves.candidates('2003-04',capture,actual,[],annual=annual)
