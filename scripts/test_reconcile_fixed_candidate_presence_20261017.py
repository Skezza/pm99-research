from scripts.reconcile_fixed_candidate_presence_20261017 import observe


def actor(carrier, name, birthday):
    return dict(carrier_id=carrier, id=f'player-{carrier}', club_id=f'club-{carrier}',
        source_name=name, facts=dict(birth_date=birthday))


def test_moved_slot_and_corrected_birthday_do_not_hide_duplicate():
    case = dict(players=[dict(source_name='Jack Midson')])
    result = observe(case, [actor(10926, 'Jean-Michel Sigere', '1977-01-26'),
        actor(10922, 'Jack Midson', '1983-09-12'), actor(11098, 'Jack Midson', '1983-07-21')])
    assert result['observation'] == 'multiple-current-name-matches'
    assert {p['carrier_id'] for p in result['matches']} == {10922, 11098}


def test_single_name_is_not_automatic_historical_clearance():
    case = dict(players=[dict(source_name='Richard Brodie')])
    result = observe(case, [actor(1, 'Richard Brodie', '1987-07-08')])
    assert result['observation'] == 'single-current-name-match-needs-source-proof'


def test_absent_names_remain_identity_review_not_repaired():
    assert observe(dict(players=[dict(source_name='Unknown')]), [])['observation'] == (
        'no-current-name-match-needs-identity-review')


def test_published_shirt_heading_does_not_hide_plain_name_copy():
    case = dict(players=[dict(source_name='#19 Kayden Jackson')])
    players = [actor(1, '#19 Kayden Jackson', '1994-02-22'),
        actor(2, 'Kayden Jackson', '1994-02-22')]
    assert observe(case, players)['observation'] == 'multiple-current-name-matches'


def test_indexed_and_unindexed_observations_agree():
    from scripts.reconcile_fixed_candidate_presence_20261017 import name_key
    players = [actor(1, '#19 Kayden Jackson', '1994-02-22'),
        actor(2, 'Kayden Jackson', '1994-02-22')]
    index = {}
    for player in players:
        index.setdefault(name_key(player['source_name']), []).append(player)
    case = dict(players=[dict(source_name='Kayden Jackson'), dict(source_name='#19 Kayden Jackson')])
    assert observe(case, players) == observe(case, players, name_index=index)
