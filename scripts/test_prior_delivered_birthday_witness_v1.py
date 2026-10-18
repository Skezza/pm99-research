"""Adversarial boundaries for reuse of a delivered original-person proof."""
import copy
import json
from types import SimpleNamespace
import pytest
from scripts import season_prior_delivered_birthday_witness_v1 as subject


@pytest.fixture
def case(tmp_path,monkeypatch):
    path=tmp_path/'proof.json';package=tmp_path/'package.json'
    row=dict(original_full_name='Original Actor',original_numeric_profile=dict(url='https://original.invalid/person/123'),
        birth_date='1984-07-04',before_birth_date='1987-07-04',carrier_id=42)
    plan=dict(schema=subject.birthdays.SCHEMA,season='2006-07',release_id='parent',updates=[row])
    path.write_text(json.dumps(plan))
    artifact=dict(id=subject.birthdays.PREFIX+'2006-07',sha256=subject.registry.sha256_file(path))
    document=dict(players=[dict(carrier_id=42,source_name='Original Actor',facts=dict(birth_date='1984-07-04'))],artifacts=[artifact])
    package.write_text(json.dumps(document))
    release=SimpleNamespace(locator=dict(sourced_profile_assignment_plan_path='proof.json'),package_path=package)
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda *args:release)
    verified=[]
    monkeypatch.setattr(subject.birthdays,'verify',lambda base,original:verified.append(copy.deepcopy(original)))
    bio=dict(source_player_id='soccerbase:123',source_profile_url=row['original_numeric_profile']['url'],name='Original Actor',birth_date='1987-07-04')
    review=dict(name='Original Actor',source_provider_person_id='soccerbase:123',canonical_source_player_id='soccerbase:123',
        published_birth_date='1987-07-04',canonical_birth_date='1984-07-04',
        prior_delivered_birthday_witness=dict(policy=subject.POLICY,season='2006-07',release_id='delivered',
            plan_path='proof.json',plan_sha256=subject.registry.sha256_file(path)))
    annual=dict(players=[dict(name='Original Actor',birth_date='1987-07-04')])
    return review,bio,annual,package,document,verified


@pytest.mark.parametrize('annual_date',['1984-07-04','1987-07-04'])
def test_reuses_same_original_profile_with_proved_or_explicitly_rejected_annual(case,annual_date):
    review,bio,annual,package,document,verified=case
    annual['players'][0]['birth_date']=annual_date
    original=copy.deepcopy((review,bio,annual))
    person=subject.resolve(review,bio,annual)
    assert person['birth_date']=='1984-07-04' and person['source_player_id']=='soccerbase:123'
    assert len(verified)==1 and (review,bio,annual)==original


@pytest.mark.parametrize('change',['hash','numeric-url','canonical-id','arbitrary-date','duplicate-annual','unrelated-annual','wrong-delivered-date','unbound-artifact'])
def test_rejects_unproved_reuse(case,change):
    review,bio,annual,package,document,verified=case
    if change=='hash':review['prior_delivered_birthday_witness']['plan_sha256']='0'*64
    elif change=='numeric-url':bio['source_profile_url']='https://original.invalid/person/999'
    elif change=='canonical-id':review['canonical_source_player_id']='soccerbase:999'
    elif change=='arbitrary-date':review['canonical_birth_date']='1984-07-05'
    elif change=='duplicate-annual':annual['players']*=2
    elif change=='unrelated-annual':annual['players'][0]['birth_date']='1984-07-05'
    elif change=='wrong-delivered-date':
        document['players'][0]['facts']['birth_date']='1987-07-04';package.write_text(json.dumps(document))
    elif change=='unbound-artifact':
        document['artifacts'][0]['sha256']='0'*64;package.write_text(json.dumps(document))
    with pytest.raises(ValueError):subject.resolve(review,bio,annual)
