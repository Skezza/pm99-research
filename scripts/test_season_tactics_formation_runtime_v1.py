import json

import pytest

from scripts import season_tactics_formation_runtime_v1 as runtime
from scripts import season_contextual_tactics_rollout_v1 as rollout


def test_samples_cover_every_reviewed_shape_and_correct_native_buttons():
    assert {r[0] for r in runtime.SAMPLES} == set(rollout.FORMATIONS)
    for division, count, button in [('Premier League', 20, (77, 302)), ('Championship', 24, (77, 337)),
                                     ('League One', 24, (559, 302)), ('League Two', 24, (559, 337))]:
        clubs = [{'carrier_id': i, 'name': f'Club {i:02d}', 'division': division} for i in range(count)]
        coords = runtime.selector({'clubs': clubs}, clubs[0])
        assert coords['division'] == button
        assert coords['team'] == (178, 323)
        assert runtime.selector({'clubs': clubs}, clubs[count // 2])['team'] == (178, 360)
    with pytest.raises(ValueError, match='grid size'):
        runtime.selector({'clubs': clubs[:3]}, clubs[0])


def test_missing_runtime_family_evidence_does_not_qualify_a_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.registry, 'supported_seasons', lambda: ['2015-16'])
    candidate = tmp_path / '2015-16/english-rollout-candidate-v3'
    candidate.mkdir(parents=True)
    (candidate / 'contextual-tactics.json').write_text(json.dumps({'clubs': [{'formation': '3-5-2'}]}))
    with pytest.raises(ValueError, match='unproved formation families: 3-5-2'):
        runtime.verify_coverage(tmp_path, tmp_path)
