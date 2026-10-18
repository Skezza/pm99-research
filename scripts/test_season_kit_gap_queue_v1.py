import json
from pathlib import Path

from scripts.season_kit_gap_queue_v1 import build_queue, canonical_json_bytes


def test_gap_queue_prioritises_recurring_clubs_deterministically(tmp_path: Path) -> None:
    source = tmp_path / "sources"
    for season, carrier in (("2000-01", 10), ("2001-02", 20)):
        directory = source / season
        directory.mkdir(parents=True)
        catalogue = {
            "rows": [
                {"carrier_id": carrier, "club_name": "Recurring FC", "status": "blocked-no-target-season-source"},
                {"carrier_id": carrier + 1, "club_name": f"Single {season}", "status": "blocked-no-target-season-source"},
            ]
        }
        request = {"clubs": [{"carrier_id": carrier}, {"carrier_id": carrier + 1}]}
        (directory / "kit-catalogue-v1.json").write_bytes(canonical_json_bytes(catalogue))
        (directory / "kit-catalogue-request-v1.json").write_bytes(canonical_json_bytes(request))

    first = build_queue(source, tmp_path / "cache")
    second = build_queue(source, tmp_path / "cache")
    assert first == second
    assert first["rows"][0]["club_name"] == "Recurring FC"
    assert first["rows"][0]["recurring_club_gap_count"] == 2
    assert first["coverage"]["source_family_counts"]["no-wikipedia-exact-page"] == 4
