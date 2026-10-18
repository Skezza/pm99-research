import copy
import pytest

from scripts import season_exact_primary_position_delta_v2 as subject
from scripts import season_exact_primary_position_delta_v1 as frozen


def actor(name, source_name=None):
    return dict(name=name, source_name=source_name, facts=dict(birth_date='1991-03-29'))


def test_middle_name_bridge_is_exact_published_name_not_fuzzy_annual_matching():
    player = actor('#15 Marten de Roon', 'Marten de Roon')
    row = dict(long_name='Marten Elco de Roon')
    before = copy.deepcopy((player, row))
    assert subject.annual_person_names(player, row) == {
        subject.roster.normalise('Marten Elco de Roon'), subject.roster.normalise('Marten de Roon')}
    assert (player, row) == before


@pytest.mark.parametrize('unproven', ['M. de Roon', 'Elco de Roon', 'Martin de Roon', 'Marten Roon', 'Marten de Roon Junior'])
def test_bridge_does_not_add_unpublished_or_different_names(unproven):
    choices = subject.annual_person_names(actor('Marten de Roon'), dict(long_name='Marten Elco de Roon'))
    assert subject.roster.normalise(unproven) not in choices


def test_unrelated_source_name_is_not_an_alias_even_with_same_birthday():
    choices = subject.annual_person_names(actor('Marten de Roon', 'Dion Donohue'), dict(long_name='Marten Elco de Roon'))
    assert subject.roster.normalise('Dion Donohue') not in choices


def test_v1_source_contract_and_artifact_namespace_are_not_reused():
    assert subject.SCHEMA != frozen.SCHEMA
    assert subject.MODE != frozen.MODE
    assert subject.PREFIX != frozen.PREFIX
    package = dict(artifacts=[dict(id=subject.PREFIX+'proof')])
    with pytest.raises(ValueError, match='exact SOURCE'):
        subject.reject_factory_recipe(package)


@pytest.mark.parametrize('bad', [[], [1, 1], [True], ['1']])
def test_v2_retains_explicit_target_admission_guards(bad):
    with pytest.raises(ValueError, match='explicit unique integer'):
        subject.prepare(None, bad)
