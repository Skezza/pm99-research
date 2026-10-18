from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_2015_world_v2_package_projection as projection  # noqa: E402


def test_portrait_index_uses_carrier_and_slot_not_stale_player_id() -> None:
    receipt = {"successes": [{"carrier_id": 3101, "slot_index": 0, "player_carrier_id": 8770}], "failures": []}
    assert projection._portrait_index(receipt)[(3101, 0)]["player_carrier_id"] == 8770
