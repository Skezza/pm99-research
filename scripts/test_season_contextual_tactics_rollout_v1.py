import copy

import pytest

from scripts import season_contextual_tactics_rollout_v1 as rollout
from scripts import season_contextual_tactics_v1 as tactics


def source(formation):
    template = rollout.formation_template(formation)
    players = {f'p-{i}': {'carrier_id': i + 1, 'facts': {'primary_position': 'G' if i == 0 else 'M'}}
               for i in range(11)}
    positions = [[114, 20, 114, 20]]
    for band, count in enumerate(map(int, formation.split('-'))):
        positions.extend([[30 + j * 35, 100 + band * 80, 30 + j * 35, 100 + band * 80]
                          for j in range(count)])
    club = {'opening': {'formation': formation, 'starting_xi_player_ids': list(players),
                        'tactics_positions': positions}}
    return club, players, [(i + 1, f'Player {i + 1}') for i in range(11)]


@pytest.mark.parametrize('formation', rollout.FORMATIONS)
def test_all_seventeen_templates_are_bounded_distinct_and_deterministic(formation):
    club, players, xi = source(formation)
    offsets = [[z % 5 - 2, z % 7 - 3, z % 5 - 2, z % 7 - 3] for z in range(20)]
    first = rollout.build_context(club, players, xi, offsets)
    assert rollout.build_context(club, players, xi, offsets) == first
    tactics.validate_context(first)
    assert first['slots'][0]['states'][0][3] == 0
    assert all(s[3] > s[1] for p in first['slots'][1:] for s in p['states'])


def test_native_slot_reorder_keeps_player_deployment_not_zip_order():
    club, players, xi = source('4-3-3')
    expected = rollout.build_context(club, players, xi, [[z % 5 - 2] * 4 for z in range(20)])
    reordered = [xi[0]] + xi[5:8] + xi[1:5] + xi[8:]
    actual = rollout.build_context(club, players, reordered, [[z % 5 - 2] * 4 for z in range(20)])
    assert {s['native_player_id']: s for s in expected['slots']} == {s['native_player_id']: s for s in actual['slots']}
    assert [s['native_player_id'] for s in actual['slots']] == [p[0] for p in reordered]


def test_ambiguous_line_or_mismatched_xi_is_not_guessed():
    club, players, xi = source('4-4-2')
    bad = copy.deepcopy(club)
    bad['opening']['tactics_positions'][5][1] = bad['opening']['tactics_positions'][4][1]
    with pytest.raises(ValueError, match='ambiguous'):
        rollout.build_context(bad, players, xi, [[0] * 4] * 20)
    with pytest.raises(ValueError, match='different players'):
        rollout.build_context(club, players, xi[:-1] + [(99, 'Wrong')], [[0] * 4] * 20)


def test_natural_midfielder_at_fullback_remains_fullback():
    club, players, xi = source('4-4-2')
    ctx = rollout.build_context(club, players, xi, [[z % 5 - 2] * 4 for z in range(20)])
    assert ctx['slots'][1]['role'] == 'RB'
    assert ctx['slots'][4]['role'] == 'LB'
