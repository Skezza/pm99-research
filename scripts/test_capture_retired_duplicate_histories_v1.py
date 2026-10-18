from scripts import capture_retired_duplicate_histories_v1 as capture


def test_only_new_exact_name_and_dob_identities_are_queried():
    known = {'source_player_id': 10, 'birth_date': '1960-01-02'}
    retired = {'source_player_id': 20, 'birth_date': '1960-02-03'}
    index = {('retiredplayer', '1960-02-03'): {20: retired},
             ('knownplayer', '1960-01-02'): {10: known}}
    rows = [
        {'identity': {'source_name': 'Known Player', 'birth_date': '1960-01-02', 'source_person': known}},
        {'identity': {'source_name': 'Known Player', 'birth_date': '1960-01-02', 'source_person': None}},
        {'identity': {'source_name': 'Retired Player', 'birth_date': '1960-02-03', 'source_person': None}},
        {'identity': {'source_name': 'Retired Player', 'birth_date': '1970-02-03', 'source_person': None}},
        {'identity': {'source_name': 'R. Player', 'birth_date': '1960-02-03', 'source_person': None}},
    ]
    claims = capture.requests_from_plans([{'season': '2000-01', 'unresolved': rows}], index)
    assert set(claims) == {20} and len(claims[20]) == 1


def test_homonym_and_missing_birth_date_do_not_create_queries():
    index = {('retiredplayer', '1960-02-03'): {20: {}, 21: {}}}
    rows = [{'identity': {'source_name': 'Retired Player', 'birth_date': dob, 'source_person': None}}
            for dob in ('1960-02-03', None, {'policy': 'preserve-existing-mode1'})]
    assert capture.requests_from_plans([{'season': '2000-01', 'unresolved': rows}], index) == {}


def test_existing_identity_in_any_input_plan_excludes_a_racing_request():
    person = {'source_player_id': 20, 'birth_date': '1960-02-03'}
    index = {('retiredplayer', '1960-02-03'): {20: person}}
    unknown = {'season': '2000-01', 'unresolved': [{'identity': {
        'source_name': 'Retired Player', 'birth_date': '1960-02-03', 'source_person': None}}]}
    known = {'season': '2005-06', 'unresolved': [{'identity': {'source_person': person}}]}
    assert capture.requests_from_plans([unknown, known], index) == {}
