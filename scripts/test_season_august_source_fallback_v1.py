import pytest
from scripts import season_august_source_fallback_v1 as policy

BINDING = dict(path='original.html', sha256='a'*64)


def args():
    return dict(season='2001-02', fixture_date='2001-08-08', competition='cup',
        source_binding=BINDING, missing_league_xi=True)


def test_august_cup_remains_explicitly_not_league_xi():
    result = policy.lineup(**args())
    assert result['league_starting_xi_missing']
    assert not result['substituted_first_league_xi']


@pytest.mark.parametrize('key,value', [('fixture_date','2001-09-08'),
    ('fixture_date','2002-08-08'), ('competition','league'),
    ('missing_league_xi',False), ('season','2001-03'),
    ('source_binding',dict(path='original.html', sha256='bad'))])
def test_approval_does_not_weaken_other_source_constraints(key, value):
    values = args(); values[key] = value
    with pytest.raises(ValueError): policy.lineup(**values)


def test_published_surname_does_not_invent_first_name_or_provider_id():
    result = policy.surname(published_surname='Trajkovic', provider='dekisa',
        club='Hajduk Kula', fixture_date='2002-08-10', source_binding=BINDING)
    assert result['given_name'] is None
    assert result['cross_provider_person_id'] is None
    assert result['full_name_missing']
