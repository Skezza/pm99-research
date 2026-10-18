from scripts import inventory_duplicate_club_dispositions_v1 as mod


def club(id, name):
    return {'id': f'club-{id}', 'carrier_id': id, 'name': name,
        'division': 'preserve-existing-mode1-membership' if id >= 3300 else 'Division Three',
        'roster_player_ids': list(range(18))}


def capture(name, path):
    return {'club_name': name, 'source_path': path, 'source_sha256': 'a' * 64, 'country_catalog': 'eng'}


def test_exact_alias_duplicate_and_absent_opening_target_are_only_inventory():
    clubs = [club(3305, 'Boreham W'), club(3323, 'Boreham Wood')]
    captures = [capture('Wrexham', 'soccerbase/team/2859/august'), capture('Wrexham', 'eng/2021-2022/national/wrexham.txt')]
    duplicate, targets = mod.candidates(clubs, captures)
    assert [r['carrier_id'] for r in duplicate] == [3323]
    assert duplicate[0]['same_real_club_lower_carriers'][0]['carrier_id'] == 3305
    assert targets[0]['whole_club_route_input_unambiguous']
    assert clubs[1]['name'] == 'Boreham Wood'


def test_existing_club_and_alias_target_are_not_reintroduced():
    duplicate, targets = mod.candidates([club(3305, 'Boreham W')],
        [capture('Boreham Wood', 'soccerbase/team/123/august')])
    assert duplicate == targets == []


def test_multiple_openings_or_missing_annual_are_explicit_not_approved():
    _, targets = mod.candidates([], [capture('Wrexham', 'soccerbase/team/2859/august'),
        capture('Wrexham', 'soccerbase/team/2859/other')])
    assert len(targets) == 1 and targets[0]['opening_capture_count'] == 2
    assert not targets[0]['whole_club_route_input_unambiguous']


def test_playable_club_is_never_selected_for_disposal():
    duplicate, _ = mod.candidates([club(351, 'Boreham W'), club(3323, 'Boreham Wood')], [])
    assert [r['carrier_id'] for r in duplicate] == [3323]
def test_abbreviated_doncaster_is_not_an_unrepresented_new_club():
    from scripts import prepare_duplicate_club_disposition_v1 as whole
    assert whole.club_keys('Doncaster') & whole.club_keys('Doncaster R.', 'Doncaster Rovers Football Club')
