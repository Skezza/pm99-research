import pytest
from scripts.season_maccabi_namesake_review_v1 import source_witness


def pages():
    archive = b'''<article><h1 class="entry-title"><a href="https://www.maccabi-tlv.co.il/en/team/tal-ben-haim/">Tal Ben Haim</a></h1><p>born in 1982 central defender June 3, 2015</p></article>
    <article><h1 class="entry-title"><a href="https://www.maccabi-tlv.co.il/en/team/tal-ben-chaim/">Tal Ben Chaim</a></h1><p>winger summer of 2015 2015/16</p></article>'''
    match = b'''<meta property="og:url" content="https://www.fcviktoria.cz/zapas.asp?id=2879"><p class="match-head hidden-mobile">5. 8. 2015, 20:45</p><article class="article-text"><p class="team-name">Maccabi Tel-Aviv</p><p class="font-15">Pablo, Ben Haim I, Ben Haim II</p></article>'''
    return archive, match


def test_distinct_original_people_and_positive_august_match():
    proof = source_witness(*pages())
    assert proof['two_distinct_published_match_people']
    assert not proof['exact_birthdays_independently_verified']
    assert not proof['first_league_fixture_claimed']


@pytest.mark.parametrize('old,new', [
    (b'Ben Haim II', b'Unrelated Player'),
    (b'5. 8. 2015', b'5. 8. 2016'),
    (b'id=2879', b'id=28790'),
    (b'Maccabi Tel-Aviv', b'FC Viktoria'),
    (b'Ben Haim I,', b'Ben Haim II,'),
])
def test_wrong_date_side_person_and_match_refused(old, new):
    archive, match = pages()
    with pytest.raises(ValueError): source_witness(archive, match.replace(old, new))


def test_two_source_urls_required_not_different_dates_alone():
    archive, match = pages()
    with pytest.raises(ValueError): source_witness(archive.replace(b'tal-ben-chaim/', b'tal-ben-haim/'), match)


def test_evidence_must_be_adjacent_to_requested_team():
    archive, match = pages()
    match = match.replace(b'<p class="font-15">', b'<p>Other squad</p><p class="font-15">')
    with pytest.raises(ValueError): source_witness(archive, match)
