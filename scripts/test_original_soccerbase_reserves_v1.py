from pathlib import Path
import pytest
from scripts import season_original_soccerbase_reserves_v1 as source


def career(team=663,start='01 Aug, 16',end='24 Jan, 18'):
    return f'<table><tr><td><a href="/teams/team.sd?team_id={team}">Any display name</a></td><td>{start}</td><td>{end}</td><td>Unknown</td></tr></table>'.encode()


def test_numeric_provider_club_and_dated_interval_are_required():
    x=source.career_interval(career(),663,'2017-08-08')
    assert x['from_date']=='2016-08-01' and x['to_date']=='2018-01-24'
    with pytest.raises(ValueError):source.career_interval(career(team=1),663,'2017-08-08')


@pytest.mark.parametrize('start,end', [('09 Aug, 17','24 Jan, 18'),('01 Aug, 16','07 Aug, 17'),
    ('Unknown','24 Jan, 18'),('01 Aug, 16','Present')])
def test_late_signing_departure_or_unknown_date_not_an_opening_reserve(start,end):
    with pytest.raises(ValueError):source.career_interval(career(start=start,end=end),663,'2017-08-08')


def test_ambiguous_original_brackets_refused():
    with pytest.raises(ValueError):source.career_interval(career()+career(),663,'2017-08-08')


def test_birth_date_or_broad_role_gap_is_not_silently_filled(tmp_path,monkeypatch):
    path=tmp_path/'74118.html';path.write_bytes(career())
    monkeypatch.setattr(source.pipeline,'read_json_file',lambda _:dict(url='https://www.soccerbase.com/players/player.sd?player_id=74118',sha256=source.registry.sha256_file(path)))
    monkeypatch.setattr(source.source,'player_profile',lambda *a,**k:dict(name='Wade Joyce',birth_date=None,position='M'))
    with pytest.raises(ValueError,match='unresolved'):source.read_profile(path,person_id=74118,team_id=663,day='2017-08-08')


def test_wrong_numerical_profile_url_refused(tmp_path,monkeypatch):
    path=tmp_path/'74118.html';path.write_bytes(career())
    monkeypatch.setattr(source.pipeline,'read_json_file',lambda _:dict(url='https://www.soccerbase.com/players/player.sd?player_id=1',sha256=source.registry.sha256_file(path)))
    with pytest.raises(ValueError,match='URL/hash'):source.read_profile(path,person_id=74118,team_id=663,day='2017-08-08')


def test_original_career_source_does_not_admit_annual_only_facts():
    with pytest.raises(ValueError,match='authority'):
        source.verify_reserve(dict(source_person=dict(provider_player_id=74118),reserve_policy='annual-squad'),
            dict(source_capture=dict(source_path='soccerbase/team/663/august')))
