import copy
import pytest
from scripts import verify_duplicate_batch_components_v1 as verify


def fixture():
    plans = {'a': {'updates': [1, 2]}, 'b': {'updates': [3]}, 'c': {'updates': []}}
    components = {s: {'release_id': 'release', 'verification_scope': 'selected-season-components',
        'players': len(p['updates']), 'seasons': [{'season': s, 'players': len(p['updates'])}],
        'compiler_sha256': 'same'} for s, p in plans.items() if p['updates']}
    return plans, components


def test_exact_components_form_one_complete_native_proof_without_mutation():
    plans, components = fixture()
    before = copy.deepcopy(components)
    result = verify.combine(plans, components, 'release')
    assert result['players'] == 3 and len(result['seasons']) == 2
    assert result['verification_scope'] == 'all-supported-seasons'
    assert components == before


@pytest.mark.parametrize('problem', ['missing-season', 'wrong-release', 'wrong-season', 'wrong-version', 'wrong-count', 'wrong-scope'])
def test_partial_or_mixed_checks_cannot_claim_complete_native_coverage(problem):
    plans, components = fixture()
    if problem == 'missing-season': components.pop('b')
    if problem == 'wrong-release': components['b']['release_id'] = 'other'
    if problem == 'wrong-season': components['b']['seasons'][0]['season'] = 'a'
    if problem == 'wrong-version': components['b']['compiler_sha256'] = 'different'
    if problem == 'wrong-count': components['b']['players'] = 9
    if problem == 'wrong-scope': components['b']['verification_scope'] = 'all-supported-seasons'
    with pytest.raises(ValueError): verify.combine(plans, components, 'release')
