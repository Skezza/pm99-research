import copy
import pytest
from scripts import refine_opening_substitution_events_v2 as refine
from scripts.test_season_opening_used_substitutes_v2 import actual
from scripts.test_season_opening_used_substitutes_v1 import event


def document(bench):
    return {'clubs': [{'carrier_id': 100, 'status': 'original-first-fixture-reparsed',
        'evidence': {'source_club_id': 1, 'source_url': 'report', 'starting_xi': {'10': 'Starter'},
            'substitutes': bench, 'raw_sources': [{'url': 'report', 'path': 'report.html'}]}}],
        'used_substitute_refresh': {'summary': {'unresolved': [{'old': 'penalty'}]}}}


def test_refinement_preserves_independent_bench_and_positive_used_substitute():
    original = document({'30': 'Unused reserve'})
    replay = document({'30': 'Unused reserve', '20': 'Incoming Full Name'})
    before = copy.deepcopy(replay)
    output, summary = refine.refine(replay, lambda _: actual().encode(), original)
    assert output['clubs'] == replay['clubs'] and replay == before
    assert summary['unresolved_clubs'] == 0
    assert output['used_substitute_refresh']['summary']['unresolved'] == []


def test_replay_added_markerless_player_cannot_survive_refinement():
    with pytest.raises(ValueError, match='lacks actual substitution markers'):
        refine.refine(document({'20': 'Incoming Full Name'}), lambda _: event().encode(), document({}))


def test_refinement_cannot_introduce_an_unreplayed_substitute():
    with pytest.raises(ValueError, match='unreplayed player appearance'):
        refine.refine(document({}), lambda _: actual().encode(), document({}))
