import copy
import pytest

from scripts import season_biographic_birth_years_v1 as biography


def row(club, name='Josef Bursik', birthday='2000-07-12'):
    return dict(club_name=club, players=[dict(name=name, birth_date=birthday)])


def test_exact_immutable_birthday_can_be_sourced_at_another_club():
    captures = [row('Stoke City'), row('Lincoln City')]
    before = copy.deepcopy(captures)
    assert len(biography.unique_date_witnesses(captures, 'Josef BURSIK', '2000-07-12')) == 2
    assert captures == before


def test_conflicting_original_biographies_refuse_namesake_join():
    assert not biography.unique_date_witnesses([row('A'), row('B', birthday='1980-07-12')],
        'Josef Bursik', '2000-07-12')


def test_initials_surname_and_number_decoration_are_not_fuzzy_aliases():
    for name in ['J. Bursik', 'Bursik', '#1 Josef Bursik', 'Joseph Bursik']:
        assert not biography.unique_date_witnesses([row('A')], name, '2000-07-12')


def test_duplicate_names_within_original_capture_are_ambiguous():
    capture = row('A')
    capture['players'].append(copy.deepcopy(capture['players'][0]))
    assert not biography.unique_date_witnesses([capture], 'Josef Bursik', '2000-07-12')


def test_new_biography_layer_preserves_earlier_birth_year_proof_and_all_facts():
    package = dict(artifacts=[dict(id='sourced-birth-year-plan-2020-21')],
        players=[dict(id='p', facts=dict(birth_date='2000-07-12'), name='Josef Bursik')])
    before = copy.deepcopy(package)
    result = biography.bind(package, dict(season='2020-21', updates=[]))
    assert package == before
    assert result['players'] == before['players']
    assert before['artifacts'][0] in result['artifacts']
    assert len(result['artifacts']) == 2


def test_factory_compile_cannot_drop_original_biography_proof():
    biography.reject_factory_recipe(dict(artifacts=[]))
    with pytest.raises(ValueError, match='must not silently discard'):
        biography.reject_factory_recipe(dict(artifacts=[dict(id=biography.PREFIX + '2020-21')]))
