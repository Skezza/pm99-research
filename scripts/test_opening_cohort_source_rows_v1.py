import pytest

from scripts import season_opening_cohort_delta_core_v1 as cohort


@pytest.mark.parametrize('season, birthday, expected', [
    (2000, '20-02-66', '1966-02-20'),
    (1990, '01-06-65', '1965-06-01'),
    (1920, '02-03-99', '1899-03-02'),
    (2017, '16-10-95', '1995-10-16'),
    (2025, '13-07-07', '2007-07-13'),
    (2000, '20-02-1966', '1966-02-20'),
    (2000, '1966-02-20', '1966-02-20'),
])
def test_published_short_years_use_target_season_not_strptime_century_cutoff(season, birthday, expected):
    row = f'8, Example Player, SEN, M, 1.89, 84, {birthday}'
    actual = cohort._parse_footballsquads_row(row, season_start_year=season)
    assert actual['birth_date'] == expected
    assert actual['height_cm'] == 189


def test_secondary_facts_can_be_missing_without_losing_name_or_position():
    row = cohort._parse_footballsquads_row('8, Example Player, ?, M, , unknown, -',
                                         season_start_year=2000)
    assert row['name'] == 'Example Player'
    assert row['primary_position'] == 'M'
    assert all(row[key] is None for key in ('nationality', 'height_cm', 'weight_kg', 'birth_date'))


def test_explicit_four_digit_year_is_not_silently_rewritten():
    row = cohort._parse_footballsquads_row('8, Example Player, ENG, F, , , 01-01-2005',
                                         season_start_year=2000)
    assert row['birth_date'] == '2005-01-01'  # chronology QA must see the actual source fact


def test_invalid_published_birthday_is_rejected():
    with pytest.raises(cohort.CohortDeltaError, match='source row cannot be parsed'):
        cohort._parse_footballsquads_row('8, Example Player, ENG, F, , , 31-02-95',
                                       season_start_year=2000)
