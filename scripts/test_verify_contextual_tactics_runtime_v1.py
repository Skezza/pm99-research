import copy
import hashlib
import json
import struct

import pytest

from scripts import verify_contextual_tactics_runtime_v1 as visual
from scripts.test_season_contextual_tactics_v1 import context


def proof_fixture(tmp_path, monkeypatch):
    candidate, run = tmp_path / 'candidate', tmp_path / 'run'
    candidate.mkdir()
    (run / 'screens').mkdir(parents=True)
    ctx = context()
    layer = {'season': '2020-21', 'clubs': [
        {'carrier_id': 301, 'name': 'Bournemouth', 'formation': '4-4-2', 'context': ctx},
        {'carrier_id': 307, 'name': 'Stoke City', 'formation': '4-4-2', 'context': copy.deepcopy(ctx)}]}
    (candidate / 'contextual-tactics.json').write_text(json.dumps(layer))
    raw = b''
    for slot in ctx['slots']:
        states = slot['states']
        raw += b''.join(struct.pack('<2I', s[3], s[2]) for s in states)
        raw += b''.join(struct.pack('<2I', s[1], s[0]) for s in states)
        raw += struct.pack('<4I', *(sum(s[c] for s in states) // 20 for c in (3, 2, 1, 0)))
    proof = {'success': True, 'carrier_id': 301, 'coordinate_values_checked': 880,
             'averages_checked': 44, 'phases': ['attack', 'defend'], 'matches': [{'readback_hex': raw.hex()}]}
    (run / 'tactics-runtime-proof.json').write_text(json.dumps(proof))
    for phase in ('attack', 'defend'):
        (run / 'screens' / f'026_tactics_matrix_{phase}_all_players.png').write_bytes(phase.encode())
    frame = run / 'screens/026_tactics_matrix_defend_all_players.png'
    identity = {'matched': True, 'expected': 'Bournemouth', 'observed': 'Bournemouth',
                'screenshot': '/workspace/artifacts/screens/' + frame.name,
                'screenshot_sha256': hashlib.sha256(frame.read_bytes()).hexdigest()}
    (run / 'tactics-team-identity.json').write_text(json.dumps(identity))
    def centres(path, phase):
        c = 2 if phase == 'attack' else 0
        return [(188 + sum(s[c + 1] for s in slot['states']) // 20,
                 137 + sum(s[c] for s in slot['states']) // 20) for slot in ctx['slots']]
    monkeypatch.setattr(visual, 'marker_centres', centres)
    return candidate, run, identity


def test_explicit_non_stoke_carrier_full_states_and_pixels(tmp_path, monkeypatch):
    candidate, run, _ = proof_fixture(tmp_path, monkeypatch)
    report = visual.verify(candidate, run, 301)
    assert report['carrier_id'] == 301
    assert report['named_player_phases_checked'] == 22
    assert report['team_identity']['matched']
    assert report['team_identity']['expected'] == 'Bournemouth'
    with pytest.raises(ValueError):
        visual.verify(candidate, run, 307)


def test_cached_exact_grid_does_not_prove_wrong_visible_team(tmp_path, monkeypatch):
    candidate, run, identity = proof_fixture(tmp_path, monkeypatch)
    identity.update({'matched': False, 'observed': 'Arsenal'})
    (run / 'tactics-team-identity.json').write_text(json.dumps(identity))
    with pytest.raises(ValueError, match='actual tactics header'):
        visual.verify(candidate, run, 301)


def test_matching_memory_and_header_still_require_correct_pixels(tmp_path, monkeypatch):
    candidate, run, _ = proof_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(visual, 'marker_centres', lambda *_: [(0, 0)] * 11)
    with pytest.raises(ValueError, match='marker differs'):
        visual.verify(candidate, run, 301)


def test_replaced_team_identity_frame_fails_hash_binding(tmp_path, monkeypatch):
    candidate, run, identity = proof_fixture(tmp_path, monkeypatch)
    (run / 'screens' / identity['screenshot'].split('/')[-1]).write_bytes(b'another-screen')
    with pytest.raises(ValueError, match='screenshot hash changed'):
        visual.verify(candidate, run, 301)


def test_explicit_visual_review_is_separate_and_hash_bound(tmp_path, monkeypatch):
    candidate, run, identity = proof_fixture(tmp_path, monkeypatch)
    identity.update({'matched': False, 'observed': 'Boumemouth'})
    (run / 'tactics-team-identity.json').write_text(json.dumps(identity))
    review = {'schema_version': 'pm99-runtime-header-visual-review-v1', 'run_tag': run.name,
              'carrier_id': 301, 'observed_club': 'Bournemouth',
              'screenshot_sha256': identity['screenshot_sha256'],
              'method': 'assistant visual inspection of original screenshot'}
    path = tmp_path / 'review.json'
    path.write_text(json.dumps(review))
    result = visual.verify(candidate, run, 301, header_review=path)
    assert not result['team_identity']['matched']
    assert result['header_visual_review']['review']['observed_club'] == 'Bournemouth'
    review['screenshot_sha256'] = '0' * 64
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match='visual header review'):
        visual.verify(candidate, run, 301, header_review=path)
