import pytest
from scripts import capture_arsenal_coupled_primary_sources_20261016 as subject


def fixture():
    return ('Aug 21st 2021 The season starts today GENOA (3-5-2): '+
        '; '.join(f'{i} Starter' for i in range(1,12))+
        '. Subs: '+', '.join(f'{i} Bench' for i in range(12,24))+
        '. Coach: Davide Ballardini.').encode()


def test_complete_primary_side_has_exact_eleven_and_twelve_substitutes():
    result=subject.genoa(fixture())
    assert result['date']=='2021-08-21' and result['formation']=='3-5-2'
    assert len(result['starting_xi'])==11 and len(result['published_bench'])==12


def test_original_html_markup_spacing_before_colons_is_not_a_different_side():
    assert subject.genoa(fixture().replace(b':',b' :'))==subject.genoa(fixture())


def test_duplicate_number_across_starters_and_bench_is_refused():
    with pytest.raises(ValueError,match='distinct substitutes'):
        subject.genoa(fixture().replace(b'12 Bench',b'1 Bench'))


def test_numbered_names_preserve_published_surnames_not_identity_guesses():
    assert subject.numbered('57 Sirigu; 3 Vanheusden; 14 Biraschi.')==[
        dict(shirt_number=57,published_match_name='Sirigu'),dict(shirt_number=3,published_match_name='Vanheusden'),
        dict(shirt_number=14,published_match_name='Biraschi')]


def test_wrong_side_or_undated_sheet_is_refused():
    with pytest.raises(ValueError,match='published date'):
        subject.genoa(b'GENOA (3-5-2): arbitrary team')


def test_duplicate_shirt_number_is_not_two_distinct_people():
    with pytest.raises(ValueError,match='duplicate primary shirt'):
        subject.numbered('57 Sirigu; 57 Other')


def test_unlisted_urls_cannot_be_captured_as_primary_approval():
    with pytest.raises(ValueError,match='unrecognised bounded'):
        subject.validate(b'other','https://example.com')
