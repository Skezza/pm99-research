import pytest

from scripts.review_becej_opening_sources_20261010 import article, resolve_label


def test_surname_namesakes_never_choose_first():
    roster = [{'name': 'Bojan Ćulum'}, {'name': 'Nikola Ćulum'}]
    result = resolve_label('Ćulum', roster)
    assert result['full_name'] is None
    assert result['candidate_names'] == ['Bojan Ćulum', 'Nikola Ćulum']


def test_published_initial_resolves_only_exact_candidate():
    roster = [{'name': 'Vukosav Kobiljski'}, {'name': 'Žarko Kobiljski'}]
    assert resolve_label('V. Kobiljski', roster)['full_name'] == 'Vukosav Kobiljski'
    assert resolve_label('Ž. Kobiljski', roster)['full_name'] == 'Žarko Kobiljski'


def test_misspelling_is_not_automatic_alias():
    result = resolve_label('Dabižjević', [{'name': 'Slavoljub Dabižljević'}])
    assert result['full_name'] is None


def test_secondary_update_time_is_not_publication_time():
    raw = b'<article><time datetime="2015-08-14T00:00:00Z"></time><time datetime="2026-01-01T00:00:00Z"></time><div class="entry-content">body</div></article>'
    assert article(raw)[2].isoformat() == '2015-08-14'


def test_missing_or_ambiguous_article_refused():
    with pytest.raises(ValueError):
        article(b'<article></article><article></article>')
    with pytest.raises(ValueError):
        article(b'<article><div class="entry-content">body</div></article>')
