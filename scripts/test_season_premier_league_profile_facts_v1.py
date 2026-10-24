import copy
import json

import pytest

from scripts import season_premier_league_profile_facts_v1 as source

URL = 'https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v1/players/8'
ROW = {'id': {'playerId': '8'}, 'name': {'display': 'Example Person'},
       'dates': {'birth': '1976-04-01'}, 'country': {'country': 'Netherlands'}}


def parse(rows, **kwargs):
    return source.parse_player_json(json.dumps(rows).encode(), url=kwargs.get('url', URL),
                                    provider_player_id=8, full_name='Example Person')


def test_matching_career_rows_establish_same_person_facts():
    result = parse([ROW, copy.deepcopy(ROW)])
    assert result['birth_date'] == '1976-04-01'
    assert result['nationality'] == 'NED'


@pytest.mark.parametrize('url', [URL.replace('/8', '/9'), URL+'?id=8', URL+'#8',
    URL.replace('https:', 'http:'), URL.replace('pulselive.com', 'example.org')])
def test_original_provider_endpoint_is_required(url):
    with pytest.raises(ValueError):
        parse([ROW], url=url)


@pytest.mark.parametrize('key,value', [('id', {'playerId': 9}),
    ('name', {'display': 'E. Person'}), ('dates', {'birth': '1976-02-31'}),
    ('country', {'country': 'Narnia'}), ('country', None), ('id', [])])
def test_conflicting_or_malformed_record_cannot_be_hidden_among_career_rows(key, value):
    second = copy.deepcopy(ROW)
    second[key] = value
    with pytest.raises(ValueError):
        parse([ROW, second])


@pytest.mark.parametrize('value', [{}, [], [None], [ROW, {'id': {}}]])
def test_empty_or_incomplete_identity_is_rejected(value):
    with pytest.raises(ValueError):
        parse(value)


def test_duplicate_json_properties_cannot_mask_a_conflicting_fact():
    raw = json.dumps([ROW]).replace('"birth": "1976-04-01"',
                                    '"birth": "1976-04-02", "birth": "1976-04-01"').encode()
    with pytest.raises(ValueError, match='repeated property'):
        source.parse_player_json(raw, url=URL, provider_player_id=8, full_name='Example Person')
