import json
import pytest
from scripts import season_published_person_identity_v1 as identity


def fixture():
    return {'success': True, 'data': [{'id': '10', 'name': 'Retired Player', 'shortName': 'R. Player',
        'lifeDates': {'dateOfBirth': '1960-01-02', 'isDateOfBirthUnknown': False},
        'relativeUrl': '/retired-player/profil/spieler/10', 'clubAssignments': [{'clubId': '999'}],
        'attributes': {'positionGroup': 'GOALKEEPER'}, 'nationalityDetails': {'nationalityId': 999},
        'portraitUrl': 'https://example.com/retired-at-age-66.jpg'}]}


def test_only_confirmed_stable_names_and_dob_are_used():
    people, gaps = identity.parse(fixture(), [10])
    assert not gaps and people[0]['birth_date'] == '1960-01-02'
    assert people[0]['published_name_variants'] == ['R. Player', 'Retired Player']
    assert not set(people[0]) & {'clubAssignments', 'attributes', 'nationalityDetails', 'portraitUrl'}


@pytest.mark.parametrize('problem', ['unknown-DOB', 'missing-DOB', 'wrong-ID', 'wrong-profile', 'duplicate-ID'])
def test_unconfirmed_dates_and_wrong_ids_never_enter_person_index(problem):
    d = fixture()
    if problem == 'unknown-DOB': d['data'][0]['lifeDates']['isDateOfBirthUnknown'] = True
    if problem == 'missing-DOB': d['data'][0]['lifeDates']['dateOfBirth'] = None
    if problem == 'wrong-ID': d['data'][0]['id'] = '99'
    if problem == 'wrong-profile': d['data'][0]['relativeUrl'] = '/other/profil/spieler/99'
    if problem == 'duplicate-ID': d['data'].append(d['data'][0])
    if problem in ('unknown-DOB', 'missing-DOB'):
        people, gaps = identity.parse(d, [10]); assert not people and gaps
    else:
        with pytest.raises(ValueError): identity.parse(d, [10])


def test_unpublished_requested_person_stays_an_explicit_gap():
    _, gaps = identity.parse(fixture(), [10, 11])
    assert gaps == [{'player_id': 11, 'reason': 'original-player-entity-unpublished'}]


def test_incremental_capture_replays_existing_response_without_network(tmp_path, monkeypatch):
    from scripts.test_original_public_supplement_merges_v1 import people_document
    monkeypatch.setattr(identity, 'ROOT', tmp_path)
    monkeypatch.setattr(identity.registry, 'ROOT', tmp_path)
    prior = tmp_path / 'prior.json'
    prior.write_text(json.dumps(people_document(tmp_path)))
    opening = tmp_path / 'opening.json'
    opening.write_text(json.dumps({'clubs': [{'status': 'original-first-fixture-reparsed',
        'evidence': {'starting_xi': {'10': 'Retired Player'}, 'substitutes': {}}}]}))
    monkeypatch.setattr(identity.transfer, 'verify_opening_sources', lambda doc: None)
    monkeypatch.setattr(identity, 'urlopen', lambda *args, **kwargs: pytest.fail('existing person refetched'))
    target = tmp_path / 'combined.json'
    identity.capture([opening], tmp_path / 'cache', target, prior)
    saved = json.loads(target.read_text())
    assert len(saved['batches']) == 1
    assert saved['reused_original_person_ledger']['raw_responses_independently_replayed'] is True
    assert identity.merge({}, saved)[1]['accepted_player_ids'] == [10]


def test_incremental_capture_refuses_forged_retained_identity(tmp_path, monkeypatch):
    from scripts.test_original_public_supplement_merges_v1 import people_document
    monkeypatch.setattr(identity, 'ROOT', tmp_path)
    monkeypatch.setattr(identity.registry, 'ROOT', tmp_path)
    document = people_document(tmp_path)
    document['batches'][0]['people'][0]['birth_date'] = '1970-01-01'
    prior = tmp_path / 'prior.json'
    prior.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='do not reproduce'):
        identity.capture([], tmp_path / 'cache', tmp_path / 'combined.json', prior)
