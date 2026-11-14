"""Source-only preflight: real slot contract, synthetic evidence, no games/network."""
import copy
from pathlib import Path

import pytest

from scripts import json_storage_io_v1 as io
from scripts import json_storage_v1 as storage
from scripts import season_recipe_preflight_v1 as p


@pytest.fixture
def registry():
    return storage.read_json(p.ROOT/'seasons/2000-01/fixed-carrier-registry.json')


def club(name='Example', country='germany', pid='1', comp='bundes', players=None):
    return dict(club_name=name,country_catalog=country,competition_catalog=comp,provider_club_id=pid,
        status='parsed-year-checked-annual-source',players=players or [],source_path=f'squad/1990/L1/{pid}.html',source_sha256='a'*64)


def test_full_denominator_including_all_non_picker_carriers(registry):
    rows=p.inventory_slots(registry)
    assert len(rows)==len({r['carrier_id']for r in rows})==543
    assert sum(r['lane']=='foreign'for r in rows)==451
    assert {3306,3311,333}<={r['carrier_id']for r in rows if r['lane']=='english'}
    classified,_=p.classify_slots(rows,[])
    assert len(classified)==543 and all(not r['opening_ownership_verified']for r in classified)


def test_bad_or_incomplete_registry_never_shrinks_denominator(registry):
    registry['carriers'].pop()
    with pytest.raises(ValueError,match='451'):
        p.inventory_slots(registry)


def test_name_is_candidate_only_and_no_containment_country_or_unknown_group_match():
    slot=dict(carrier_id=400,lane='foreign',native_name='Example',native_country_family='germany',division=None)
    candidates=[club('FC Example'),club('Example',country='france')]
    rows,_=p.classify_slots([slot],candidates)
    assert rows[0]['status']=='no-exact-source-candidate'
    rows,_=p.classify_slots([slot],[club()])
    assert rows[0]['status']=='annual-source-candidate' and not rows[0]['historical_identity_verified']
    slot['native_country_family']=None
    rows,_=p.classify_slots([slot],[club(country='unknown')])
    assert rows[0]['status']=='no-exact-source-candidate'


def test_duplicate_candidates_are_not_arbitrarily_resolved():
    slot=dict(carrier_id=400,lane='foreign',native_name='Example',native_country_family='germany',division=None)
    rows,_=p.classify_slots([slot],[club(pid='1'),club(pid='2')])
    assert rows[0]['status']=='ambiguous-name-candidates' and rows[0]['candidate_count']==2


def test_english_capacity_order_is_only_a_proposal_and_reports_overflow():
    slot=dict(carrier_id=301,lane='english',native_name=None,native_country_family='england',division='Premier League')
    a,b=club('B',country='eng',comp='faprem'),club('A',country='eng',pid='2',comp='faprem')
    x=p.classify_slots([slot],[a,b]);y=p.classify_slots([slot],[b,a])
    assert x==y and len(x[1])==1
    assert x[0][0]['candidate']['club_name']=='A'
    assert x[0][0]['match_method']=='division-capacity-proposal-not-authoring'


@pytest.mark.parametrize('title,accepted', [('Detailed squad 90/91',True),('Detailed squad 1990/1991',True),
    ('Detailed squad 1991/92',False),('Founded in 1990 - current squad',False),('Detailed squad 1990',False)])
def test_split_season_requires_pair_in_actual_title(tmp_path,title,accepted):
    path=tmp_path/'squad/1990/L1/1.html';path.parent.mkdir(parents=True)
    io.write_bytes(path,f'<html><title>{title}</title><body>{"x"*1200}</body></html>'.encode())
    cache=p.VerifiedOfflineCache(tmp_path,1990)
    if accepted:assert cache.get('https://www.transfermarkt.com/example/kader/verein/1/saison_id/1990','squad/1990/L1/1.html')
    else:
        with pytest.raises(p.CaptureError,match='mismatch'):
            cache.get('https://www.transfermarkt.com/example/kader/verein/1/saison_id/1990','squad/1990/L1/1.html')


def test_missing_cache_is_fetch_request_not_network(tmp_path):
    cache=p.VerifiedOfflineCache(tmp_path,1990)
    with pytest.raises(p.CaptureError,match='missing'):
        cache.get('https://www.transfermarkt.com/test/saison_id/1990','squad/1990/L1/1.html')
    assert len(cache.missing)==1 and cache.used=={}


def test_calendar_cache_key_and_title_are_distinct(tmp_path):
    route=p.calendar.route_provider_year(1990,'NO1','norway')
    key=p.calendar.cache_key(kind='squad',target_year=1990,provider_year=route.provider_season_id,code='NO1',club_id=1)
    assert key=='squad-calendar-route-v1/1990/1989/NO1/1.html'
    path=tmp_path/key;path.parent.mkdir(parents=True);io.write_bytes(path,b'<title>Detailed squad 1991</title>'+b'x'*1200)
    with pytest.raises(p.CaptureError,match='mismatch'):
        p.VerifiedOfflineCache(tmp_path,1990).get('https://www.transfermarkt.com/test/saison_id/1989',key)


def test_provider_ids_missing_dob_and_ambiguous_names_not_collapsed(registry,tmp_path):
    players=[dict(name='A Smith',birth_date=None,source_identity=dict(provider='transfermarkt',player_id=str(i)))for i in [1,2]]
    players += [dict(name='J Smith',birth_date=None),dict(name='J Smith',birth_date=None)]
    c=club(players=players)
    report=p.assemble_report('1990-91',registry,[c],[],[],p.VerifiedOfflineCache(tmp_path,1990),[])
    assert report['coverage']['parsed_player_rows']==4 and report['coverage']['unique_provider_ids']==2
    assert len(report['same_name_unidentified_candidates'])==1
    assert report['coverage']['opening_owner_verified']==0 and not report['full_d1_complete']


def test_logical_compressed_registry_and_shared_frame_not_mutated(registry,tmp_path):
    path=tmp_path/'registry.json';alias=tmp_path/'alias.json'
    storage.write_bytes(path,p.canonical(registry),compressed=True,overwrite=False)
    io.link(path,alias)
    before=storage.sha256_file(path);frame=storage.physical_path(path);meta=frame.stat()
    assert p.inventory_slots(storage.read_json(path))==p.inventory_slots(registry)
    assert storage.sha256_file(alias)==before==storage.sha256_file(path)
    assert frame.stat().st_ino==meta.st_ino and frame.stat().st_nlink==2


def test_new_output_only_and_exact_lock_hash(registry,tmp_path):
    report=p.assemble_report('1990-91',registry,[],[],[],p.VerifiedOfflineCache(tmp_path,1990),[])
    a=tmp_path/'a';b=tmp_path/'b'
    assert p.write_outputs(a,report)==p.write_outputs(b,copy.deepcopy(report))
    assert storage.read_json(a/'input-lock.json')['expected_report_sha256']==p.digest(p.canonical(report))
    with pytest.raises(ValueError,match='new'):
        p.write_outputs(a,report)


@pytest.mark.parametrize('value',['1990-92','1990','1990-90','hello'])
def test_bad_season_is_rejected(value):
    with pytest.raises(ValueError):p.season_year(value)


@pytest.mark.parametrize('title',['Founded 1990 - Squad 1988/89','Squad 1991; founded 1990','Squad 1989/90 / 1990/91'])
def test_calendar_foundation_year_or_conflicting_pair_is_not_source_year(tmp_path,title):
    path=tmp_path/'calendar.html';io.write_bytes(path,f'<title>{title}</title>{"x"*1200}'.encode())
    with pytest.raises(p.CaptureError,match='mismatch'):
        p.VerifiedOfflineCache(tmp_path,1990).get('https://www.transfermarkt.com/test/saison_id/1989','calendar.html')


def test_failed_probe_replays_without_network_and_keeps_frozen_failure(tmp_path,monkeypatch):
    from urllib.error import HTTPError
    calls=[]
    def denied(self,url,key):
        calls.append(url);raise HTTPError(url,403,'Forbidden',{},None)
    monkeypatch.setattr(p.BoundedProbeCache,'get',denied)
    monkeypatch.setattr(p.time,'sleep',lambda _:None)
    c=club();c['players']=[dict(name='Test')];c['source_url']='https://www.transfermarkt.com/example/kader/verein/1/saison_id/1990'
    a=p.probe_managers([c],1,'1990-08-31',tmp_path,offline=False)
    b=p.probe_managers([c],1,'1990-08-31',tmp_path,offline=True)
    assert a==b and len(calls)==1 and a[0][0]['failure']['http_status']==403


def test_probe_limits_and_locked_missing_inputs_fail(tmp_path):
    for n in [0,5,True]:
        with pytest.raises(ValueError,match='between'):p.probe_managers([],n,'1990-08-31',tmp_path,offline=True)
    c=club(players=[dict(name='Test')]);c['source_url']='https://www.transfermarkt.com/example/kader/verein/1/saison_id/1990'
    with pytest.raises(ValueError,match='locked probe source'):
        p.probe_managers([c],1,'1990-08-31',tmp_path,offline=True)


def test_local_source_snapshot_counts_and_hash_pinning(tmp_path):
    duckdb=pytest.importorskip('duckdb')
    database=tmp_path/'source.duckdb';receipt=tmp_path/'pin.json'
    c=duckdb.connect(str(database))
    c.execute("CREATE TABLE version AS SELECT 'test' AS version")
    c.execute('CREATE TABLE transfers(player_id INTEGER,transfer_date DATE)')
    c.execute("INSERT INTO transfers VALUES (1,'1989-07-01'),(1,'1990-08-01'),(2,'1990-09-01')")
    c.execute('CREATE TABLE games(season INTEGER)');c.execute('INSERT INTO games VALUES (1990),(2015)');c.close()
    h=io.physical_sha256_file(database)
    storage.write_bytes(receipt,p.canonical(dict(source=dict(database_sha256=h,database_version='test'))),compressed=False)
    result=p.snapshot_coverage(database,receipt,1990,['1','3'])
    assert [r['transfer_rows']for r in result['transfer_rows_by_year']]==[1,2,0]
    assert result['captured_people_with_period_transfer_rows']==1 and result['games_in_target_season']==1
    assert not result['dated_ownership_verified'] and io.physical_sha256_file(database)==h
    storage.write_bytes(receipt,p.canonical(dict(source=dict(database_sha256='0'*64,database_version='test'))),compressed=False,overwrite=True)
    with pytest.raises(ValueError,match='differs'):p.snapshot_coverage(database,receipt,1990,['1'])


def test_retired_competition_name_is_not_selected_season(tmp_path):
    title='First Division (- 91/92) 90/91 | Transfermarkt'
    io.write_bytes(tmp_path/'page.html',f'<title>{title}</title>{"x"*1200}'.encode())
    cache=p.VerifiedOfflineCache(tmp_path,1990)
    cache.get('https://www.transfermarkt.com/test/saison_id/1990','page.html')
    assert cache.title_checks['page.html']['matched']


def test_english_capacity_is_separate_from_foreign_source_matches(registry,tmp_path):
    c=club('A',country='eng',comp='faprem',players=[dict(name='Test')])
    report=p.assemble_report('1990-91',registry,[c],[],[],p.VerifiedOfflineCache(tmp_path,1990),[])
    assert report['coverage']['division_capacity_proposals']==1
    assert report['coverage']['candidate_slots_with_annual_source']==0


def test_unmatched_sources_and_repeated_page_observations_are_explicit(registry,tmp_path):
    c=club('Unmapped club',country='unmapped',players=[dict(name='Test',source_identity=dict(provider='transfermarkt',player_id='1'))])
    other=dict(c,competition_catalog='another-scope')
    report=p.assemble_report('1990-91',registry,[c,other],[],[],p.VerifiedOfflineCache(tmp_path,1990),[])
    assert len(report['source_clubs_without_slot'])==2
    assert report['coverage']['source_club_observations']==2
    assert report['coverage']['parsed_squad_pages']==report['coverage']['parsed_player_rows']==1
    assert report['cross_club_identity_claims']==[]


def test_successful_competition_alias_removes_failed_alias_fetch_request(tmp_path,monkeypatch):
    cache=p.VerifiedOfflineCache(tmp_path,1990)
    monkeypatch.setattr(p.squads,'competition_code_candidates',lambda *_:['old','new'])
    def teams(**kwargs):
        if kwargs['competition_code']=='old':
            cache.missing['old.html']=dict(cache_key='old.html',url='https://example.com',reason='missing')
            raise p.CaptureError('missing alias')
        from types import SimpleNamespace
        return [SimpleNamespace(club_id=1,club_path='/example/startseite/verein/1',transfermarkt_name='Example')]
    monkeypatch.setattr(p,'_competition_teams',teams)
    scope=dict(country_catalog='eng',competition_catalog='faprem',source_competition_code='GB1')
    p.replay_sources(1990,[scope],cache)
    assert 'old.html' not in cache.missing
    assert len(cache.missing)==1  # The real missing squad remains actionable.


def test_cli_lock_mismatch_does_not_publish_outputs(registry,tmp_path,monkeypatch):
    report=p.assemble_report('1990-91',registry,[],[],[],p.VerifiedOfflineCache(tmp_path,1990),[])
    monkeypatch.setattr(p,'run',lambda *args,**kwargs:report)
    lock=tmp_path/'lock.json';output=tmp_path/'not-published'
    storage.write_bytes(lock,p.canonical(dict(report['input_lock'],expected_report_sha256='0'*64)),compressed=True)
    with pytest.raises(SystemExit) as exc:
        p.main(['1990-91','--lock',str(lock),'--output-dir',str(output)])
    assert exc.value.code==2 and not output.exists()
