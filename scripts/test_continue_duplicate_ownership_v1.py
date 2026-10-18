import copy
import json
import pytest
from scripts import continue_duplicate_ownership_v1 as continuation
from scripts import season_release_registry_v1 as registry


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'ROOT',tmp_path)
    def source(relative,text='{}'):
        path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        return {'path':relative,'sha256':registry.sha256_file(path)}
    opening=source('source-root/opening/2015-16/opening-review.json')
    review=source('source-root/reviews/2015-16/report.json')
    return {'season':'2015-16','allow_sourced_outfield_reserve_role_changes':True,
        'allow_published_display_aliases':True,'allow_dated_reserve_owners':True,
        'bindings':{'opening_path':opening['path'],'opening_sha256':opening['sha256'],
            'review_path':review['path'],'review_sha256':review['sha256'],
            'opening_person_supplement_policy':'original-identity-policy',
            'supplemental_opening':source('extra-fixtures.json',json.dumps({'season':'2015-16'})),
            'published_person_supplement':source('people.json'),
            'published_transfer_supplement':source('transfers.json'),
            'soccerbase_opening_sources':{'review':source('soccerbase.json'),'club_entities':source('club-entities.json')}}}


def test_all_original_per_season_inputs_and_flags_survive_continuation(tmp_path,monkeypatch):
    plan=fixture(tmp_path,monkeypatch);before=copy.deepcopy(plan)
    p=continuation.parameters(plan,True)
    assert p['supplemental_opening_path']==tmp_path/'extra-fixtures.json'
    assert p['source_root']==tmp_path/'source-root'
    assert all(p[k] for k in ('with_opening_person_supplement','allow_sourced_outfield_reserve_role_changes',
        'allow_published_display_aliases','allow_dated_reserve_owners','allow_dated_outfield_reserve_role_changes'))
    assert p['published_person_path']==tmp_path/'people.json'
    assert p['published_transfer_path']==tmp_path/'transfers.json'
    assert p['soccerbase_review_path']==tmp_path/'soccerbase.json'
    assert p['soccerbase_club_entities_path']==tmp_path/'club-entities.json'
    assert plan==before


def test_existing_dated_position_policy_is_never_silently_disabled(tmp_path,monkeypatch):
    plan=fixture(tmp_path,monkeypatch);plan['allow_dated_outfield_reserve_role_changes']=True
    assert continuation.parameters(plan)['allow_dated_outfield_reserve_role_changes']


@pytest.mark.parametrize('problem',['changed-supplement','other-season-supplement','changed-people','changed-opening',
    'other-root-review','new-policy-without-existing-policy','outside-workspace'])
def test_changed_omitted_or_cross_season_original_input_is_refused(tmp_path,monkeypatch,problem):
    plan=fixture(tmp_path,monkeypatch)
    if problem=='changed-supplement':(tmp_path/'extra-fixtures.json').write_text('changed')
    if problem=='other-season-supplement':
        path=tmp_path/'extra-fixtures.json';path.write_text(json.dumps({'season':'2016-17'}))
        plan['bindings']['supplemental_opening']['sha256']=registry.sha256_file(path)
    if problem=='changed-people':(tmp_path/'people.json').write_text('changed')
    if problem=='changed-opening':(tmp_path/'source-root/opening/2015-16/opening-review.json').write_text('changed')
    if problem=='other-root-review':
        plan['bindings']['review_path']='people.json';plan['bindings']['review_sha256']=registry.sha256_file(tmp_path/'people.json')
    if problem=='new-policy-without-existing-policy':plan['allow_sourced_outfield_reserve_role_changes']=False
    if problem=='outside-workspace':plan['bindings']['published_person_supplement']['path']='../outside.json'
    with pytest.raises(ValueError):continuation.parameters(plan,True)
