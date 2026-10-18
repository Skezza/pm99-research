"""Local integration evidence: actual immutable native baseline, no writes."""
import copy
import pytest
from scripts import season_takano_period_country_v1 as source
from scripts import build_takano_period_country_20261017 as build


@pytest.fixture(scope='module')
def fixture():
    path=build.ROOT/'country-plan.json'
    if not path.exists():pytest.skip('local source-bound Takano plan unavailable')
    plan=source.pipeline.read_json_file(path)
    base=source.registry.load_registered_release(plan['season'],plan['release_id'])
    return base,plan,(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(),(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()


def test_actual_country_transaction_is_one_byte_idempotent_and_retains_adopted_date(fixture):
    base,plan,jug,eq=fixture
    changed,same_eq=source.apply(jug,eq,plan)
    assert same_eq==eq and len(changed)==len(jug)
    assert sum(a!=b for a,b in zip(jug,changed))==1
    assert source.apply(changed,eq,plan)==(changed,eq)
    before=source.pipeline.read_json_file(base.package_path);after=source.bind(before,plan)
    old=next(p for p in before['players'] if p['carrier_id']==10992)
    current=next(p for p in after['players'] if p['carrier_id']==10992)
    assert current['facts']['nationality']=='JPN'
    assert current['facts']['birth_date']==old['facts']['birth_date']=='1976-09-30'
    assert current['ratings']==old['ratings']
    assert after['clubs']==before['clubs'] and after['managers']==before['managers']
    assert after['assets']==before['assets']
    assert [p for p in before['players'] if p['carrier_id']!=10992]==[p for p in after['players'] if p['carrier_id']!=10992]


@pytest.mark.parametrize('problem',['other-player-byte','other-club-byte','unknown-postimage','stale-recipe','forged-country','discard-birthday-conflict'])
def test_real_baseline_drift_or_forged_source_decision_refuses(fixture,problem):
    base,plan,jug,eq=fixture
    with pytest.raises(ValueError):
        if problem in ('other-player-byte','unknown-postimage'):
            if problem=='unknown-postimage':jug,_=source.apply(jug,eq,plan)
            altered=bytearray(jug);altered[-1]^=1
            source.apply(bytes(altered),eq,plan)
        elif problem=='other-club-byte':
            altered=bytearray(eq);altered[-1]^=1
            source.apply(jug,bytes(altered),plan)
        elif problem=='stale-recipe':
            package=source.pipeline.read_json_file(base.package_path);package['players'][0]['name']='Other Actor'
            source.bind(package,plan)
        else:
            forged=copy.deepcopy(plan)
            if problem=='forged-country':forged['nationality']='ENG'
            else:forged['birth_date_unchanged_and_explicitly_disputed']=False
            source.verify(base,forged)
