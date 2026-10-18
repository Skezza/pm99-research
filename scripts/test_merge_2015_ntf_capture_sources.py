"""Fixture tests for disjoint, content-addressed NTF capture merging."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.merge_2015_ntf_capture_sources import SCHEMA, merge


def _capture(carrier_id: int, source_path: str) -> dict:
    return {
        "schema_version": SCHEMA,
        "season": {"catalog": "test", "label": "2015"},
        "source": {"title": "fixture"},
        "clubs": [
            {
                "candidate_carrier_id": carrier_id,
                "country_catalog": "test-country",
                "competition_catalog": "test-competition",
                "club_name": f"Club {carrier_id}",
                "source_path": source_path,
                "source_sha256": f"hash-{carrier_id}",
                "players": [],
            }
        ],
    }


def test_merge_keeps_disjoint_carriers_and_counts_players() -> None:
    result = merge([_capture(1, "one.html"), _capture(2, "two.html")])
    assert result["summary"] == {"club_count": 2, "player_count": 0, "candidate_carrier_count": 2}
    assert [club["candidate_carrier_id"] for club in result["clubs"]] == [1, 2]
    assert len(result["source"]["inputs"]) == 2


def test_merge_rejects_reused_candidate_carrier() -> None:
    try:
        merge([_capture(1, "one.html"), _capture(1, "other.html")])
    except ValueError as exc:
        assert "candidate carrier" in str(exc)
    else:
        raise AssertionError("reused carrier must not be merged")


if __name__ == "__main__":
    test_merge_keeps_disjoint_carriers_and_counts_players()
    test_merge_rejects_reused_candidate_carrier()
    print("manual fixture tests: ok")
