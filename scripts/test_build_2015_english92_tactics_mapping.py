from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_2015_english92_release import _opening_tactics_from_first_fixture  # noqa: E402


def test_first_fixture_coordinates_use_pm99_vertical_then_depth_order() -> None:
    """Keep the short vertical PM99 axis separate from its wide depth axis."""
    contract = {
    "starting_xi": [
            {"position": "G", "pitch_left_percent": 40.0, "pitch_top_percent": 80.0},  # goalkeeper
            {"position": "D", "pitch_left_percent": 73.0, "pitch_top_percent": 61.0},  # right-back
            {"position": "D", "pitch_left_percent": 7.5, "pitch_top_percent": 61.0},  # left-back
            {"position": "F", "pitch_left_percent": 40.0, "pitch_top_percent": 3.0},  # striker
            *[{"position": "M", "pitch_left_percent": 40.0, "pitch_top_percent": 43.0}] * 7,
        ],
        "formation": "4-1-4-1",
    }

    positions = _opening_tactics_from_first_fixture(contract)

    assert positions[0] == [128, 55, 128, 55]
    assert positions[1] == [62, 130, 62, 130]
    assert positions[2] == [193, 130, 193, 130]
    assert positions[3] == [128, 400, 128, 400]
    assert all(60 <= position[0] <= 200 for position in positions)


def test_4141_uses_one_attacking_line_not_five_source_diagram_dots() -> None:
    """The Stoke regression: four midfielders must not render as strikers."""
    contract = {
        "formation": "4-1-4-1",
        "starting_xi": [
            {"position": "G", "pitch_left_percent": 40.0, "pitch_top_percent": 80.0},
            {"position": "D", "pitch_left_percent": 52.5, "pitch_top_percent": 63.0},
            {"position": "D", "pitch_left_percent": 28.0, "pitch_top_percent": 63.0},
            {"position": "D", "pitch_left_percent": 7.5, "pitch_top_percent": 61.0},
            {"position": "D", "pitch_left_percent": 73.0, "pitch_top_percent": 61.0},
            {"position": "M", "pitch_left_percent": 40.0, "pitch_top_percent": 43.0},
            {"position": "M", "pitch_left_percent": 50.0, "pitch_top_percent": 23.0},
            {"position": "M", "pitch_left_percent": 30.0, "pitch_top_percent": 23.0},
            {"position": "M", "pitch_left_percent": 15.0, "pitch_top_percent": 18.0},
            {"position": "F", "pitch_left_percent": 65.0, "pitch_top_percent": 18.0},
            {"position": "F", "pitch_left_percent": 40.0, "pitch_top_percent": 3.0},
        ],
    }

    positions = _opening_tactics_from_first_fixture(contract)

    assert [position[1] for position in positions] == [
        55, 130, 130, 130, 130, 210, 280, 280, 280, 280, 400,
    ]
    assert sum(position[1] >= 305 for position in positions) == 1


def test_tactics_mapping_rejects_an_ambiguous_formation() -> None:
    contract = {
        "formation": "4-4-3",
        "starting_xi": [{"position": "G", "pitch_left_percent": 40, "pitch_top_percent": 80}] * 11,
    }

    with pytest.raises(ValueError, match="ten outfield"):
        _opening_tactics_from_first_fixture(contract)
