"""Refuse identity/starter/source tampering; preserve all unrelated records."""
import copy
import pytest
from scripts import season_haladas2000_opening_keeper_v1 as source
from scripts import season_cross_club_reserve_repair_v1 as reserve


@pytest.fixture(scope='module')
def native_case():
    base=source.registry.load_registered_release('2000-01','sourced-preetz-period-profile-20261017-r138a');plan=source.prepare(base)
    return base,plan


def test_source_name_date_country_and_first_keeper_positive(native_case):
    _,plan=native_case;decision=plan['source_decision']
    assert decision['original_fixture']['date']=='2000-07-22'
    assert decision['replacement']['birth_date']=='1972-01-18'
    assert decision['replacement']['nationality']=='HUN'
    assert plan['capacity_claim']['recovery']['exact_shrink_roundtrip'] is True
    assert plan['ratings']['values']['handling']>=35
    assert decision['full_Haladas_opening_XI_or_capacity_squad_approved'] is False


@pytest.mark.parametrize('key,value',[('display_name','Kiraly'),('fine_roles',[9]),('capacity_claim',{}),('jug_sha256','0'*64)])
def test_tampered_native_source_plan_refused(native_case,key,value):
    base,plan=native_case;bad=copy.deepcopy(plan);bad[key]=value
    with pytest.raises(ValueError):source.verify(base,bad)


def test_recipe_only_selected_actor_and_portrait_changes(native_case):
    base,plan=native_case;old=source.pipeline.read_json_file(base.package_path);new=source.bind(old,plan)
    assert old['clubs']==new['clubs']
    for a,b in zip(old['players'],new['players']):
        if a['carrier_id']!=8507:assert a==b
        else:
            assert b['name']=='Kurucsai' and b['source_name']=='Kornél Kurucsai'
            assert b['facts']['nationality']=='HUN' and b['facts']['fine_roles']==[0]
            assert b['facts']['birth_date']=='1972-01-18'
    portrait=next(p for p in new['assets']['portraits'] if p['player_id']=='player-8507')
    assert portrait['status']=='native-no-photo'


def test_real_native_same_slot_and_idempotence(native_case):
    base,plan=native_case
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after,same=source.apply(jug,eq,plan)
    assert len(jug)==len(after) and eq==same
    assert source.apply(after,eq,plan)==(after,eq)
    assert source.admission.native.native_facts(after,2211)==source.admission.native.native_facts(jug,2211)
    assert source.admission.native.native_facts(after,8507)==dict(name='Kurucsai',birth_date='1972-01-18',position='G',startup_order=1)


def test_existing_reserve_policy_still_refuses_starter_keeper(native_case):
    base,plan=native_case;package=source.pipeline.read_json_file(base.package_path)
    actors={p['carrier_id']:p for p in package['players']};clubs={c['id']:c for c in package['clubs']}
    before,keep=actors[8507],actors[2211];eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    with pytest.raises(ValueError,match='starter or keeper'):
        reserve.guard_pair(before,keep,plan['source_decision']['displaced']['native'],plan['source_decision']['retained']['native'],
            source.admission.ownership.native_owners(eq),clubs[before['club_id']],clubs[keep['club_id']])


@pytest.mark.parametrize('problem',['wrong-date','wrong-starter','not-round-one','wrong-country','wrong-birthday'])
def test_original_page_faults_cannot_authorize_replacement(native_case,monkeypatch,problem):
    base,_=native_case;original=source.admission.page
    def changed(key,url):
        page,binding=original(key,url);raw=str(page)
        if problem=='wrong-date' and 'opening-archive' in key:raw=raw.replace('2000.VII.22.','2000.VII.29.')
        if problem=='wrong-starter' and 'opening-archive' in key:raw=raw.replace('Kurucsai','Takács')
        if problem=='not-round-one' and 'opening-archive' in key:raw=raw.replace('1. forduló','2. forduló')
        if problem=='wrong-country' and 'country-row' in key:raw=raw.replace('Hungary','Norway')
        if problem=='wrong-birthday' and 'secondary-player-facts' in key:raw=raw.replace('1972.01.18','1972.01.19')
        return source.admission.BeautifulSoup(raw,'html.parser'),binding
    monkeypatch.setattr(source.admission,'page',changed)
    with pytest.raises(ValueError):source.admission.decision(base)
