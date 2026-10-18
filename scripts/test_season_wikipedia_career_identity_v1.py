import pytest
from scripts import season_wikipedia_career_identity_v1 as wiki
from scripts import season_soccerbase_duplicate_source_policy_v1 as provider


def page(spells, *, extra=''):
    return '<h1>Luigi Sala</h1><table class="infobox"><tr><td><span class="bday">1974-02-21</span></td></tr>' + (
        '<tr><th class="infobox-header">Senior career*</th></tr>' + ''.join(
        f'<tr><th>{years}</th><td>{club}</td><td>1</td><td>0</td></tr>' for years, club in spells)
        + extra + '</table>')


def read(raw, year=2000, url='https://en.wikipedia.org/wiki/Luigi_Sala'):
    return wiki.read(raw, 'Luigi_Sala', url, f'{year}-08-01', 'Milan', 'italy')


def test_independent_full_name_DOB_and_interior_year_without_invented_days():
    person, owner = read(page([('1998–2001', 'AC Milan'), ('2001–2005', 'Atalanta'),
        ('2003–2004', '→ Chievo (loan)')]))
    assert person['name'] == 'Luigi Sala' and person['birth_date'] == '1974-02-21'
    assert owner['owner']['entry_year'] == 1998
    assert owner['exact_transfer_dates_claimed'] is False
    assert provider.person_id(person).startswith('person-wikipedia-')
    assert provider.person_id(person) == provider.person_id(person.copy())


def test_unrelated_video_infobox_is_explicitly_distinguished_from_a_second_biography():
    original = page([('1998–2001', 'AC Milan')])
    raw = original + '<table class="infobox"><tr><td>External videos</td></tr></table>'
    with pytest.raises(ValueError, match='heading and infobox'):
        read(raw)
    person, _ = wiki.read(raw, 'Luigi_Sala', 'https://en.wikipedia.org/wiki/Luigi_Sala',
        '2000-08-01', 'Milan', 'italy', allow_nonperson_infoboxes=True)
    assert person['birth_date'] == '1974-02-21'
    for competing in (original, '<table class="infobox"><span class="bday">1974-02-22</span></table>'):
        with pytest.raises(ValueError, match='heading and infobox'):
            wiki.read(original + competing, 'Luigi_Sala', 'https://en.wikipedia.org/wiki/Luigi_Sala',
                '2000-08-01', 'Milan', 'italy', allow_nonperson_infoboxes=True)


@pytest.mark.parametrize('year', [1998, 2001])
def test_boundary_year_is_not_exact_transfer_evidence(year):
    with pytest.raises(ValueError, match='interior'):
        read(page([('1998–2001', 'AC Milan')]), year)


@pytest.mark.parametrize('other', [('2000', '→ Chievo (loan)'), ('1999–2002', 'Atalanta'),
                                  ('1998–present', 'AC Milan'), ('2001–1998', 'AC Milan')])
def test_overlapping_loan_competing_owner_unbounded_and_reversed_years_refused(other):
    with pytest.raises(ValueError):
        read(page([('1998–2001', 'AC Milan'), other]))


def test_manager_international_and_current_team_never_become_playing_ownership():
    extra = '<tr><th class="infobox-header">Managerial career</th></tr><tr><th>1998–2001</th><td>AC Milan</td></tr>'
    with pytest.raises(ValueError):
        read(page([('1998–2001', 'Inter Milan')], extra=extra))


def test_later_ongoing_spell_is_excluded_without_fabricating_an_exit_year():
    person,owner=read(page([('1998–2001','AC Milan'),('2026–','Fulham')]))
    assert owner['owner']['club']=='AC Milan'
    assert owner['career_rows'][1]['departure_year'] is None
    assert owner['career_rows'][1]['future_open_ended_spell_excluded']


@pytest.mark.parametrize('years,club',[('1999–','AC Milan'),('2000–','AC Milan'),('2026–','')])
def test_ongoing_target_spell_or_empty_future_club_is_still_refused(years,club):
    with pytest.raises(ValueError):read(page([('1998–2001','AC Milan'),(years,club)]))


def month_page(sentence='In January 2004, Belenguer joined Getafe CF, also promoting.'):
    body = page([('2004–2010', 'Getafe')]).replace('Luigi Sala', 'David Belenguer').replace('1974-02-21', '1972-12-17')
    body = body.replace('<td>Getafe</td>', '<td><a href="/wiki/Getafe_CF">Getafe</a></td>')
    return body + '<p>' + sentence.replace('Getafe CF', '<a href="/wiki/Getafe_CF">Getafe CF</a>') + '</p>'


def month_read(raw, anchor='2004-08-01'):
    return wiki.read(raw, 'David_Belenguer', 'https://en.wikipedia.org/wiki/David_Belenguer',
                     anchor, 'Getafe', 'spain', allow_entry_month=True)


def test_explicit_joined_month_proves_before_anchor_without_guessing_day():
    person, owner = month_read(month_page())
    assert owner['entry_month_witness']['latest_possible_entry'] == '2004-01-31'
    assert owner['exact_transfer_dates_claimed'] is False
    assert person['identity_policy'] == wiki.MONTH_POLICY
    assert provider.person_id(person).startswith('person-wikipedia-')


@pytest.mark.parametrize('sentence', [
    'In August 2004, Belenguer joined Getafe CF, also promoting.',
    'In January 2005, Belenguer joined Getafe CF, also promoting.',
    'In January 2004, Belenguer joined Racing, later facing Getafe CF.',
    'In January 2004, Belenguer joined Racing and Getafe CF.',
    'In January 2004, Someone joined Getafe CF, also promoting.',
    'In January 2004, Belenguer joined Getafe CF on loan.',
    'In summer 2004, Belenguer joined Getafe CF.',
])
def test_month_route_refuses_vague_future_other_club_wrong_person_and_loans(sentence):
    with pytest.raises(ValueError): month_read(month_page(sentence))


def test_month_latest_day_and_duplicate_claims_refused():
    with pytest.raises(ValueError): month_read(month_page(), '2004-01-15')
    with pytest.raises(ValueError): month_read(month_page() + '<p>In January 2004, Belenguer joined <a href="/wiki/Getafe_CF">Getafe CF</a>.</p>')


def test_entry_month_is_opt_in_and_cannot_resolve_exit_year():
    with pytest.raises(ValueError):
        wiki.read(month_page(), 'David_Belenguer', 'https://en.wikipedia.org/wiki/David_Belenguer',
                  '2004-08-01', 'Getafe', 'spain')
    with pytest.raises(ValueError): month_read(month_page(), '2010-08-01')


def test_missing_middle_name_needs_exact_literal_full_name_not_inference():
    raw = page([('1998–2001', 'AC Milan')])
    with pytest.raises(ValueError, match='Full name field'):
        wiki.read(raw, 'Luigi_Sala', 'https://en.wikipedia.org/wiki/Luigi_Sala',
                  '2000-08-01', 'Milan', 'italy', expected_name='Luigi Mario Sala')
    raw = raw.replace('<table class="infobox">', '<table class="infobox"><tr><th>Full name</th><td>Luigi Mario Sala<sup>[1]</sup></td></tr>')
    person, _ = wiki.read(raw, 'Luigi_Sala', 'https://en.wikipedia.org/wiki/Luigi_Sala',
                         '2000-08-01', 'Milan', 'italy', expected_name='Luigi Mario Sala')
    assert person['name'] == 'Luigi Mario Sala'


@pytest.mark.parametrize('change', ['name', 'DOB', 'heading', 'URL', 'provider'])
def test_wrong_article_or_ambiguous_identity_or_namespace_refused(change):
    raw = page([('1998–2001', 'AC Milan')])
    url = 'https://en.wikipedia.org/wiki/Luigi_Sala'
    if change == 'name': raw = raw.replace('Luigi Sala', 'Mario Sala')
    elif change == 'DOB': raw = raw.replace('</td></tr>', '<span class="bday">1974-02-22</span></td></tr>', 1)
    elif change == 'heading': raw += '<h1>Another person</h1>'
    elif change == 'URL': url += '?title=another'
    else: url = url.replace('en.wikipedia.org', 'example.org')
    with pytest.raises(ValueError):
        read(raw, url=url)
