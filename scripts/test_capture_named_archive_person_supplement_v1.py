import pytest
from scripts import capture_named_archive_person_supplement_v1 as capture


def test_two_original_publishers_agree_on_exact_name_variant_and_confirmed_date():
    person = {'birth_date': '1978-01-30', 'published_name_variants': ['Matt Hocking', 'M. Hocking']}
    bio = {'name': 'Matt Hocking', 'birth_date': '1978-01-30'}
    capture.validate_person(person, bio)


@pytest.mark.parametrize('problem', ['DOB', 'name', 'invented-nickname'])
def test_no_conflicting_date_or_unpublished_name_expansion(problem):
    person = {'birth_date': '1978-01-30', 'published_name_variants': ['Matt Hocking']}
    bio = {'name': 'Matt Hocking', 'birth_date': '1978-01-30'}
    if problem == 'DOB': person['birth_date'] = '1978-01-31'
    if problem == 'name': bio['name'] = 'Mike Hocking'
    if problem == 'invented-nickname': person['published_name_variants'] = ['Matthew Hocking']
    with pytest.raises(ValueError): capture.validate_person(person, bio)
