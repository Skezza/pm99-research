import pytest
from scripts import project_admitted_country_plan_v1 as subject
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline


def admission():
    return dict(schema=subject.source.SCHEMA,original_person_document=dict(sha256='source-sha'),
        targets={'1':['nationality'],'2':['nationality']},
        updates=[dict(carrier_id=1,fields=['nationality'],nationality='SCO')],unresolved=[dict(carrier_id=2)])


def test_projection_preserves_source_and_does_not_mutate_original():
    original=admission();result=subject.project(original,{'1':['nationality']})
    assert result['updates']==original['updates']
    assert result['unresolved']==[] and original['unresolved']
    assert result['original_person_document']==original['original_person_document']


@pytest.mark.parametrize('targets',[{}, {'2':['nationality']}, {'1':['birth_date']}])
def test_projection_never_admits_a_refused_person_or_changes_scope(targets):
    with pytest.raises(ValueError):subject.project(admission(),targets)


def test_projection_matches_existing_independently_rederived_actual_plan():
    root=registry.ROOT/'.local/consolidated-audit-20261009/original-country-default-delivery-20261017-v1/2014-15'
    if not (root/'country-plan.json').exists():pytest.skip('local original source corpus unavailable')
    original=pipeline.read_json_file(root/'source-admission.json')
    actual=pipeline.read_json_file(root/'country-plan.json')
    assert subject.project(original,actual['targets'])==actual
