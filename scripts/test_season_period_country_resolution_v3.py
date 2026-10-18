import pytest
from scripts import season_period_country_resolution_v3 as subject


def test_passport_alias_uses_names_only_and_exact_identity():
    person = dict(source_player_id=130756, name='Giannelli Imbula', birth_date='1992-09-12')
    raw = dict(id='130756', name='Giannelli Imbula',
        lifeDates=dict(dateOfBirth='1992-09-12', isDateOfBirthUnknown=False),
        nationalityDetails=dict(passportName='Gilbert Imbula Wanga', nationalityId='UNUSED'))
    assert subject.passport.parse_person(raw, person) == 'Gilbert Imbula Wanga'
    raw['id'] = '1'
    with pytest.raises(ValueError, match='numerical ID/full name/DOB'):
        subject.passport.parse_person(raw, person)


def test_initial_only_alias_is_not_a_full_name_identity_bridge():
    person = dict(source_player_id=1, name='John Smith', birth_date='1992-09-12')
    raw = dict(id=1, name='John Smith',
        lifeDates=dict(dateOfBirth='1992-09-12', isDateOfBirthUnknown=False),
        nationalityDetails=dict(passportName='J. Smith'))
    assert subject.passport.parse_person(raw, person) is None


@pytest.fixture(scope='module')
def original_index():
    path = subject.fifa.fifa.identity.old.FIFA
    if not path.exists():
        pytest.skip('local original FIFA corpus unavailable')
    sha = subject.fifa.registry.sha256_file(path)
    return subject.fifa.load(sha), sha


@pytest.mark.parametrize('year,carrier,expected,rule', [
    ('2016-17', 9161, 'FRA', 'exact-target-FIFA'),
    ('2021-22', 14166, 'COD', 'independent-prior-dated'),
    ('2016-17', 33239, 'CGO', 'independent-prior-dated'),
])
def test_real_original_country_conflicts_are_resolved_without_current_flags(original_index,year,carrier,expected,rule):
    path = subject.cgo.CATALOG.parent.parent / ('country-policy-v2-cohort-20261017/' + year + '/country-plan.json')
    if not path.exists():
        pytest.skip('local original country plan unavailable')
    row = next(r for r in subject.cgo.pipeline.read_json_file(path)['updates'] if r['carrier_id'] == carrier)
    index, sha = original_index
    result = subject.resolve(row, year, index=index, file_sha=sha)
    assert result['nationality'] == expected
    assert result['resolution_rule'].startswith(rule)
    assert not result['exclusive_citizenship_or_target_season_caps_claimed']
    if carrier == 9161:
        assert result['exact_FIFA_witness']['long_name'] == 'Gilbert Gianelli Imbula Wanga'
        assert result['original_passport_name_alias']['name'] == 'Gilbert Imbula Wanga'


def test_original_mandeville_spanish_proposal_is_rejected_in_favour_of_exact_fifa_england(original_index):
    path = subject.cgo.CATALOG.parent.parent / 'original-country-default-delivery-20261017-v1/2017-18/country-plan.json'
    if not path.exists():
        pytest.skip('local original country plan unavailable')
    row = next(r for r in subject.cgo.pipeline.read_json_file(path)['updates'] if r['carrier_id'] == 10683)
    index, sha = original_index
    result = subject.resolve(row, '2017-18', index=index, file_sha=sha)
    assert result['original_annual_nationality'] == 'ESP'
    assert result['nationality'] == 'ENG'
