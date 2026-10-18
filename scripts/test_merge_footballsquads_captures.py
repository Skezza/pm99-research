from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.merge_footballsquads_captures import MergeError, merge_captures  # noqa: E402


def _capture(*, catalog: str, label: str, country: str, club_name: str) -> dict[str, object]:
    return {
        "schema_version": "pm99-footballsquads-season-capture-v1",
        "source": {
            "title": "footballcsv/cache.footballsquads",
            "repository": "https://example.test/source",
            "revision": "a" * 40,
            "license": "CC0-1.0",
        },
        "season": {"catalog": catalog, "label": label},
        "clubs": [{
            "country_catalog": country,
            "competition_catalog": "league",
            "club_name": club_name,
            "competition_name": "League",
            "source_path": f"{country}/{catalog}/league/{club_name}.txt",
            "source_sha256": "b" * 64,
            "players": [{"unresolved_fields": []}],
        }],
        "summary": {},
    }


def test_merge_keeps_calendar_and_split_year_sources_in_one_historical_input() -> None:
    split = _capture(catalog="2015-2016", label="2015/16", country="spain", club_name="Barcelona")
    calendar = _capture(catalog="2015", label="2015", country="brazil", club_name="Santos")
    result = merge_captures(captures=[("calendar.json", calendar, "c" * 64), ("split.json", split, "d" * 64)])

    assert result["season"]["catalog"] == "2015-world-hybrid"
    assert result["summary"]["club_count_by_country"] == {"brazil": 1, "spain": 1}
    assert [row["capture_name"] for row in result["source"]["inputs"]] == ["calendar.json", "split.json"]


def test_merge_names_the_logical_target_season_without_rewriting_inputs() -> None:
    split = _capture(catalog="2008-2009", label="2008/09", country="spain", club_name="Barcelona")
    calendar = _capture(catalog="2008", label="2008", country="brazil", club_name="Santos")

    result = merge_captures(
        captures=[("calendar.json", calendar, "c" * 64), ("split.json", split, "d" * 64)],
        merged_catalog="2008-09-hybrid",
        merged_label="2008/09",
    )

    assert result["season"] == {"catalog": "2008-09-hybrid", "label": "2008/09"}
    assert result["source"]["inputs"] == [
        {"capture_name": "calendar.json", "sha256": "c" * 64, "catalog": "2008", "label": "2008"},
        {"capture_name": "split.json", "sha256": "d" * 64, "catalog": "2008-2009", "label": "2008/09"},
    ]


def test_merge_rejects_duplicate_club_source_selectors() -> None:
    one = _capture(catalog="2015", label="2015", country="brazil", club_name="Santos")
    two = _capture(catalog="2015", label="2015", country="brazil", club_name="Santos")
    with pytest.raises(MergeError, match="overlap"):
        merge_captures(captures=[("one.json", one, "c" * 64), ("two.json", two, "d" * 64)])


def test_merge_rejects_ambiguous_duplicate_capture_names() -> None:
    one = _capture(catalog="2015", label="2015", country="brazil", club_name="Santos")
    two = _capture(catalog="2015-2016", label="2015/16", country="spain", club_name="Barcelona")
    with pytest.raises(MergeError, match="unique non-blank names"):
        merge_captures(captures=[("source.json", one, "c" * 64), ("source.json", two, "d" * 64)])


def test_merge_retains_hash_bound_blocked_sources() -> None:
    split = _capture(catalog="2008-2009", label="2008/09", country="spain", club_name="Barcelona")
    split["blocked_sources"] = [
        {"source_path": "spain/2008-2009/laliga/broken.txt", "source_sha256": "e" * 64, "reason": "bad squad row"}
    ]
    calendar = _capture(catalog="2008", label="2008", country="brazil", club_name="Santos")

    result = merge_captures(
        captures=[("calendar.json", calendar, "c" * 64), ("split.json", split, "d" * 64)],
        merged_catalog="2008-09-hybrid",
        merged_label="2008/09",
    )

    assert result["blocked_sources"] == split["blocked_sources"]
    assert result["summary"]["blocked_source_count"] == 1
