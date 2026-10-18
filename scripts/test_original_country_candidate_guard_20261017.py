import pytest
from scripts import build_original_country_defaults_20261017 as subject


def test_exact_unchanged_display_and_dob_does_not_require_lossy_l_transliteration():
    subject.guard_candidate(dict(name='#4 Kacper Lopata',source_name='Kacper Łopata',
        facts=dict(birth_date='2001-08-27')),dict(name='#4 Kacper Lopata',birth_date='2001-08-27'))


@pytest.mark.parametrize('changes',[dict(name='Another Person'),dict(birth_date='2001-08-28')])
def test_changed_identity_or_dob_still_refuses(changes):
    candidate=dict(name='#4 Kacper Lopata',birth_date='2001-08-27');candidate.update(changes)
    with pytest.raises(ValueError,match='another person'):
        subject.guard_candidate(dict(name='#4 Kacper Lopata',source_name='Kacper Łopata',
            facts=dict(birth_date='2001-08-27')),candidate)


@pytest.mark.parametrize('changes',[dict(source_person_id=999),dict(birth_date='2001-08-28'),dict(source_country='ENG')])
def test_exact_display_never_overrides_independent_numeric_person_dob_country(changes):
    candidate=dict(source_person_id=633228,birth_date='2001-08-27',source_country='POL');candidate.update(changes)
    with pytest.raises(ValueError,match='numeric person/DOB/country'):
        subject.guard_source_person(dict(source_person=dict(source_player_id=633228,birth_date='2001-08-27'),
            nationality='POL'),candidate)


def test_positive_numeric_person_guard():
    subject.guard_source_person(dict(source_person=dict(source_player_id=633228,birth_date='2001-08-27'),nationality='POL'),
        dict(source_person_id=633228,birth_date='2001-08-27',source_country='POL'))
