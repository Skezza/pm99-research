from scripts.reconcile_foreign_portrait_biographies_v1 import verdict
from scripts.reconcile_foreign_portrait_biographies_v1 import official_edition_verdict


def fixture():
    page = {'page_id': 1, 'birth_date': '1993-03-22', 'name_keys': [],
            'title': 'Róber Ibáñez', 'source_url': 'https://en.wikipedia.org/w/index.php?oldid=1'}
    index = {'rober ibanez': [page], 'roberto ibanez castro': [page]}
    row = {'name': 'Róber Ibáñez', 'dated_source_name': 'Roberto Ibáñez Castro',
           'recipe_birth_date': '1993-03-22', 'source_birth_date': '1993-03-22',
           'issues': ['source-name-needs-independent-review']}
    return row, index


def test_explicit_alias_and_matching_dates_can_clear_name_warning():
    row, index = fixture()
    assert verdict(row, index)['cleared_issues'] == ['source-name-needs-independent-review']


def test_conflicting_date_is_never_auto_cleared():
    row, index = fixture()
    row['recipe_birth_date'] = '1990-01-01'
    assert verdict(row, index)['cleared_issues'] == []


def test_mononym_is_not_an_independent_identity():
    row, index = fixture()
    row['name'] = 'Lucas'
    assert verdict(row, index)['cleared_issues'] == []


def test_different_people_cannot_be_joined_by_matching_dates():
    row, index = fixture()
    index['roberto ibanez castro'] = [{'page_id': 2, 'birth_date': '1993-03-22'}]
    assert verdict(row, index)['cleared_issues'] == []


def test_biography_match_cannot_clear_missing_bitmap_evidence():
    row, index = fixture()
    row['issues'].append('no-original-materialisation-matching-name-and-installed-bitmap')
    assert verdict(row, index)['cleared_issues'] == ['source-name-needs-independent-review']


def test_reference_supporting_recipe_can_document_wrong_csv_date():
    row, index = fixture()
    row['source_birth_date'] = '1990-01-01'
    row['issues'].append('recipe-and-source-birth-date-disagree-or-missing')
    result = verdict(row, index)
    assert result['result'] == 'identity-corroborated-upstream-csv-date-conflict'
    assert result['upstream_conflicting_birth_date'] == '1990-01-01'
    assert 'recipe-and-source-birth-date-disagree-or-missing' in result['cleared_issues']


def test_official_alias_requires_corroborating_birthday():
    row = {'name': 'Lucas', 'fifa_id': 200949, 'source_hash_matches': True, 'face_count': 1,
           'recipe_birth_date': '1988-09-10', 'source_birth_date': '1992-08-13',
           'issues': ['source-name-needs-independent-review']}
    ea = {200949: {'f': 'Lucas', 'l': 'Rodrigues M. Silva', 'c': 'Lucas'}}
    assert not official_edition_verdict(row, ea, {})['cleared_issues']


def test_official_label_can_resolve_real_mononym_without_guessing():
    row = {'name': 'Lucas Pérez', 'fifa_id': 199354, 'source_hash_matches': True, 'face_count': 1,
           'recipe_birth_date': '1988-09-10', 'source_birth_date': '1988-09-10',
           'issues': ['source-name-needs-independent-review']}
    ea = {199354: {'f': 'Lucas', 'l': 'Pérez Martínez', 'c': 'Lucas Pérez'}}
    assert official_edition_verdict(row, ea, {})['cleared_issues'] == row['issues']


def test_official_edition_membership_needs_dates_and_source_bytes():
    row = {'name': 'Lucas Pérez', 'fifa_id': 199354, 'source_hash_matches': False, 'face_count': 1,
           'recipe_birth_date': '1988-09-10', 'source_birth_date': '1988-09-10',
           'issues': ['player-id-not-in-dated-edition']}
    ea = {199354: {'f': 'Lucas', 'l': 'Pérez Martínez', 'c': 'Lucas Pérez'}}
    assert not official_edition_verdict(row, ea, {})['cleared_issues']
