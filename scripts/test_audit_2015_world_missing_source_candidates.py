from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_2015_world_missing_source_candidates import build_receipt  # noqa: E402


def _fixture(*, baseline: str = "Perugia") -> dict[str, object]:
    # Keep the fixture at the real 149-gap cardinality while making only one
    # family row interesting.  The remaining synthetic carriers are
    # intentionally unclassified and must remain unresolved.
    carrier_ids = [225, *range(10000, 10148)]
    carriers = [
        {
            "carrier_id": carrier_id,
            "baseline_club": {"name": baseline if carrier_id == 225 else f"Unknown {carrier_id}"},
            "roster_slots": [{}],
        }
        for carrier_id in carrier_ids
    ]
    proposals = [
        {
            "carrier_id": carrier_id,
            "status": "no-distinct-captured-top-competition-squad-with-required-capacity"
            if carrier_id == 225
            else "no-captured-source-country",
        }
        for carrier_id in carrier_ids
    ]
    # This extra ready row proves that a source selector already consumed by
    # another carrier is not silently reused as a direct closure.
    proposals.append(
        {
            "carrier_id": 999,
            "status": "source-squad-ready",
            "source_selector": {
                "country_catalog": "italy",
                "competition_catalog": "seriea",
                "club_name": "Empoli",
                "source_path": "italy/2015-2016/seriea/empoli.txt",
                "source_sha256": "a" * 64,
            },
        }
    )
    stats = {
        "player_id": "1",
        "name": "Example",
        "season": "16",
        "year": "2016",
        "page_url": "https://www.fifaindex.com/player/1/example/fifa16/",
        "club": "Empoli",
    }
    return {
        "registry": {"carriers": carriers},
        "source_draft": {"proposals": proposals},
        "fs_data": {
            "schema_version": "pm99-footballsquads-season-capture-v1",
            "season": {"label": "2015/16"},
            "source": {"revision": "test"},
            "clubs": [
                {
                    "country_catalog": "italy",
                    "competition_catalog": "seriea",
                    "club_name": "Empoli",
                    "source_path": "italy/2015-2016/seriea/empoli.txt",
                    "source_sha256": "a" * 64,
                    "players": [{}],
                }
            ],
        },
        "stats_rows": [stats],
        "fut_rows": [{"CLUB": "Empoli", "LEAGUE": "Serie A", "LOADDATE": "2018-09-19"}],
        "tm_data": {
            "schema_version": "pm99-world-2015-transfermarkt-opening-fixtures-v1",
            "season": "2015",
            "source": {"database_version": "test"},
            "clubs": [],
        },
    }


def _build(tmp_path: Path, **kwargs: object) -> dict[str, object]:
    value = _fixture(**kwargs)
    paths = {key: tmp_path / f"{key}.fixture" for key in ("fs", "stats", "fut", "tm")}
    for path in paths.values():
        path.write_bytes(b"fixture\n")
    return build_receipt(
        registry=value["registry"],
        source_draft=value["source_draft"],
        fs_data=value["fs_data"],
        stats_rows=value["stats_rows"],
        fut_rows=value["fut_rows"],
        tm_data=value["tm_data"],
        fs_path=paths["fs"],
        stats_path=paths["stats"],
        fut_path=paths["fut"],
        tm_path=paths["tm"],
    )


def test_exact_candidate_retains_selector_and_marks_reuse_conflict(tmp_path: Path) -> None:
    result = _build(tmp_path, baseline="Empoli")
    row = next(row for row in result["records"] if row["carrier_id"] == 225)
    candidate = row["footballsquads_exact_candidates"][0]
    assert candidate["source_selector"]["source_path"].endswith("empoli.txt")
    assert candidate["capacity_sufficient"] is True
    assert candidate["selector_already_used_by_carrier_ids"] == [999]
    assert candidate["eligible_for_direct_gap_closure"] is False


def test_similar_but_non_exact_name_is_not_joined(tmp_path: Path) -> None:
    result = _build(tmp_path, baseline="Empoli United")
    row = next(row for row in result["records"] if row["carrier_id"] == 225)
    assert row["footballsquads_exact_candidates"] == []
    assert row["fifa16_exact_candidates"] == []
    assert row["transfermarkt_exact_candidates"] == []
    assert row["candidate_status"] == "unresolved"
    assert result["candidate_summary"]["unresolved_carrier_count"] == 149
