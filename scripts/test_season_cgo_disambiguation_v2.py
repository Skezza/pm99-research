import pytest
from scripts import season_cgo_disambiguation_v2 as subject


def html(years='2014–', country='Congo_national_football_team', name='Marvin Baudry', born='1990-01-26'):
    return (f'<h1 id="firstHeading">{name}</h1><table class="infobox">'
        f'<tr><td class="bday">{born}</td></tr><tr><td>{years}</td>'
        f'<td><a href="./{country}">Congo</a></td><td>36</td></tr></table>').encode()


def parse(raw, season='2015-16'):
    return subject.parse(raw, 'Marvin Baudry', '1990-01-26', season, '2026-10-17T03:19:37+00:00')


def test_explicit_since_year_is_not_misread_as_single_year():
    proof = parse(html())
    assert proof['country'] == 'CGO'
    assert proof['dated_national_team_spells'][0]['explicitly_ongoing_at_original_capture']
    assert proof['dated_national_team_spells'][0]['to_year'] is None


@pytest.mark.parametrize('years', ['2019–', '2019', '', '2014–2027', '2018–2014'])
def test_future_undated_or_impossible_spells_are_not_approved(years):
    with pytest.raises(ValueError):
        parse(html(years))


@pytest.mark.parametrize('years', ['2014', '2008–2013', '2014–2014'])
def test_retirement_does_not_erase_an_independently_dated_country_association(years):
    proof = parse(html(years))
    assert proof['country'] == 'CGO'
    assert not proof['dated_national_team_spells'][0]['continuous_target_year_national_team_membership_claimed']


@pytest.mark.parametrize('kwargs', [dict(name='Other Baudry'), dict(born='1990-01-27')])
def test_identity_is_not_inferred(kwargs):
    with pytest.raises(ValueError, match='full-name/DOB'):
        parse(html(**kwargs))


def test_dr_congo_is_not_republic_of_congo():
    assert parse(html(country='DR_Congo_national_football_team'))['country'] == 'COD'


def test_both_congos_is_ambiguous():
    extra = b'<table class="infobox"><tr><td>2014\xe2\x80\x93</td><td><a href="./DR_Congo_national_football_team">DR Congo</a></td></tr></table>'
    with pytest.raises(ValueError, match='ambiguous'):
        parse(html() + extra)


def test_original_2015_three_person_country_batch_is_independently_proved():
    path = subject.CATALOG.parent.parent / 'country-policy-v2-cohort-20261017/2015-16/country-plan.json'
    if not subject.CATALOG.exists() or not path.exists():
        pytest.skip('local original corpus unavailable')
    rows = subject.pipeline.read_json_file(path)['updates']
    assert len(rows) == 3
    for row in rows:
        assert subject.verify(row, '2015-16')['country'] == 'CGO'


def test_original_future_imbula_country_is_not_a_2016_witness():
    path = subject.CATALOG.parent.parent / 'country-policy-v2-cohort-20261017/2016-17/country-plan.json'
    if not subject.CATALOG.exists() or not path.exists():
        pytest.skip('local original corpus unavailable')
    row = next(r for r in subject.pipeline.read_json_file(path)['updates'] if r['carrier_id'] == 9161)
    with pytest.raises(ValueError, match='not established by target season'):
        subject.verify(row, '2016-17')
    with pytest.raises(ValueError, match='dated country: COD'):
        subject.verify(row, '2019-20')
