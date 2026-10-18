"""Adversarial literal table/date checks, including combined-record lookalikes."""
from datetime import date
import pytest
from bs4 import BeautifulSoup
from scripts import admit_hertha_dated_cohort_coach_20261017 as source


@pytest.fixture(scope='module')
def raw():
    return source.prior.originals.publisher_original(source.external('hertha-original-coach-list-asof2024'))


@pytest.mark.parametrize('opening,name',[
    (date(2001,8,1),'Jürgen Röber'),(date(2002,2,6),'Falko Götz'),
    (date(2002,6,29),'Falko Götz'),(date(2002,7,1),'Huub Stevens'),
    (date(2002,8,1),'Huub Stevens'),(date(2003,8,1),'Huub Stevens'),
    (date(2003,12,4),'Andreas Thom'),(date(2004,8,1),'Falko Götz'),
])
def test_literal_coach_at_date_not_current_or_previous(raw,opening,name):
    assert source.dated_coach(raw,opening)['name']==name


def test_snapshot_does_not_prove_future_opening(raw):
    with pytest.raises(ValueError,match='snapshot'):source.dated_coach(raw,date(2024,8,1))


def test_wrong_club_refused(raw):
    page=BeautifulSoup(raw,'html.parser');page.select_one('h1').string='List of another club managers'
    with pytest.raises(ValueError,match='another club'):source.dated_coach(str(page),date(2002,8,1))


def test_combined_statistics_not_an_independent_chronology(raw):
    page=BeautifulSoup(raw,'html.parser')
    heading=next(h for h in page.select('h2,h3') if h.get_text(' ',strip=True)=='Tenure, wins, draws, losses and winning percentage')
    heading.string='Unreviewed chronology'
    with pytest.raises(ValueError,match='one literal dated coach'):source.dated_coach(str(page),date(2002,8,1))


def test_overlapping_source_rows_refused(raw):
    page=BeautifulSoup(raw,'html.parser');table=page.select_one('table.wikitable')
    row=next(tr for tr in table.select('tr') if 'Huub Stevens' in tr.get_text())
    duplicate=BeautifulSoup(str(row),'html.parser').find('tr');table.append(duplicate)
    with pytest.raises(ValueError,match='unique closed coach'):source.dated_coach(str(page),date(2002,8,1))


def test_invalid_older_source_row_is_exposed_not_silently_fixed(raw):
    result=source.dated_coach(raw,date(2002,8,1))
    assert any('Günter Sebert' in row for row in result['ignored_invalid_historical_rows'])


@pytest.mark.parametrize('season',['2002-03','2003-04'])
def test_primary_sources_corroborate_closed_stevens_spell(season):
    proof=source.stevens_originals(season)
    assert proof['decision']['name']=='Huub Stevens'
    assert len(proof['originals'])==4 and proof['exact_opening_XI_approved'] is False
