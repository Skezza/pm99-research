"""Never choose between duplicate club labels using name order or a few stars."""
from types import SimpleNamespace
import pytest
from scripts import coupled_manager_timeline_admission_20261016 as subject


def fixture(tmp_path, monkeypatch):
    game=tmp_path/'game';(game/'DBDAT').mkdir(parents=True)
    (game/'DBDAT/EQ98030.FDI').write_bytes(b'ab')
    players=[]; clubs=[]
    for cid,start in ((1,100),(2,200)):
        members=[]
        for i in range(11):
            pid=f'p{start+i}';members.append(pid)
            players.append(dict(id=pid,carrier_id=start+i,club_id=f'c{cid}',
                name=f'Player {i}' if cid==1 else f'Other {i}',facts=dict(birth_date=f'1980-01-{i+1:02d}')))
        clubs.append(dict(id=f'c{cid}',carrier_id=cid,roster_player_ids=members))
    captured=dict(country_catalog='italy',club_name='Internazionale',
        players=[dict(name=f'Player {i}',birth_date=f'1980-01-{i+1:02d}') for i in range(11)])
    monkeypatch.setattr(subject.roster,'load_sources',lambda s:([captured],[]))
    status={'status':'raw-source-reparsed'}
    monkeypatch.setattr(subject.roster,'SourceVerifier',lambda s:SimpleNamespace(verify=lambda r:status))
    entries=[SimpleNamespace(record_id=i,payload_offset=i-1,payload_length=1) for i in (1,2)]
    monkeypatch.setattr(subject.roster.IndexedFDIFile,'from_bytes',lambda raw:SimpleNamespace(entries=entries))
    native={b'a':list(range(100,111)),b'b':list(range(200,211))}
    monkeypatch.setattr(subject.roster,'parse_eq_external_team_roster_payload',lambda raw,_:
        SimpleNamespace(rows=[SimpleNamespace(player_record_id=i) for i in native[raw]]))
    return SimpleNamespace(season='2017-18',game_path=game),dict(players=players),clubs,captured,status,native


def test_complete_original_and_native_roster_identifies_exactly_one_carrier(tmp_path,monkeypatch):
    base,package,clubs,*_=fixture(tmp_path,monkeypatch)
    owner,proof=subject.original_roster_owner(base,package,46,clubs)
    assert owner['id']=='c1' and proof['all_native_roster_members_matched']==11
    assert proof['not_opening_squad_or_other_carrier_approval'] is True


def test_two_matching_copies_are_still_ambiguous(tmp_path,monkeypatch):
    base,package,clubs,*_=fixture(tmp_path,monkeypatch)
    for i,p in enumerate(package['players'][11:]):p['name']=f'Player {i}'
    assert subject.original_roster_owner(base,package,46,clubs)==(None,None)


def test_ten_matching_players_are_not_enough_for_an_eleven_member_roster(tmp_path,monkeypatch):
    base,package,clubs,captured,*_=fixture(tmp_path,monkeypatch)
    captured['players'].pop()
    assert subject.original_roster_owner(base,package,46,clubs)==(None,None)


def test_unreplayed_original_does_not_disambiguate_a_club(tmp_path,monkeypatch):
    base,package,clubs,_,status,_=fixture(tmp_path,monkeypatch)
    status['status']='raw-source-unavailable'
    assert subject.original_roster_owner(base,package,46,clubs)==(None,None)


def test_missing_identity_date_does_not_get_name_only_approval(tmp_path,monkeypatch):
    base,package,clubs,*_=fixture(tmp_path,monkeypatch)
    package['players'][0]['facts']['birth_date']=dict(policy='preserve-existing-mode1')
    assert subject.original_roster_owner(base,package,46,clubs)==(None,None)


def test_actual_native_roster_disagreement_is_not_hidden_by_recipe_matches(tmp_path,monkeypatch):
    base,package,clubs,_,_,native=fixture(tmp_path,monkeypatch)
    native[b'a'][-1]=999
    with pytest.raises(ValueError,match='native roster differs'):
        subject.original_roster_owner(base,package,46,clubs)
