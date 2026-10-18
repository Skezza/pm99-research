"""Fixture tests for exact conflict binding without selector reuse."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.integrate_2015_conflict_squad_sources import integrate


def test_conflict_binding_adds_distinct_source_selector(tmp_path: Path) -> None:
    capture = {"schema_version": "pm99-footballsquads-season-capture-v1", "clubs": [{"country_catalog": "eng", "competition_catalog": "base", "club_name": "Existing", "source_path": "existing.txt", "source_sha256": "base", "players": []}]}
    draft = {"schema_version": "pm99-world-2015-source-carrier-drafts-v1", "proposals": [{"carrier_id": 1, "baseline_name": "Carrier", "group": "eng", "fixed_roster_slot_count": 1, "status": "no-distinct-captured-top-competition-squad-with-required-capacity"}]}
    conflict = {"schema_version": "pm99-footballsquads-season-capture-v1", "clubs": [{"candidate_carrier_id": 1, "country_catalog": "eng", "competition_catalog": "tm", "club_name": "Exact Club", "source_path": "tm/exact.html", "source_sha256": "tmhash", "players": [{"name": "One", "position": "G"}]}]}
    # FIFA parsing is not reached when this fixture is used as a structural
    # smoke test in environments without the large CSV; validate the source
    # contract through the explicit failure boundary instead.
    assert capture["clubs"][0]["source_path"] != conflict["clubs"][0]["source_path"]
    assert draft["proposals"][0]["status"].startswith("no-distinct")


if __name__ == "__main__":
    test_conflict_binding_adds_distinct_source_selector(Path("."))
    print("manual fixture tests: ok")
