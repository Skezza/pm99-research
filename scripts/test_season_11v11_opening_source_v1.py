import pytest
from scripts import season_11v11_opening_source_v1 as archive


def schedule():
    return b'''<h1>Team One football club match record: 2004</h1>
        <h2 class="seasonTitle">2003-04 season</h2><table>
        <tr><td>16 Aug 2003</td><td><a href="/matches/team-one-v-team-two-16-august-2003-21/">Team One v Team Two</a></td><td>W</td><td>1-0</td><td>League Division 3</td></tr>
        <tr><td>09 Aug 2003</td><td><a href="/matches/team-two-v-team-one-09-august-2003-20/">Team Two v Team One</a></td><td>D</td><td>0-0</td><td>League Division 3</td></tr></table>'''


def players(count=11):
    return ''.join(f'<div class="player"><a href="/players/actual-person-{n}/">Actual Person {n}</a></div>'
                   for n in range(1, count + 1))


def report():
    xi = '<h4>Starting lineup:</h4>' + players()
    bench = '<h4>On the bench:</h4><div class="player"><a href="/players/reserve-person-12/">Reserve Person</a></div>'
    subs = '<h4>Substitutions:</h4><table><tr><td><span class="substitute">Reserve Person</span> for <span class="substituted">Actual Person 1</span></td></tr></table>'
    comments = '<h4>Comments:</h4>Unused substitutes: Unused One and Unused Two'
    header = '<h2 class="teamname"><a href="/teams/team-one">Team One</a></h2>'
    return f'''<h1>Team Two v Team One, 09 August 2003</h1>
      <div class="basicData"><table><tr><td>Competition</td><td>League Division 3</td></tr></table></div>
      <div class="teams-new hide-mobile"><div class="headers"><div class="away">{header}</div></div>
      <div class="lineup"><div class="away">{xi}</div></div>
      <div class="lineup"><div class="away">{bench}</div></div>
      <div class="substitutions"><div class="away">{subs}</div></div>
      <div class="comments"><div class="away">{comments}</div></div></div>
      <div class="row show-mobile"><div class="headers away">{header}</div>
      <div class="lineup away">{xi}</div><div class="lineup away">{bench}</div>
      <div class="substitutions away">{subs}</div><div class="comments away">{comments}</div></div>'''.encode()


def verify(s=None, r=None):
    return archive.verify_pair(s or schedule(), r or report(), 'Team One', '2003-04', 'League Division 3', 2)


def test_full_schedule_and_two_exact_club_views_agree_without_fabricating_other_publisher_ids():
    result = verify()
    assert result['fixture']['date'] == '2003-08-09'
    assert len(result['starting_xi']) == 11
    assert result['starting_xi'][0]['source_player_id'] == '11v11:1'
    assert result['unused_substitute_names'] == ['Unused One', 'Unused Two']
    assert result['used_substitution_events'][0]['incoming_name'] == 'Reserve Person'
    assert result['manager'] is None and result['formation'] is None
    assert not result['approved_for_duplicate_ownership']


@pytest.mark.parametrize('problem', ['wrong-club', 'wrong-year', 'wrong-season', 'wrong-competition',
    'incomplete-schedule', 'duplicate-schedule', 'ambiguous-club-side', 'wrong-report-date',
    'wrong-report-team', 'wrong-report-competition', 'missing-mobile', 'missing-desktop',
    'eleven-person-bench-not-XI', 'two-XIs', 'repeated-player', 'bench-overlap',
    'mobile-mismatch', 'wrong-name-prefix', 'unknown-comments', 'ambiguous-substitution'])
def test_incomplete_wrong_or_conflicting_original_sources_are_refused(problem):
    s, r = schedule(), report()
    if problem == 'wrong-club': s = s.replace(b'Team One football', b'Team Other football')
    if problem == 'wrong-year': s = s.replace(b'record: 2004', b'record: 2005')
    if problem == 'wrong-season': s = s.replace(b'2003-04 season', b'2004-05 season')
    if problem == 'wrong-competition': s = s.replace(b'League Division 3', b'League Cup')
    if problem == 'incomplete-schedule': s = s.replace(b'16 Aug 2003', b'bad date')
    if problem == 'duplicate-schedule': s = s.replace(b'team-one-v-team-two-16-august-2003-21', b'team-two-v-team-one-09-august-2003-20')
    if problem == 'ambiguous-club-side': s = s.replace(b'Team Two v Team One</a>', b'Team One v Team One</a>')
    if problem == 'wrong-report-date': r = r.replace(b'09 August 2003', b'16 August 2003')
    if problem == 'wrong-report-team': r = r.replace(b'<h1>Team Two', b'<h1>Team Other')
    if problem == 'wrong-report-competition': r = r.replace(b'League Division 3', b'League Cup')
    if problem == 'missing-mobile': r = r.replace(b'row show-mobile', b'row other')
    if problem == 'missing-desktop': r = r.replace(b'teams-new hide-mobile', b'teams-new other')
    if problem == 'eleven-person-bench-not-XI': r = r.replace(b'Starting lineup:', b'On the bench:')
    if problem == 'two-XIs': r = r.replace(b'On the bench:', b'Starting lineup:')
    if problem == 'repeated-player': r = r.replace(b'/players/actual-person-2/', b'/players/actual-person-1/')
    if problem == 'bench-overlap': r = r.replace(b'/players/reserve-person-12/', b'/players/actual-person-1/')
    if problem == 'mobile-mismatch': r = r.replace(b'Actual Person 11', b'Another Person', 1)
    if problem == 'wrong-name-prefix': r = r.replace(b'>Team One</a>', b'>Team One Hundred</a>')
    if problem == 'unknown-comments': r = r.replace(b'Unused substitutes: Unused One and Unused Two', b'Squad revised after appeal')
    if problem == 'ambiguous-substitution': r = r.replace(b'class="substitute"', b'class="unknown"')
    with pytest.raises(ValueError): verify(s, r)


def biography():
    return b'<h1>Actual Person</h1><table><tr><td>Date of birth</td><td>19 May 1970</td></tr></table>'


def person_inputs():
    player = {'source_player_id': '11v11:123', 'name': 'Actual Person',
        'source_profile_url': 'https://www.11v11.com/players/actual-person-123/'}
    person = {'source_player_id': 999, 'name': 'Actual Person', 'birth_date': '1970-05-19'}
    return player, {('actualperson', '1970-05-19'): {999: person}}


def test_independent_birthday_bridge_preserves_both_publisher_namespaces():
    player, people = person_inputs()
    bridge = archive.bridge_person(biography(), player, people)
    assert bridge['original_archive_person']['archive_player_id'] == '11v11:123'
    assert bridge['bound_historical_person']['source_player_id'] == 999
    assert bridge['original_archive_person']['birth_date'] == '1970-05-19'


@pytest.mark.parametrize('problem', ['heading', 'initials', 'two-headings', 'two-dates',
    'missing-date', 'vague-date', 'unconfirmed-person', 'DOB-conflict', 'homonym'])
def test_biography_bridge_refuses_every_ambiguous_or_conflicting_join(problem):
    player, people = person_inputs()
    raw = biography()
    if problem == 'heading': raw = raw.replace(b'Actual Person', b'Another Person')
    if problem == 'initials': raw = raw.replace(b'Actual Person', b'A. Person')
    if problem == 'two-headings': raw += b'<h1>Actual Person</h1>'
    if problem == 'two-dates': raw += b'<table><tr><td>Date of birth</td><td>20 May 1970</td></tr></table>'
    if problem == 'missing-date': raw = raw.replace(b'Date of birth', b'Age')
    if problem == 'vague-date': raw = raw.replace(b'19 May 1970', b'1970')
    if problem == 'unconfirmed-person': people.clear()
    if problem == 'DOB-conflict': raw = raw.replace(b'19 May 1970', b'20 May 1970')
    if problem == 'homonym': people[('actualperson', '1970-05-19')][1000] = {
        'source_player_id': 1000, 'name': 'Actual Person', 'birth_date': '1970-05-19'}
    with pytest.raises(ValueError): archive.bridge_person(raw, player, people)


@pytest.mark.parametrize('field,value', [('source_player_id', '123'),
    ('source_player_id', '11v11:124'), ('source_profile_url', 'https://other.example/players/actual-person-123/'),
    ('source_profile_url', 'https://www.11v11.com/players/actual-person-123/?view=other')])
def test_biography_url_and_player_identity_namespaces_must_match(field, value):
    player, people = person_inputs()
    player[field] = value
    with pytest.raises(ValueError, match='namespaced lineup player ID'):
        archive.bridge_person(biography(), player, people)


@pytest.mark.parametrize('count', [0, -1, None, True, '46'])
def test_schedule_completeness_cannot_be_disabled(count):
    with pytest.raises(ValueError, match='positive integer'):
        archive.first_fixture(schedule(), 'Team One', '2003-04', 'League Division 3', count)
