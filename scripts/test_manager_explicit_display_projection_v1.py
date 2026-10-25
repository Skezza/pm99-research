import pytest

from scripts.publish_historical_role_delta_v1 import _validate_manager_display_projection


def plan(full, native):
    return {'native_name_projection': 'explicit-published-family-name-v1',
            'updates': [{'after': full, 'native_after': native}]}


@pytest.mark.parametrize('full,native', [
    ('Sören Åkeby', 'Åkeby'), ('Sören Åkeby', 'Akeby'),
    ('Georges Bregy', 'Bregy'), ('Héctor Cúper', 'Cuper'),
    ('Gian Piero Gasperini', 'Gasperini'), ('Cuca', 'Cuca'),
])
def test_explicit_family_or_retained_single_name(full, native):
    _validate_manager_display_projection(plan(full, native))


@pytest.mark.parametrize('native', ['Sören Åkeby', 'Soren Akeby', 'keby', 'Bregy'])
def test_full_name_clipping_or_different_person_cannot_claim_family_projection(native):
    with pytest.raises(ValueError, match='published surname'):
        _validate_manager_display_projection(plan('Sören Åkeby', native))


@pytest.mark.parametrize('native', ['asperini', 'Bregy', ''])
def test_ambiguous_compound_still_requires_whole_published_tokens(native):
    with pytest.raises(ValueError, match='published surname'):
        _validate_manager_display_projection(plan('Gian Piero Gasperini', native))


def test_other_historical_name_policies_are_unchanged():
    _validate_manager_display_projection({'updates': [{'after': 'Sören Åkeby',
                                                        'native_after': 'Sören Åkeby'}]})
