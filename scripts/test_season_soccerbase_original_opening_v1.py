import copy
import pytest
from scripts import season_soccerbase_original_opening_v1 as reader


SCHEDULE_URL = 'https://www.soccerbase.com/teams/team.sd?season_id=154&team_id=364&teamTabs=results'
MATCH_URL = 'https://www.soccerbase.com/matches/additional_information.sd?id_game=833593'


def test_missing_birthday_is_explicitly_returned_not_fabricated_or_cached_as_strict():
    player={'provider_player_id':40039,'source_player_id':'soccerbase:40039'}
    url='https://www.soccerbase.com/players/player.sd?player_id=40039'
    raw='<h1>Sean Bowles</h1><table><tr><th>Age</th><td>Unknown</td></tr></table>'
    with pytest.raises(ValueError,match='full-name/DOB'):
        reader.profile(raw,player,url)
    result=reader.profile(raw,player,url,allow_missing_birth_date=True)
    assert result['name']=='Sean Bowles' and result['birth_date'] is None
    with pytest.raises(ValueError,match='full-name/DOB'):
        reader.profile(raw,player,url)
    with pytest.raises(ValueError,match='full-name/DOB'):
        reader.profile(raw.replace('Sean Bowles','S Bowles'),player,url,allow_missing_birth_date=True)
    for published in ('<th>Born</th><td>12/03/1987</td>',
                      '<th>Age</th><td>40 (Born not parsed)</td>'):
        with pytest.raises(ValueError,match='full-name/DOB'):
            reader.profile('<h1>Sean Bowles</h1><table><tr>'+published+'</tr></table>',
                           player,url,allow_missing_birth_date=True)


def schedule():
    return '''<h1>Boreham W Results</h1><select id="seasonSelect">
      <option selected value="0">Choose another season</option>
      <option value="154">2021/2022</option></select>
      <table><tr class="match" id="tgc833593">
      <td class="tournament"><a>National League</a></td>
      <td class="dateTime"><span class="hide">2021-08-21 15:00</span></td>
      <td class="homeTeam"><a href="/teams/team.sd?team_id=2779&amp;season_id=154">Weymouth</a></td>
      <td class="awayTeam"><a href="/teams/team.sd?team_id=364&amp;season_id=154">Boreham W</a></td>
      <td class="score"><a class="vs"><em>0</em><em>2</em></a></td></tr></table>'''


def fixture():
    return reader.first_fixture(schedule(), 364, '2021-22', 'National League', 'Boreham W', SCHEDULE_URL)


def lineup():
    def row(number, mirror=False):
        cells = [f'<td><a href="/players/player.sd?player_id={number}">N Player</a></td>',
                 '<td>(G)</td>', '<td>1</td>', '<td></td>']
        return '<tr>' + ''.join(reversed(cells) if mirror else cells) + '</tr>'
    def side(name, start, mirror):
        return (f'<div class="{name}"><table><tbody class="firstTeam">'
                + ''.join(row(i, mirror) for i in range(start, start+11))
                + '</tbody><tbody>' + row(start+11, mirror) + '</tbody></table></div>')
    return ('''<div class="gameInfo"><p class="score">
        <span class="teamA">Weymouth<em>0</em></span>
        <span class="teamB">Boreham W<em>2</em></span></p>
        <span class="bageTeamA"><img src="/teambadges/2779.png"></span>
        <span class="bageTeamB"><img src="/teambadges/364.png"></span></div>
        <div class="lineup">''' + side('teamA', 100, False) + side('teamB', 200, True) + '</div>')


def test_namespaced_mirrored_xi_schedule_date_not_fragment_date():
    result = reader.match(lineup(), fixture(), 364, MATCH_URL)
    assert result['starting_xi'][0]['source_player_id'] == 'soccerbase:200'
    assert len(result['starting_xi']) == 11
    assert len(result['published_bench']) == 1
    assert result['fixture_date_published_on_original_schedule']
    assert not result['match_page_date_independently_published']
    assert not result['approved_for_native_ownership_repair']


@pytest.mark.parametrize('problem', ['season-offset', 'wrong-year', 'wrong-heading', 'missing-score',
    'wrong-side-season', 'duplicate-fixture', 'outside-year', 'substring-team'])
def test_reject_schedule_conflicts(problem):
    raw = schedule(); url = SCHEDULE_URL
    if problem == 'season-offset': url = url.replace('154', '151')
    if problem == 'wrong-year': raw = raw.replace('2021/2022', '2020/2021')
    if problem == 'wrong-heading': raw = raw.replace('Boreham W Results', 'Other Results')
    if problem == 'missing-score': raw = raw.replace('<em>2</em>', '')
    if problem == 'wrong-side-season': raw = raw.replace('season_id=154', 'season_id=151')
    if problem == 'duplicate-fixture': raw += raw[raw.index('<table>'):]
    if problem == 'outside-year': raw = raw.replace('2021-08-21', '2020-08-21')
    if problem == 'substring-team': raw = raw.replace('team_id=364', 'team_id=3648')
    with pytest.raises(ValueError):
        reader.first_fixture(raw, 364, '2021-22', 'National League', 'Boreham W', url)


@pytest.mark.parametrize('problem', ['badge', 'score', 'name', 'game-url', 'no-explicit-xi',
    'repeated-player', 'short-xi', 'multiple-roles', 'absent-club'])
def test_reject_match_conflicts(problem):
    raw = lineup(); url = MATCH_URL; team = 364
    if problem == 'badge': raw = raw.replace('/364.png', '/3648.png')
    if problem == 'score': raw = raw.replace('Boreham W<em>2', 'Boreham W<em>3')
    if problem == 'name': raw = raw.replace('Boreham W<em>', 'Other<em>')
    if problem == 'game-url': url += '0'
    if problem == 'no-explicit-xi': raw = raw.replace('class="firstTeam"', '')
    if problem == 'repeated-player': raw = raw.replace('player_id=211', 'player_id=200')
    if problem == 'short-xi': raw = raw.replace('player_id=210', 'person=210')
    if problem == 'multiple-roles': raw = raw.replace('<td>1</td>', '<td>(D)</td>')
    if problem == 'absent-club': team = 3648
    with pytest.raises(ValueError): reader.match(raw, fixture(), team, url)


def test_declared_missing_opponent_badge_preserves_exact_game_names_and_score():
    raw=lineup().replace('/2779.png','/default.png')
    with pytest.raises(ValueError): reader.match(raw,fixture(),364,MATCH_URL)
    result=reader.match(raw,fixture(),364,MATCH_URL,True)
    assert result['numeric_club_badges_published']==1
    assert not result['approved_for_native_ownership_repair']
    with pytest.raises(ValueError):
        reader.match(raw.replace('/364.png','/default.png'),fixture(),364,MATCH_URL,True)
    with pytest.raises(ValueError):
        reader.match(raw.replace('Weymouth<em>','Other<em>'),fixture(),364,MATCH_URL,True)


def test_explicit_unknown_position_keeps_identity_without_inventing_role():
    raw=lineup().replace('<td>(G)</td>','<td>(-)</td>')
    with pytest.raises(ValueError):reader.match(raw,fixture(),364,MATCH_URL)
    result=reader.match(raw,fixture(),364,MATCH_URL,True)
    assert all(p['position'] is None for p in result['starting_xi']+result['published_bench'])
    assert len(result['unknown_dated_positions'])==12
    with pytest.raises(ValueError):
        reader.match(raw.replace('<td>(-)</td>','<td>(GK)</td>'),fixture(),364,MATCH_URL,True)


def person():
    return {'provider_player_id': 50514, 'source_player_id': 'soccerbase:50514'}


@pytest.mark.parametrize('row', [
    '<tr><th>Age</th><td><strong>36</strong> (Born 22 Feb, 1990) </td></tr>',
    '<tr><td>Born</td><td>22 Feb, 1990</td></tr>',
])
def test_read_explicit_original_dob_without_current_age_inference(row):
    result = reader.profile('<h1>1. Nathan Ashmore</h1><table>'+row+'</table>', person(),
        'https://www.soccerbase.com/players/player.sd?player_id=50514')
    assert result['name'] == 'Nathan Ashmore' and result['birth_date'] == '1990-02-22'
    assert not result['ownership_established_by_biography']


@pytest.mark.parametrize('problem', ['initial', 'no-dob', 'wrong-url', 'namespace', 'duplicate-dob'])
def test_reject_biography_identity_conflicts(problem):
    row = '<tr><th>Age</th><td>36 (Born 22 Feb, 1990)</td></tr>'
    raw = '<h1>Nathan Ashmore</h1><table>'+row+'</table>'
    p = person(); url = 'https://www.soccerbase.com/players/player.sd?player_id=50514'
    if problem == 'initial': raw = raw.replace('Nathan Ashmore', 'N Ashmore')
    if problem == 'no-dob': raw = raw.replace(' (Born 22 Feb, 1990)', '')
    if problem == 'wrong-url': url += '0'
    if problem == 'namespace': p['source_player_id'] = 'transfermarkt:50514'
    if problem == 'duplicate-dob': raw += '<table>'+row+'</table>'
    with pytest.raises(ValueError): reader.profile(raw, p, url)


def test_successful_biography_cache_does_not_hide_byte_changes_or_return_mutable_shared_fact():
    raw='<h1>Nathan Ashmore</h1><table><tr><th>Age</th><td>36 (Born 22 Feb, 1990)</td></tr></table>'
    url='https://www.soccerbase.com/players/player.sd?player_id=50514'
    result=reader.profile(raw,person(),url);result['name']='Tampered'
    assert reader.profile(raw,person(),url)['name']=='Nathan Ashmore'
    assert reader.profile(raw.replace('22 Feb','23 Feb'),person(),url)['birth_date']=='1990-02-23'
    with pytest.raises(ValueError):reader.profile(raw,person(),url+'0')


def test_later_explicit_unscored_row_cannot_hide_or_replace_the_earliest_fixture():
    first=schedule()
    later=first[first.index('<table>'):].replace('tgc833593','tgc833594').replace('2021-08-21','2021-10-12')
    later=later.replace('<a class="vs"><em>0</em><em>2</em></a>','<span class="vs">v</span>')
    raw=first+later
    with pytest.raises(ValueError):reader.first_fixture(raw,364,'2021-22','National League','Boreham W',SCHEDULE_URL)
    assert reader.first_fixture(raw,364,'2021-22','National League','Boreham W',SCHEDULE_URL,
        allow_later_unscored=True)==fixture()
    with pytest.raises(ValueError):reader.first_fixture(first+later.replace('2021-10-12','2021-08-20'),364,
        '2021-22','National League','Boreham W',SCHEDULE_URL,allow_later_unscored=True)
    with pytest.raises(ValueError):reader.first_fixture(first+later.replace('2021-10-12','2021-08-21'),364,
        '2021-22','National League','Boreham W',SCHEDULE_URL,allow_later_unscored=True)
