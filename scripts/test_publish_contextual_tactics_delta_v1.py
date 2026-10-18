import json
import hashlib
from pathlib import Path

import pytest

from app.eq_initial_tactics import GRID_BYTES, patch_indexed_tactics, read_initial_tactics
from scripts import publish_contextual_tactics_delta_v1 as publisher
from scripts import season_contextual_tactics_v1 as tactics
from scripts import verify_contextual_tactics_runtime_v1 as visual
from scripts import season_pipeline_v2 as pipeline
from scripts.test_season_package_compiler_v2 import _write_fixture_base


def completion_fixture(tmp_path, monkeypatch):
    source, _ = _write_fixture_base(tmp_path)
    candidate = tmp_path / 'candidate'
    (candidate / 'DBDAT').mkdir(parents=True)
    raw = (source / 'DBDAT/EQ98030.FDI').read_bytes()
    states = [[list(s) for s in rows] for rows in read_initial_tactics(tactics.payloads(raw)[307]).states]
    states[1][0][1] = (states[1][0][1] + 20) % 398
    raw = patch_indexed_tactics(raw, {307: states})
    (candidate / 'DBDAT/EQ98030.FDI').write_bytes(raw)
    (candidate / 'candidate-receipt.json').write_text(json.dumps({'source_game_path': str(source)}))
    eq = tactics.payloads(raw)[307]
    offset = read_initial_tactics(eq).grid_offset
    (source / 'TACTICS').mkdir()
    (source / 'TACTICS/TACTIC.000').write_bytes(b'old-native-library')
    runs = [tmp_path / name for name in ('save', 'reload', 'match')]
    for run in runs:
        run.mkdir()
    (runs[0] / 'tactics_library').mkdir()
    saved = runs[0] / 'tactics_library/TACTIC.000'
    saved.write_bytes(b'\xff' + b'header' + eq[offset:offset + GRID_BYTES])
    commands = [
        ['--dbdat-dir', str(candidate / 'DBDAT')],
        ['--dbdat-dir', str(source / 'DBDAT'), '--tactics-override-file', str(saved), '--tactics-load-row', '2'],
        ['--dbdat-dir', str(candidate / 'DBDAT')],
    ]
    for run, command in zip(runs, commands):
        (run / 'control_launch.json').write_text(json.dumps({'child_command': command}))
    (runs[2] / 'summary.json').write_text(json.dumps({'success': True, 'dashboard_reached': True,
        'match_count': 1, 'skip_initial_tactics_strategy': True}))
    monkeypatch.setattr(visual, 'verify', lambda *_: {'success': True})
    monkeypatch.setattr(publisher.registry, 'relative_workspace_path', str)
    return candidate, runs, saved


def test_completed_pilot_requires_changed_native_save_and_old_baseline_reload(tmp_path, monkeypatch):
    candidate, runs, saved = completion_fixture(tmp_path, monkeypatch)
    report = publisher.verify_completion(candidate, *runs)
    assert report['save_reload_proven'] and report['match_smoke_proven']
    command = json.loads((runs[1] / 'control_launch.json').read_text())
    command['child_command'][1] = str(candidate / 'DBDAT')
    (runs[1] / 'control_launch.json').write_text(json.dumps(command))
    with pytest.raises(ValueError, match='negative control'):
        publisher.verify_completion(candidate, *runs)


def test_unchanged_library_file_is_not_save_proof(tmp_path, monkeypatch):
    candidate, runs, saved = completion_fixture(tmp_path, monkeypatch)
    source = Path(json.loads((candidate / 'candidate-receipt.json').read_text())['source_game_path'])
    (source / 'TACTICS/TACTIC.000').write_bytes(saved.read_bytes())
    with pytest.raises(ValueError, match='independently changed'):
        publisher.verify_completion(candidate, *runs)


def test_route_success_without_completed_match_is_not_match_proof(tmp_path, monkeypatch):
    candidate, runs, _ = completion_fixture(tmp_path, monkeypatch)
    summary = json.loads((runs[2] / 'summary.json').read_text())
    summary['match_count'] = 0
    (runs[2] / 'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError, match='complete a match'):
        publisher.verify_completion(candidate, *runs)


def test_registration_without_completion_proof_fails_before_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(visual, 'verify', lambda *_: {'success': True})
    with pytest.raises(ValueError, match='registration requires'):
        publisher.publish(tmp_path / 'absent', tmp_path / 'absent-run', release_id='candidate', register=True)


def test_inherited_json_semantic_hash_is_distinct_from_raw_file_hash(tmp_path):
    path = tmp_path / 'old-plan.json'
    value = {'name': 'José', 'positions': [1, 2, 3]}
    path.write_text(json.dumps(value, indent=2))
    expected = hashlib.sha256(pipeline.canonical_json_bytes(value)).hexdigest()
    assert publisher.verify_recipe_artifact(path, expected)['hash_contract'] == 'canonical-semantic-json'
    value['positions'][0] = 42
    path.write_text(json.dumps(value, indent=2))
    with pytest.raises(ValueError, match='hash changed'):
        publisher.verify_recipe_artifact(path, expected)
