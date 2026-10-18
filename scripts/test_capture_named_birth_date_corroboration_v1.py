import pytest
from scripts import capture_named_birth_date_corroboration_v1 as capture


def wiki(name='Rob Holding', dates=('1995-09-20',)):
    return ('<h1>' + name + '</h1><table class="infobox">' +
        ''.join('<span class="bday">' + d + '</span>' for d in dates) + '</table>').encode()


def test_exact_biography_and_official_dob_are_parsed_without_current_team_or_age():
    assert capture.parse(wiki(), 'Rob Holding', 'wikipedia') == '1995-09-20'
    raw = b'<h1>Ben White</h1><dl><div><dt>Dob</dt><dd>08 October 1997 (28YRS)</dd></div></dl>'
    assert capture.parse(raw, 'Ben White', 'england-profile') == '1997-10-08'


@pytest.mark.parametrize('raw', [wiki('Another Player'), wiki(dates=()),
    wiki(dates=('1995-09-20', '1994-11-09')), wiki(dates=('20/09/1995',)),
    b'<h1>Rob Holding</h1><span class="bday">1995-09-20</span>'])
def test_same_surname_or_unscoped_or_ambiguous_dates_are_not_corroboration(raw):
    with pytest.raises(ValueError): capture.parse(raw, 'Rob Holding', 'wikipedia')


@pytest.mark.parametrize('url', ['http://en.wikipedia.org/wiki/Rob_Holding',
    'https://en.wikipedia.org.evil.example/wiki/Rob_Holding',
    'https://en.wikipedia.org/wiki/Rob_Holding?oldid=wrong',
    'https://user@en.wikipedia.org/wiki/Rob_Holding'])
def test_source_domain_and_exact_article_url_are_enforced(url):
    with pytest.raises(ValueError): capture.validate_url('wikipedia', url)
