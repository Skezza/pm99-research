import pytest

from scripts import season_milan_opening_review_v1 as review


def sheet(names=None):
    names = names or review.SHEET_NAMES
    return ('<p>MILAN vs VICENZA 2-0</p><p>MILAN: '
            + ', '.join(names) + ' - All.: Zaccheroni</p>').encode()


def test_actual_starters_parse_without_substitutes():
    names = list(review.SHEET_NAMES)
    names[6] += " (46' Giunti)"
    assert review.archive_sheet(sheet(names)) == review.SHEET_NAMES


@pytest.mark.parametrize('raw', [
    sheet().replace(b'2-0', b'0-2'),
    sheet().replace(b'Abbiati', b'Lehmann'),
    sheet().replace(b'Zaccheroni', b'Terim'),
    sheet() + sheet(),
    sheet().replace(b'Shevchenko', b'Shevchenko, Giunti'),
])
def test_changed_or_ambiguous_sheet_fails(raw):
    with pytest.raises(ValueError):
        review.archive_sheet(raw)


def test_full_name_accent_bridge_is_exact_not_fuzzy():
    assert review.plain('LEONARDO Nascimento de Araújo') == 'leonardo nascimento de araujo'
    assert review.plain('Leonardo da Silva') != 'leonardo nascimento de araujo'
