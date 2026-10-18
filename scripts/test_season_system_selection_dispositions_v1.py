import copy
import pytest
from scripts.season_system_selection_dispositions_v1 import verify_club


def fixture():
    players = {id: {'id': f'player-{id}', 'club_id': 'club-8801',
        'policy': 'preserve-existing-mode1', 'facts': {'birth_date': {'policy': 'preserve-existing-mode1'}},
        'proof': {'artifact_id': 'world-mode1-runtime-contract', 'grade': 'static-contract'}}
        for id in range(19400, 19411)}
    club = {'id': 'club-8801', 'carrier_id': 8801, 'name': 'Sel. América',
        'full_name': 'Selección América', 'division': 'preserve-existing-mode1-membership',
        'opening': {'policy': 'preserve-existing-mode1'}, 'roster_player_ids': [p['id'] for p in players.values()]}
    records = {id: bytes([id % 255]) for id in players}
    return club, players, b'base-club', b'base-club', records, copy.deepcopy(records)


def test_only_exact_factory_selection_is_exempted():
    verify_club(*fixture())


@pytest.mark.parametrize('fault', ['real-club', 'edited-name', 'edited-fact', 'source-person',
                                  'native-player', 'native-club', 'missing-member', 'extra-member'])
def test_changed_or_real_club_cannot_hide_under_selection_exception(fault):
    club, players, old_eq, new_eq, base, current = fixture()
    if fault == 'real-club': club['carrier_id'] = 1002
    if fault == 'edited-name': club['name'] = 'Real Historical Club'
    if fault == 'edited-fact': players[19403]['facts']['birth_date'] = '1982-03-31'
    if fault == 'source-person': players[19403]['source_name'] = 'Real Historical Player'
    if fault == 'native-player': current[19403] += b'edited'
    if fault == 'native-club': new_eq += b'edited'
    if fault == 'missing-member': club['roster_player_ids'].pop()
    if fault == 'extra-member': players[42] = copy.deepcopy(players[19403])
    with pytest.raises(ValueError): verify_club(club, players, old_eq, new_eq, base, current)
