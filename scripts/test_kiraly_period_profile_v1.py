"""Adversarial chronology/identity guards and actual eight-season byte checks."""
import copy
import pytest
from scripts import season_kiraly_period_profile_v1 as source

SCOPE=source.registry.ROOT/'.local/consolidated-audit-20261009/haladas2000-opening-keeper-20261017/all26-Kiraly-original-name-native-scope-v95.json'


@pytest.fixture(scope='module')
def raw():
    binding,_=source.original()
    return (source.registry.ROOT/binding['path']).read_bytes()


def test_literal_original_period_country_and_keeper(raw):
    decision=source.parse_source(raw)
    assert decision['nationality']=='HUN' and decision['position']=='G'
    assert decision['national_representation']==dict(from_year=1998,to_year=2016,country='Hungary')
    assert decision['opening_ownership_approved'] is False


@pytest.mark.parametrize('problem',['name','birthday','period','country','position','chronology-heading'])
def test_wrong_original_identity_or_chronology_refused(raw,problem):
    page=source.BeautifulSoup(raw,'html.parser')
    if problem=='name':page.select_one('h1').string='Another goalkeeper'
    if problem=='birthday':page.select_one('.bday').string='1976-04-02'
    changes={'period':('1998–2016','1998–1999'),'country':('Hungary','Germany'),
        'position':('Goalkeeper','Forward'),'chronology-heading':('International career','Unknown career')}
    changed=str(page)
    if problem in changes:
        old,new=changes[problem]
        assert old in changed
        changed=changed.replace(old,new)
    with pytest.raises(ValueError):source.parse_source(changed)


@pytest.mark.parametrize('season',['2008-09','2014-15','2015-16','2018-19'])
def test_correct_scoped_seasons_not_authorized(season):
    with pytest.raises(ValueError):source.prepare(type('Release',(),dict(season=season))())


@pytest.fixture(scope='module',params=list(source.TARGETS))
def case(request):
    season=request.param;scope=source.pipeline.read_json_file(SCOPE)
    row=next(r for r in scope['matches'] if r['season']==season and r['carrier_id']==source.TARGETS[season])
    base=source.registry.load_registered_release(season,row['release_id']);return base,source.prepare(base)


def test_all_eight_exact_native_delta_and_replay(case):
    base,plan=case;jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after,same=source.apply(jug,eq,plan)
    assert len(after)==len(jug) and same==eq
    assert sum(a!=b for a,b in zip(jug,after))==plan['expected_native_byte_changes']
    assert source.apply(after,eq,plan)==(after,eq)
    entry=next(e for e in source.IndexedFDIFile.from_bytes(after).entries if e.record_id==plan['carrier_id'])
    payload=entry.decode_payload(after);native=source.roster.native_player(payload,plan['carrier_id'])
    assert native['position']=='G' and native['roles']==[0,98,98,98,98,98]
    assert payload[native['name_end']+8]^0x61==plan['native_country_code']


def test_recipe_other_people_dates_names_ten_skills_owners_unchanged(case):
    base,plan=case;old=source.pipeline.read_json_file(base.package_path);new=source.bind(old,plan)
    assert old['clubs']==new['clubs'] and old['assets']==new['assets']
    for a,b in zip(old['players'],new['players']):
        if a['carrier_id']!=plan['carrier_id']:assert a==b
        else:
            assert a['name']==b['name'] and a['ratings']==b['ratings'] and a['club_id']==b['club_id']
            assert a['facts']['birth_date']==b['facts']['birth_date']
            assert b['facts']['nationality']=='HUN' and b['facts']['fine_roles']==[0]


def test_tampered_role_or_country_plan_refused(case):
    base,plan=case
    for key,value in [('nationality','GER'),('fine_roles',[12]),('native_country_code',2)]:
        bad=copy.deepcopy(plan);bad[key]=value
        with pytest.raises(ValueError):source.verify(base,bad)
