"""Adversarial source/native guards, using current actual game preimages."""
import copy
from types import SimpleNamespace
import pytest
from scripts import season_preetz_period_profile_v1 as source


@pytest.fixture(scope='module')
def originals():
    bindings,decision=source.originals()
    raw=[(source.registry.ROOT/b['path']).read_bytes() for b in bindings.values()]
    return raw,decision


def test_originals_reparse(originals):
    raw,decision=originals
    assert source.parse_sources(*raw)==decision
    assert decision['nationality']=='GER'


@pytest.mark.parametrize('old,new',[(b'Michael Preetz',b'Michael Otherx'),(b'1967-08-17',b'1967-08-18'),(b'Nation: Germany',b'Nation: Norway')])
def test_reject_wrong_identity_or_nation(originals,old,new):
    raw,_=originals
    text=' '.join(source.BeautifulSoup(raw[0],'html.parser').get_text(' ',strip=True).split()).encode()
    assert old in text
    with pytest.raises(ValueError):source.parse_sources(text.replace(old,new),raw[1])


@pytest.mark.parametrize('term',[b'1998/99',b'1999',b'2000',b'2003'])
def test_reject_missing_period_role_or_country_continuity(originals,term):
    raw,_=originals
    with pytest.raises(ValueError):source.parse_sources(raw[0],raw[1].replace(term,b'XXXX'))


def test_already_compatible_2002_not_authorized():
    with pytest.raises(ValueError):source.prepare(SimpleNamespace(season='2002-03'))


@pytest.fixture(scope='module',params=['2000-01','2001-02'])
def native_case(request):
    parents={'2000-01':'sourced-hertha-cohort-label-20261017-r137a',
             '2001-02':'sourced-original-alias-countries-20261016-r120a'}
    base=source.registry.load_registered_release(request.param,parents[request.param])
    plan=source.prepare(base)
    return base,plan


def test_exact_actual_two_byte_delta_and_replay(native_case):
    base,plan=native_case
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after,same=source.apply(jug,eq,plan)
    assert same==eq and len(after)==len(jug)
    assert sum(a!=b for a,b in zip(jug,after))==2
    assert source.apply(after,eq,plan)==(after,eq)


@pytest.mark.parametrize('field,value',[('carrier_id',18894),('nationality','NOR'),('fine_roles',[9]),('native_country_code',44)])
def test_plan_tampering_refused(native_case,field,value):
    base,plan=native_case;bad=copy.deepcopy(plan);bad[field]=value
    with pytest.raises(ValueError):source.verify(base,bad)


def test_recipe_skills_dates_names_and_other_people_preserved(native_case):
    base,plan=native_case;package=source.pipeline.read_json_file(base.package_path)
    patched=source.bind(package,plan)
    for old,new in zip(package['players'],patched['players']):
        if old['carrier_id']!=plan['carrier_id']:assert old==new
        else:
            assert new['ratings']==old['ratings'] and new['name']==old['name']
            assert new['facts']['birth_date']==old['facts']['birth_date']
            assert new['facts']['nationality']=='GER' and new['facts']['fine_roles']==[12]
    assert package['clubs']==patched['clubs']


def test_wrong_whole_native_input_refused(native_case):
    base,plan=native_case;jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    with pytest.raises(ValueError):source.apply(bytes([jug[0]^1])+jug[1:],eq,plan)
    with pytest.raises(ValueError):source.apply(jug,bytes([eq[0]^1])+eq[1:],plan)
