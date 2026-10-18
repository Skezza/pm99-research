import pytest
from scripts import capture_explicit_reserve_histories_v1 as capture


def fixture():
    claim = {'source_player_id': 42, 'name': 'Real Player', 'birth_date': '1990-01-02'}
    return claim, {('realplayer', '1990-01-02'): {42: claim}}


def test_exact_reserve_identity_uses_original_numeric_namespace():
    claim, people = fixture()
    assert capture.confirm_claims([claim], people) == [42]


@pytest.mark.parametrize('problem', ['wrong-id', 'wrong-dob', 'initial', 'ambiguous',
                                     'duplicate', 'soccerbase-id', 'boolean'])
def test_unconfirmed_claims_cannot_trigger_requests(problem):
    claim, people = fixture()
    claims = [dict(claim)]
    if problem == 'wrong-id': claims[0]['source_player_id'] = 43
    if problem == 'wrong-dob': claims[0]['birth_date'] = '1990-01-03'
    if problem == 'initial': claims[0]['name'] = 'R. Player'
    if problem == 'ambiguous': people[('realplayer', '1990-01-02')][43] = dict(claim, source_player_id=43)
    if problem == 'duplicate': claims.append(dict(claim))
    if problem == 'soccerbase-id': claims[0]['source_player_id'] = 'soccerbase:42'
    if problem == 'boolean': claims[0]['source_player_id'] = True
    with pytest.raises(ValueError): capture.confirm_claims(claims, people)
