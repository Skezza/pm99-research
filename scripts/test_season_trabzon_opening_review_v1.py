import copy

import pytest

from scripts import season_trabzon_opening_review_v1 as review


def identity():
    annual = [{'name': 'Erhan Namlı', 'position': 'M', 'birth_date': None}]
    players = [dict(carrier_id=id, id=f'player-{id}', name='Erhan Namli',
                    source_name='Erhan Namlı', facts={'primary_position': 'M'})
               for id in (8052, 32505)]
    native = {8052: {'birth_date': '1974-05-07', 'position': 'M'},
              32505: {'birth_date': '1977-09-17', 'position': 'M'}}
    return annual, players, native


def test_same_name_different_birthdays_require_positive_person_source():
    annual, players, native = identity()
    with pytest.raises(ValueError, match='ambiguous native carrier'):
        review.join_person('7213', 'erhan-namli', annual, players, native)
    joined = review.join_person('7213', 'erhan-namli', annual, players, native,
                                dated_person={'birth_date': '1974-05-07', 'registered_name': 'ERHAN NAMLI'})
    assert joined['carrier_id'] == 8052
    assert joined['birthday_independently_verified'] is True


@pytest.mark.parametrize('problem', ['wrong-birthday', 'two-matching-birthdays',
                                   'duplicate-annual', 'wrong-native-position', 'wrong-recipe-position', 'wrong-person'])
def test_identity_ambiguity_or_drift_refuses(problem):
    annual, players, native = identity()
    person = {'birth_date': '1974-05-07', 'registered_name': 'ERHAN NAMLI'}
    if problem == 'wrong-person': person['registered_name'] = 'ANOTHER PERSON'
    if problem == 'wrong-birthday': person['birth_date'] = '1980-01-01'
    if problem == 'two-matching-birthdays': native[32505]['birth_date'] = person['birth_date']
    if problem == 'duplicate-annual': annual.append(copy.deepcopy(annual[0]))
    if problem == 'wrong-native-position': native[8052]['position'] = 'G'
    if problem == 'wrong-recipe-position': players[0]['facts']['primary_position'] = 'G'
    with pytest.raises(ValueError):
        review.join_person('7213', 'erhan-namli', annual, players, native, dated_person=person)


def test_full_original_slug_not_surname_expansion_or_generated_capture():
    raw = b'<a href="/erhan-namli/profil/spieler/7213">Namli</a>'
    assert review.original_person_links(raw, {'7213': 'Namli'}) == {'7213': 'erhan-namli'}


@pytest.mark.parametrize('raw', [
    b'<a href="/erhan-namli/profil/spieler/72130">Namli</a>',
    b'<a href="https://other.org/erhan-namli/profil/spieler/7213">Namli</a>',
    b'<a href="/erhan-namli/profil/spieler/7213">Namli</a><a href="/another-person/profil/spieler/7213">Other</a>',
    b'<a href="/erhan-namli/profil/spieler/7213/extra">Namli</a>',
])
def test_original_person_url_identity_and_ambiguity_are_checked(raw):
    with pytest.raises(ValueError):
        review.original_person_links(raw, {'7213': 'Namli'})


def test_unsourced_birthday_is_not_falsely_approved_by_full_name_match():
    annual, players, native = identity()
    result = review.join_person('7213', 'erhan-namli', annual, players[:1], native)
    assert result['birthday_independently_verified'] is False


def test_turkish_dotless_i_slug_bridge_is_explicit():
    assert review.key('Orhan Çıkırıkçı') == review.key('orhan-cikirikci')
