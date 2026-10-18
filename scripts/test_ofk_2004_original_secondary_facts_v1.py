import pytest
from scripts import ofk_2004_original_secondary_facts_v1 as secondary


def desired():
    return [dict(source_person=dict(source_player_id=10, birth_date='1980-01-02'))]


def page(dob='02/01/1980 (24)', country='Serbia', height='6 ft 3 in'):
    cells = [f'<td class="rueckennummer" title="Defender">1</td>',
        '<td><a href="/player/profil/spieler/10">Player</a></td>',
        f'<td>{dob}</td>', f'<td><img class="flaggenrahmen" title="{country}"></td>',
        '<td>Retired</td>', f'<td>{height}</td>', '<td>right</td>',
        '<td>01/07/2004</td>', '<td>Old club</td>', '<td>-</td>']
    return ('<title>OFK Beograd - Detailed squad 04/05</title><table class="items"><tbody><tr>'
        + ''.join(cells) + '</tr></tbody></table>').encode()


def test_stable_person_literal_birthday_and_rounded_declared_height():
    row = secondary.parse(page(), desired())[10]
    assert row['nationality'] == 'SRB' and row['height_cm'] == 191
    assert row['height_policy'] == 'rounded-original-imperial-display-not-exact-centimetre'
    assert row['weight_kg'] is None and row['weight_policy'] == 'unpublished-not-invented'


@pytest.mark.parametrize('country, code', [('Serbia', 'SRB'), ('Montenegro', 'MNE'), ('North Macedonia', 'MKD')])
def test_legacy_jurisdiction_representation_is_explicit(country, code):
    row = secondary.parse(page(country=country), desired())[10]
    assert row['nationality'] == code
    assert row['source_country_label'] == country
    assert 'YUGOSLAVIA' in row['country_representation']


@pytest.mark.parametrize('height', ['N/A', '-', ''])
def test_unknown_height_is_logged_not_fabricated(height):
    row = secondary.parse(page(height=height), desired())[10]
    assert row['height_cm'] is None and row['height_policy'] == 'unpublished'


@pytest.mark.parametrize('raw', [page(dob='03/01/1980 (24)'), page(country='Unmapped'),
    page(height='6 ft 12 in'), page(height='1.9'), page(height='9 ft 0 in'),
    page().replace(b'/spieler/10', b'/spieler/11')])
def test_conflicting_person_date_country_or_unit_refused(raw):
    with pytest.raises(ValueError): secondary.parse(raw, desired())


def test_only_declared_primary_flag_and_annual_not_last_club_used():
    raw = page().replace(b'</td><td>Retired', b'<img class="flaggenrahmen" title="England"></td><td>Retired')
    assert secondary.parse(raw, desired())[10]['nationality'] == 'SRB'


def calendar_page(year=2015, country='Venezuela'):
    return page(country=country).replace(b'OFK Beograd - Detailed squad 04/05',
        f'Deportivo Táchira - Detailed squad {year} (2014/15)'.encode())


def test_explicit_calendar_secondary_facts_never_claim_opening_membership():
    row = secondary.parse(calendar_page(), desired(), expected_calendar_year=2015,
        expected_club_name='Deportivo Táchira', country_codes={'Venezuela': 'VEN'},
        country_representation='native VENEZUELA')[10]
    assert row['nationality'] == 'VEN'
    assert 'NOT opening membership' in row['limitation']
    assert row['source_policy'].startswith('original-explicit-calendar-')


@pytest.mark.parametrize('raw', [calendar_page(2014), calendar_page(country='Unmapped'), page()])
def test_calendar_club_year_and_unmapped_nationality_refused(raw):
    with pytest.raises(ValueError):
        secondary.parse(raw, desired(), expected_calendar_year=2015,
            expected_club_name='Deportivo Táchira', country_codes={'Venezuela': 'VEN'})
