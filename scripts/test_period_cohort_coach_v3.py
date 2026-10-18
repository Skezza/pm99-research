"""Adversarial coupling, provenance, display aliases and exact native writers."""
import copy
import pytest
from scripts import season_period_cohort_coach_v3 as source
from scripts import publish_historical_role_delta_v1 as publisher


@pytest.fixture(scope='module',params=['2002-03','2003-04'])
def case(request):
    base=source.registry.load_registered_release(request.param,'sourced-kiraly-period-profiles-20261017-r141a')
    return base,source.prepare(base)


def test_full_cohort_closed_tenure_and_only_two_name_domains(case):
    base,plan=case;proof=plan['admission'];manager=plan['manager_plan']
    assert proof['represented_source_and_native_people']==25
    assert plan['updates'][0]['after']=='Hertha Berlin'
    assert manager['updates'][0]['after']=='Huub Stevens'
    assert manager['updates'][0]['native_after']=='Stevens'
    assert proof['dated_coach']['decision']['from_date']=='2002-07-01'
    assert proof['dated_coach']['decision']['to_date']=='2003-12-04'
    assert proof['opening_XI_or_kits_approved'] is False
    source.verify_manager_pair(plan,manager)


@pytest.mark.parametrize('damage',['missing','wrong-coach','wrong-owner','wrong-method'])
def test_cannot_pair_label_with_another_manager_plan(case,damage):
    _,plan=case;manager=copy.deepcopy(plan['manager_plan'])
    if damage=='missing':manager=None
    elif damage=='wrong-coach':manager['updates'][0]['after']='Jürgen Röber'
    elif damage=='wrong-owner':manager['updates'][0]['club_carrier_id']=422
    else:manager['source_method']='unreviewed'
    with pytest.raises(ValueError,match='exact dated manager'):source.verify_manager_pair(plan,manager)


def test_recipe_retains_full_identity_and_explicit_short_native_alias(case):
    base,plan=case;package=source.pipeline.read_json_file(base.package_path)
    inert=dict(season=base.season,updates=[])
    updated=publisher.updated_package(package,inert,manager_plan=plan['manager_plan'],club_plan=plan)
    oldplayers=package['players'];assert updated['players']==oldplayers
    before={c['id']:c for c in package['clubs']};after={c['id']:c for c in updated['clubs']}
    assert all(c==after[i] for i,c in before.items() if i!='club-421')
    before={m['id']:m for m in package['managers']};after={m['id']:m for m in updated['managers']}
    assert all(m==after[i] for i,m in before.items() if i!='manager-1313')
    manager=after['manager-1313']
    assert manager['name']=='Huub Stevens'
    assert manager['native_names']==dict(surname='Stevens',display_name='Stevens')
    proof=next(p for p in updated['proofs'] if p['id'].startswith('proof-historical-managers-') and
        p['artifact_id']==manager['proof']['artifact_id'])
    assert proof['covers']==['raw-reparsed-dated-closed-manager-tenure']


def test_existing_manager_plan_keeps_previous_recipe_semantics(case):
    base,plan=case;package=source.pipeline.read_json_file(base.package_path)
    manager_plan=copy.deepcopy(plan['manager_plan']);manager_plan.pop('source_method')
    updated=publisher.updated_package(package,dict(season=base.season,updates=[]),manager_plan=manager_plan)
    manager=next(m for m in updated['managers'] if m['id']=='manager-1313')
    assert 'native_names' not in manager
    proof=next(p for p in updated['proofs'] if p['artifact_id']==manager['proof']['artifact_id'])
    assert proof['covers']==['raw-reparsed-first-fixture-manager-names']
