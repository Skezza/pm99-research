import copy
from pathlib import Path
import pytest
from scripts import season_external_soccerbase_birthday_v2 as birthdays
from scripts import season_original_secondary_bench_role_v1 as bench


def excerpt():
    return dict(literal_excerpt='John Norman\nDate of birth | 26 June 1971\nMorecambe | 01 Mar 2000 | 30 Jun 2002',
        structured_facts=dict(name='John Norman', birth_date='1971-06-26', club='Morecambe',
                              from_date='2000-03-01', to_date='2002-06-30'))


def test_literal_publisher_excerpt_is_parsed_not_trusted_as_structured_json():
    document = excerpt(); before = copy.deepcopy(document)
    assert birthdays.birthday(document, 'https://www.11v11.com/players/john-norman-9941/',
                              'John Norman', 'F', 'Morecambe', '2000-08-19') == '1971-06-26'
    assert document == before


@pytest.mark.parametrize('problem', ['wrong-person', 'structured-date', 'wrong-club', 'future-spell', 'other-publisher'])
def test_excerpt_cannot_supply_another_person_or_undated_membership(problem):
    document = excerpt(); url = 'https://www.11v11.com/players/john-norman-9941/'
    if problem == 'wrong-person': document['literal_excerpt'] = document['literal_excerpt'].replace('John Norman', 'John Smith')
    if problem == 'structured-date': document['structured_facts']['birth_date'] = '1971-06-25'
    if problem == 'wrong-club': document['literal_excerpt'] = document['literal_excerpt'].replace('Morecambe', 'Woking')
    if problem == 'future-spell': document['literal_excerpt'] = document['literal_excerpt'].replace('01 Mar 2000', '01 Mar 2001')
    if problem == 'other-publisher': url = 'https://example.invalid/players/john-norman-9941/'
    with pytest.raises(ValueError): birthdays.birthday(document, url, 'John Norman', 'F', 'Morecambe', '2000-08-19')


@pytest.mark.parametrize('problem', ['known-date', 'other-person', 'fake-TM-id', 'unapproved-policy'])
def test_secondary_date_route_cannot_overwrite_known_biographies(problem):
    bio = dict(name='Original Person', birth_date=None, source_player_id='soccerbase:42')
    review = dict(name=bio['name'], published_birth_date=None, source_provider_person_id=bio['source_player_id'],
        canonical_source_player_id=bio['source_player_id'], secondary_birthday_policy=birthdays.POLICY)
    if problem == 'known-date': bio['birth_date'] = '1971-06-26'
    if problem == 'other-person': review['name'] = 'Another Person'
    if problem == 'fake-TM-id': review['canonical_source_player_id'] = 42
    if problem == 'unapproved-policy': review['secondary_birthday_policy'] = 'guess'
    with pytest.raises(ValueError, match='cannot override'):
        birthdays.resolve(review, bio, {})


def official_role(name='Chris Price', birthday='24th Oct 1975', role='Midfielder'):
    return ('<html><head><title>Stalybridge Celtic - Official Site - Player Profile ' + name +
        '</title></head><body>Career Position ' + role + ' Born ' + birthday + '</body></html>').encode()


def test_official_bench_biography_role_requires_full_name_and_exact_dob():
    assert bench.parse(official_role(), 'https://www.stalybridgeceltic.co.uk/play.php?code=PRICC',
                       'Chris Price', '1975-10-24') == 'M'


@pytest.mark.parametrize('problem', ['other-person', 'other-date', 'role-missing', 'other-site'])
def test_bench_biography_never_guesses_from_a_name_or_nearby_date(problem):
    raw = official_role(); url = 'https://www.stalybridgeceltic.co.uk/play.php?code=PRICC'
    if problem == 'other-person': raw = official_role(name='Another Price')
    if problem == 'other-date': raw = official_role(birthday='25th Oct 1975')
    if problem == 'role-missing': raw = official_role(role='Unknown')
    if problem == 'other-site': url = 'https://example.invalid/play.php?code=PRICC'
    with pytest.raises(ValueError): bench.parse(raw, url, 'Chris Price', '1975-10-24')


def test_all_four_real_secondary_biographies_rederive_from_retained_originals():
    root = birthdays.registry.ROOT / '.local/consolidated-audit-20261009/morecambe2000-source-closure-20261017'
    if not (root / 'secondary-birthdays-source-admission.json').exists(): pytest.skip('local original sources unavailable')
    document = birthdays.pipeline.read_json_file(root / 'secondary-birthdays-source-admission.json')
    actual = birthdays.pipeline.read_json_file(root / 'original-opening-equivalence.json')['actual']
    people = {r['soccerbase_person']['source_player_id']: r['soccerbase_person']
              for group in actual['identity_bridges'].values() for r in group}
    assert len(document['reviews']) == 4
    for review in document['reviews']:
        result = birthdays.resolve(review, people[review['source_provider_person_id']], actual)
        assert result['birth_date'] == review['canonical_birth_date']
        assert result['birthday_confidence'] == 'single-original-secondary-publication-not-consensus'


@pytest.mark.parametrize('problem', ['starter', 'published-role', 'duplicate-bench', 'another-person', 'another-date'])
def test_secondary_role_cannot_override_original_deployment_or_identity(problem):
    bio = dict(source_player_id='soccerbase:123', name='Chris Price', birth_date='1975-10-24')
    review = dict(policy=bench.POLICY, source_provider_person_id=bio['source_player_id'],
                  name=bio['name'], birth_date=bio['birth_date'], primary_position='M')
    row = dict(source_player_id=bio['source_player_id'], position=None)
    actual = dict(original_match=dict(starting_xi=[], published_bench=[row]))
    if problem == 'starter': actual['original_match']['starting_xi'] = [row]
    if problem == 'published-role': row['position'] = 'D'
    if problem == 'duplicate-bench': actual['original_match']['published_bench'].append(copy.deepcopy(row))
    if problem == 'another-person': review['name'] = 'Other Price'
    if problem == 'another-date': review['birth_date'] = '1975-10-25'
    with pytest.raises(ValueError): bench.resolve(review, bio, actual)


def test_explicit_bench_role_review_cannot_be_silently_ignored():
    from scripts import test_prepare_duplicate_club_disposition_v1 as fixtures
    actual, annual = fixtures.fixture()
    original = actual['identity_bridges']['published_bench'][0]['soccerbase_person']
    with pytest.raises(ValueError, match='unused or tries to override'):
        fixtures.plan.matchday_people(actual, annual,
            role_resolutions={original['source_player_id']: dict(policy=bench.POLICY)})
