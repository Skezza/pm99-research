import copy

import pytest
from scripts import checkpoint_foreign_stock_delivery_v1 as checkpoint


def inputs():
    player=dict(name='A. Liebeskind',facts=dict(birth_date='1985-01-07',height_cm=178,nationality='VEN'),
        ratings=dict(values={'speed':35,'stamina':41,'aggression':45,'quality':57,'handling':56,
            'passing':49,'dribbling':25,'heading':27,'tackling':33,'shooting':18}))
    review=dict(observed_native_name='A. LIEBESKIND',observed_club='Deportivo Tachira',observed_age=30,
        observed_height='5 ft 10 in',observed_nationality='VENEZUELA',observed_skills=copy.deepcopy(player['ratings']['values']))
    return review,{'club':'Deportivo Tachira'},player,2015,{'VENEZUELA':171}


def test_exact_original_review_matches_source_bound_native_facts():
    assert checkpoint.verify_profile_review(*inputs())


def test_explicit_unpublished_height_matches_actual_native_not_a_source_claim():
    args = list(inputs())
    args[2]['facts']['height_cm'] = {'policy': 'preserve-existing-mode1'}
    assert checkpoint.verify_profile_review(*args, native_height_cm=178)
    with pytest.raises(ValueError, match='actual native readback'):
        checkpoint.verify_profile_review(*args)


def test_fallback_native_height_cannot_override_published_height():
    with pytest.raises(ValueError, match='published source'):
        checkpoint.verify_profile_review(*inputs(), native_height_cm=185)


@pytest.mark.parametrize('height', [{'policy': 'invented'}, None, '178'])
def test_undeclared_height_policy_is_not_a_fallback(height):
    args = list(inputs())
    args[2]['facts']['height_cm'] = height
    with pytest.raises(ValueError, match='undeclared fallback'):
        checkpoint.verify_profile_review(*args, native_height_cm=178)


@pytest.mark.parametrize('cm,inches',[(178,70),(185,72),(191,75),(197,77)])
def test_native_height_uses_truncated_feet_then_remaining_inches(cm,inches):
    assert checkpoint.native_height_display_inches(cm)==inches


def test_197cm_actual_profile_passes_but_nearest_inch_rounding_is_rejected():
    args=list(inputs());args[2]['facts']['height_cm']=197
    args[0]['observed_height']='6 ft 5 in'
    assert checkpoint.verify_profile_review(*args)
    args[0]['observed_height']='6 ft 6 in'
    with pytest.raises(ValueError,match='review differs'):
        checkpoint.verify_profile_review(*args)


@pytest.mark.parametrize('cm',[None,'197',149,251,True])
def test_invalid_native_height_is_rejected(cm):
    with pytest.raises(ValueError,match='invalid native'):
        checkpoint.native_height_display_inches(cm)


@pytest.mark.parametrize('field,value',[('observed_native_name','Different Person'),('observed_club','Cobresal'),
    ('observed_age',31),('observed_height','6 ft 2 in'),('observed_nationality','XXX'),('observed_skills',{'handling':81})])
def test_wrong_person_stats_country_age_or_height_refused(field,value):
    args=list(inputs());args[0][field]=value
    with pytest.raises(ValueError,match='review differs'):
        checkpoint.verify_profile_review(*args)
