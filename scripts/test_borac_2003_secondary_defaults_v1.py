import copy

import pytest

from scripts import prepare_borac_2003_verified_inputs_v1 as inputs


def proposal():
    rows = [dict(source_person=dict(source_player_id=n),
        source_player=dict(position=role, height_cm=None, weight_kg=None),
        secondary_facts_status=dict(height='unpublished', weight='unpublished'))
        for n, role in enumerate('GDMF', 1)]
    return dict(desired_people=rows, allocation=[dict(replacement=copy.deepcopy(r)) for r in rows])


def test_unpublished_defaults_are_deterministic_explicit_and_keep_both_views_aligned():
    first, second = proposal(), proposal()
    a = inputs.apply_unpublished_physical_defaults(first)
    b = inputs.apply_unpublished_physical_defaults(second)
    assert a == b and first == second
    assert [(r['height_cm'], r['weight_kg']) for r in a] == [(185, 80), (180, 76), (178, 74), (180, 76)]
    assert all(r['historically_sourced'] is False for r in a)
    assert [r['replacement'] for r in first['allocation']] == first['desired_people']


@pytest.mark.parametrize('field,value', [('height_cm', 191), ('weight_kg', 81), ('height_cm', {'policy': 'published'})])
def test_defaults_never_overwrite_a_published_fact_or_partially_mutate(field, value):
    value_before = proposal()
    value_before['desired_people'][-1]['source_player'][field] = value
    snapshot = copy.deepcopy(value_before)
    with pytest.raises(ValueError, match='published physical fact'):
        inputs.apply_unpublished_physical_defaults(value_before)
    assert value_before == snapshot


def test_unknown_broad_role_is_not_silently_given_a_physical_default():
    value = proposal()
    value['desired_people'][-1]['source_player']['position'] = '?'
    before = copy.deepcopy(value)
    with pytest.raises(ValueError, match='supported broad role'):
        inputs.apply_unpublished_physical_defaults(value)
    assert value == before
