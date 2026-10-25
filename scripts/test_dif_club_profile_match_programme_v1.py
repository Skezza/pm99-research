"""Portable source-admission regressions; no game or network corpus required."""
import pytest
from scripts.season_dif_club_profile_match_programme_v1 import (
    parse_dif_player_profile, parse_match_programme_player_block,
)

NAME = 'Asta Example'
URL = 'https://www.dif.se/spelare/herrar/2000-2009/asta-example'


def profile(name=NAME, birthday='7 maj. 1982'):
    return (f'<article><h1>{name}</h1><dl>Född {birthday} '
            'Nationalitet Svensk Position Målvakt Säsonger i DIF 2002</dl></article>').encode()


def programme(name=NAME, birthday='May 7th, 1982'):
    return f'{name.upper()} - Position: Goalkeeper. Date of birth:\n{birthday}. First team: Example Town.\n'


def test_named_profile_and_independent_programme_agree():
    card = parse_dif_player_profile(profile(), url=URL, fullname=NAME)
    block = parse_match_programme_player_block(programme(), NAME)
    assert card['birth_date'] == block['birth_date'] == '1982-05-07'
    assert card['nationality_literal'] == 'Svensk'
    assert card['position_literal'] == 'Målvakt'
    assert block['position_literal'] == 'Goalkeeper'


@pytest.mark.parametrize('url', [URL.replace('www.dif.se', 'unrelated.example'), URL.replace('asta-example', 'other-person')])
def test_profile_refuses_unrelated_publisher_or_subject(url):
    with pytest.raises(ValueError):
        parse_dif_player_profile(profile(), url=url, fullname=NAME)


def test_profile_refuses_duplicate_subject_cards():
    with pytest.raises(ValueError, match='heading'):
        parse_dif_player_profile(profile()+profile(), url=URL, fullname=NAME)


def test_profile_refuses_invalid_calendar_date():
    with pytest.raises(ValueError, match='calendar'):
        parse_dif_player_profile(profile(birthday='32 maj. 1982'), url=URL, fullname=NAME)


def test_programme_refuses_duplicate_or_missing_person():
    for text in [programme()+programme(), programme(name='Other Person')]:
        with pytest.raises(ValueError, match='unique'):
            parse_match_programme_player_block(text, NAME)


def test_programme_does_not_take_an_adjacent_column_birthday():
    text = f'{NAME.upper()} - Position: Goalkeeper. Date of birth:\n'
    text += ' '*80+'OTHER PERSON - Position: Defender. Date of birth:\n'
    text += ' '*80+'January 1st, 1990.\n'
    with pytest.raises(ValueError, match='DOB'):
        parse_match_programme_player_block(text, NAME)


def test_programme_refuses_invalid_calendar_date():
    with pytest.raises(ValueError, match='calendar'):
        parse_match_programme_player_block(programme(birthday='May 32nd, 1982'), NAME)
