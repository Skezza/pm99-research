"""Tests for the source-only 2015 top-flight membership receipt."""

import json
from pathlib import Path

from scripts.capture_2015_top_flight_membership_v1 import League, capture, parse_membership


def _payload() -> bytes:
    return json.dumps({"parse": {"title": "2015 Test League", "pageid": 123, "text": "<h2 id=\"Teams\">Teams</h2><table class=\"wikitable\"><tr><th>Club</th><th>City</th></tr><tr><td><a href=\"/wiki/Alpha_FC\" title=\"Alpha FC\">Alpha</a></td><td>A</td></tr><tr><td><a href=\"/wiki/Beta_FC\" title=\"Beta FC\">Beta</a></td><td>B</td></tr></table><h2 id=\"Results\">Results</h2>"}}).encode("utf-8")


def test_parse_membership_uses_the_teams_table_first_column() -> None:
    title, page_id, teams = parse_membership(_payload())
    assert (title, page_id) == ("2015 Test League", 123)
    assert teams == [
        {"name": "Alpha", "article_title": "Alpha FC", "article_path": "/wiki/Alpha_FC"},
        {"name": "Beta", "article_title": "Beta FC", "article_path": "/wiki/Beta_FC"},
    ]


def test_capture_is_cached_and_source_only(tmp_path: Path) -> None:
    league = League("test", "test-country", "2015 Test League", "2015", 2)
    result = capture(
        leagues=(league,),
        cache_root=tmp_path,
        retrieved_on="2026-09-12",
        fetch=lambda _: _payload(),
    )
    assert result["summary"] == {
        "requested_family_count": 1,
        "captured_family_count": 1,
        "unresolved_family_count": 0,
        "team_count": 2,
    }
    record = result["leagues"][0]
    assert record["country_catalog"] == "test-country"
    assert record["teams"][0]["name"] == "Alpha"
    assert "carrier" not in record
    assert (tmp_path / record["source_path"]).is_file()
