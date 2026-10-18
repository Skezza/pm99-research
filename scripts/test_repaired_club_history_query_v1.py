import copy
import json
import pytest
from scripts import season_published_transfer_history_v1 as history
from scripts import repair_prefix_selected_opening_sources_v1 as repair


def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'ROOT', tmp_path)
    source = tmp_path / 'capture.json'
    source.write_text('{}')
    correction = {'club': 'Example', 'carrier_id': 14, 'before': {'wrong': True},
        'after': {'correct': True}, 'original_capture_path': source.name,
        'original_capture_sha256': history.registry.sha256_file(source)}
    corrected = tmp_path / 'correction.json'
    corrected.write_text(json.dumps(correction))
    plan = {'schema_version': 'pm99-source-repaired-opening-club-roster-plan-v1',
        'club': 'Example', 'carrier_id': 14, 'bindings': {
            'source_correction_path': corrected.name,
            'source_correction_sha256': history.registry.sha256_file(corrected)},
        'desired_matchday_people': [{'source_player_id': i, 'requires_new_club_slot': i == 0,
            'other_club_player_ids': ['old-copy'] if i == 0 else []} for i in range(11)]}
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(plan))
    monkeypatch.setattr(repair, 'replay', lambda *args: (correction['after'], {
        'starting_xi': {str(i): 'Player' for i in range(11)}, 'substitutes': {}}, []))
    return path, plan, correction


def test_only_new_original_matchday_people_with_other_club_copies_are_queried(tmp_path, monkeypatch):
    path, _, _ = inputs(tmp_path, monkeypatch)
    assert history.repaired_club_plan_ids(path) == {0}


@pytest.mark.parametrize('problem', ['invented-person', 'wrong-club', 'changed-original', 'changed-correction', 'unreproducible'])
def test_plan_labels_never_replace_original_report_replay(problem, tmp_path, monkeypatch):
    path, plan, correction = inputs(tmp_path, monkeypatch)
    if problem == 'invented-person': plan['desired_matchday_people'][0]['source_player_id'] = 99
    if problem == 'wrong-club': plan['club'] = 'Another Club'
    if problem == 'changed-original': (tmp_path / 'capture.json').write_text('{"changed":true}')
    if problem == 'changed-correction': (tmp_path / 'correction.json').write_text('{}')
    if problem == 'unreproducible':
        monkeypatch.setattr(repair, 'replay', lambda *args: ({'invented': True}, {}, []))
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError): history.repaired_club_plan_ids(path)
