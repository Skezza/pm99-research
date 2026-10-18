import copy
import pytest
from scripts import season_english_result_date_binding_v1 as binding
from scripts.test_season_football_data_opening_dates_v1 import rows, encoded


def inputs():
    values = rows()
    for row in values:
        for k in ('HomeTeam', 'AwayTeam'):
            if row[k] == 'Team 00': row[k] = 'Boston'
    capture = {'country_catalog': 'eng', 'competition_catalog': 'd3', 'club_name': 'Boston United'}
    entities = {3489: {'source_club_id': 3489, 'country_id': 189, 'club_type_id': 1,
        'main_club_id': '3489', 'is_national_team': False,
        'published_names': ['Boston United', 'Boston Utd']}}
    return capture, entities, encoded(values), '2003-04'


def test_explicit_club_identity_and_original_dates_never_approve_players():
    result = binding.bind(*inputs())
    assert result['source_club_id'] == 3489
    assert result['original_date_evidence']['fixture']['date'] == '2003-08-09'
    assert result['starting_xi'] is None and result['substitutes'] is None
    assert result['manager'] is None and not result['player_ownership_approved']


@pytest.mark.parametrize('problem', ['womens', 'other-country', 'unmatched-name', 'reserve-team',
    'national-team', 'different-main-club', 'ambiguous-lifecycle', 'incomplete-results'])
def test_unrelated_or_ambiguous_sources_never_become_opening_claims(problem):
    args = list(inputs()); c, es, raw, season = args; e = es[3489]
    if problem == 'womens': c['competition_catalog'] = 'wsl'
    if problem == 'other-country': c['country_catalog'] = 'scotland'
    if problem == 'unmatched-name': e['published_names'] = ['Boston Womens FC']
    if problem == 'reserve-team': e['club_type_id'] = 5
    if problem == 'national-team': e['is_national_team'] = True
    if problem == 'different-main-club': e['main_club_id'] = '11'
    if problem == 'ambiguous-lifecycle': es[9000] = dict(e, source_club_id=9000, main_club_id='9000')
    if problem == 'incomplete-results': args[2] = raw[:raw.rfind(b'\n', 0, len(raw)-1)+1]
    with pytest.raises(ValueError): binding.bind(*args)
