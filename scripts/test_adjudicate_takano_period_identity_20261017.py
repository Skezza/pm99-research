import pytest
from scripts.adjudicate_takano_period_identity_20261017 import parse_news,parse_legacy


def news():
    return ('<time>Tuesday 07 November 2006 19:00 EST</time><p>Keisuke Takano (Japan) The student made history in 1997 when he became the first Japanese to score in the FA Cup. His goal, for Morecambe, came in a 3-3 first-round replay against Emley, who won on penalties.</p>').encode()


def test_news_is_literal_historical_event_not_birthplace_or_baseball_namesake():
    assert parse_news(news())['historical_event_year']==1997
    for old,new in [(b'Japanese',b'English'),(b'Morecambe',b'Another Club'),(b'1997',b'2007'),(b'Keisuke',b'Another'),(b'2006',b'2026')]:
        with pytest.raises(ValueError):parse_news(news().replace(old,new))


def test_aggregate_disagreement_must_be_kept_not_rewritten_to_match_preference():
    raw=b'<table><tr><td>Keisuke "Kenny" Takano</td><td>Japan</td><td>30-Sep-78</td><td>19-Feb-00</td><td>22-Apr-00</td></tr></table>'
    assert parse_legacy(raw)['published_birthday']=='1978-09-30'
    with pytest.raises(ValueError):parse_legacy(raw.replace(b'30-Sep-78',b'30-Sep-76'))
    with pytest.raises(ValueError):parse_legacy(raw+raw)
