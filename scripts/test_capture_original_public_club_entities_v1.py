import copy
import pytest
from scripts import capture_original_public_club_entities_v1 as capture


def entity():
    return {'success': True, 'data': [{'id': '11', 'name': 'Arsenal FC',
        'baseDetails': {'shortName': 'Arsenal', 'countryId': 189, 'mainClubId': '11',
            'clubTypeId': 1, 'isNationalTeam': False, 'primaryCompetitionId': 'GB1'},
        'squadDetails': {'squadSize': 1, 'players': ['Contemporary Player']},
        'manager': 'Contemporary Coach', 'kit': 'Contemporary Shirt'}]}


def test_explicit_names_and_identity_are_discovery_only():
    original = entity(); before = copy.deepcopy(original)
    rows, gaps = capture.parse(original, [11, 12])
    assert rows[0]['published_names'] == ['Arsenal FC', 'Arsenal']
    assert not rows[0]['historical_name_membership_or_ownership_approval']
    assert not {'squadDetails', 'manager', 'kit', 'primaryCompetitionId'} & rows[0].keys()
    assert gaps == [12] and original == before


@pytest.mark.parametrize('problem', ['failure', 'not-list', 'no-ID', 'unrequested', 'duplicate', 'no-name', 'no-base'])
def test_wrong_or_ambiguous_original_entities_are_refused(problem):
    doc = entity(); row = doc['data'][0]
    if problem == 'failure': doc['success'] = False
    if problem == 'not-list': doc['data'] = {}
    if problem == 'no-ID': del row['id']
    if problem == 'unrequested': row['id'] = '12'
    if problem == 'duplicate': doc['data'].append(copy.deepcopy(row))
    if problem == 'no-name': row['name'] = ''
    if problem == 'no-base': del row['baseDetails']
    with pytest.raises(ValueError): capture.parse(doc, [11])
