from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_2015_world_source_carrier_drafts import build_drafts  # noqa: E402


def _club(name: str, count: int, *, competition: str = "laliga") -> dict[str, object]:
    return {
        "country_catalog": "spain",
        "competition_catalog": competition,
        "club_name": name,
        "competition_name": "La Liga",
        "source_path": f"spain/2015-2016/{competition}/{name}.txt",
        "source_sha256": "a" * 64,
        "players": [{} for _ in range(count)],
    }


def test_same_name_source_is_preferred_and_capacity_is_preserved() -> None:
    registry = {"carriers": [{
        "carrier_id": 1,
        "baseline_club": {"name": "F.C. Barcelona"},
        "roster_slots": [{}, {}],
    }]}
    source = {
        "schema_version": "pm99-footballsquads-season-capture-v1",
        "clubs": [_club("Other Club", 5), _club("FC Barcelona", 2)],
    }

    result = build_drafts(registry=registry, source_capture=source)

    row = result["proposals"][0]
    assert row["status"] == "source-squad-ready"
    assert row["source_club_name"] == "FC Barcelona"
    assert row["allocation_method"] == "same-normalised-club-name"
    assert row["source_competition_catalogs"] == ["laliga"]


def test_second_division_source_is_never_used_for_top_competition_carrier() -> None:
    registry = {"carriers": [{
        "carrier_id": 1,
        "baseline_club": {"name": "Carrier"},
        "roster_slots": [{}, {}],
    }]}
    source = {
        "schema_version": "pm99-footballsquads-season-capture-v1",
        "clubs": [_club("Segunda Club", 10, competition="segunda"), _club("La Liga Club", 2)],
    }

    result = build_drafts(registry=registry, source_capture=source)

    assert result["proposals"][0]["source_club_name"] == "La Liga Club"


def test_missing_source_country_is_explicit_not_reassigned() -> None:
    registry = {"carriers": [{
        "carrier_id": 700,
        "baseline_club": {"name": "Carrier"},
        "roster_slots": [{}],
    }]}
    source = {"schema_version": "pm99-footballsquads-season-capture-v1", "clubs": [_club("FC Barcelona", 2)]}

    result = build_drafts(registry=registry, source_capture=source)

    assert result["proposals"][0]["status"] == "no-captured-source-country"
