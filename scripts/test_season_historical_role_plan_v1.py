from scripts import season_historical_role_plan_v1 as plan


def test_fifa_roles_require_exact_edition_identity_and_date():
    p = {'name': 'Test Player', 'facts': {'birth_date': '1990-01-01', 'primary_position': 'F'}}
    row = {'player_id': '42', 'long_name': 'Test Player', 'dob': '1990-01-01',
           'player_positions': 'RW, ST', 'fifa_update_date': '2014-09-18'}
    index = {(15, 'testplayer', '1990-01-01'): [row]}
    assert plan.fifa_roles(p, '2014-15', index)[0] == [11, 12]
    assert plan.fifa_roles(p, '2013-14', index) == (None, None)
    p['facts']['birth_date'] = {'policy': 'preserve-existing-mode1'}
    assert plan.fifa_roles(p, '2014-15', index) == (None, None)


def test_same_name_and_date_with_multiple_people_is_not_a_match():
    p = {'name': 'Test Player', 'facts': {'birth_date': '1990-01-01', 'primary_position': 'F'}}
    rows = [{'player_id': str(i)} for i in (1, 2)]
    assert plan.fifa_roles(p, '2014-15', {(15, 'testplayer', '1990-01-01'): rows}) == (None, None)
