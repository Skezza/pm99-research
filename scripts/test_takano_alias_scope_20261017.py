import copy
import pytest
from scripts.deliver_takano_period_country_20261017 import check_alias_scope


def fixture():
    rows=[dict(season=f'{y}-{str(y+1)[-2:]}',release_id=f'r{y}',manifest_sha256=str(y)) for y in range(2000,2026)]
    current=[dict(r,locator_path='extra-binding-metadata') for r in rows]
    return dict(bindings=rows,matches=[dict(season='2000-01',layer='main',carrier_id=10992)]),current


def test_scope_checks_exact_manifests_not_additional_binding_presentation_fields():
    scope,current=fixture()
    check_alias_scope(scope,current)
    check_alias_scope(dict(scope,bindings=list(reversed(scope['bindings']))),current)


@pytest.mark.parametrize('problem',['hash','release','missing-season','repeated-season','other-actor','extra-occurrence'])
def test_scope_drift_never_silently_approves_an_incomplete_cascade(problem):
    scope,current=fixture();scope=copy.deepcopy(scope)
    if problem=='hash':scope['bindings'][0]['manifest_sha256']='wrong'
    if problem=='release':scope['bindings'][0]['release_id']='old'
    if problem=='missing-season':scope['bindings'].pop()
    if problem=='repeated-season':scope['bindings'][-1]=scope['bindings'][0]
    if problem=='other-actor':scope['matches'][0]['carrier_id']=10993
    if problem=='extra-occurrence':scope['matches'].append(scope['matches'][0])
    with pytest.raises(ValueError):check_alias_scope(scope,current)
