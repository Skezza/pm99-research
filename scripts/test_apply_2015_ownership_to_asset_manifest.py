"""Tests for ownership-aware 2015 portrait dispositions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.apply_2015_ownership_to_asset_manifest import build


def test_displaced_portrait_is_preserved_and_loses_modern_candidate() -> None:
    manifest = {"schema_version": "pm99-world-2015-asset-candidate-manifest-v1", "coverage": {}, "sources": {}, "clubs": [{"carrier_id": 1, "players": [{"slot_index": 0, "player_carrier_id": 10, "fifa16_player_id": 99, "portrait": {"status": "fifa16-url-candidate"}}]}, {"carrier_id": 2, "players": [{"slot_index": 0, "player_carrier_id": 20, "fifa16_player_id": 99, "portrait": {"status": "fifa16-url-candidate"}}]}]}
    ownership = {"schema_version": "pm99-world-2015-person-ownership-decisions-v1", "decisions": [{"retained": {"team_carrier_id": 1, "slot_index": 0, "player_carrier_id": 10}, "displaced": [{"team_carrier_id": 2, "slot_index": 0, "player_carrier_id": 20, "disposition": "preserve-native-carrier-row"}]}]}
    result = build(manifest=manifest, ownership=ownership)
    assert result["clubs"][0]["players"][0]["portrait"]["status"] == "fifa16-url-candidate"
    displaced = result["clubs"][1]["players"][0]
    assert displaced["portrait"]["status"] == "preserve-native-carrier-portrait"
    assert "fifa16_player_id" not in displaced
