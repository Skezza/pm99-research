from __future__ import annotations

import pytest

from scripts.compose_season_source_captures_v1 import compose
from scripts.merge_footballsquads_captures import MergeError


def capture(repository: str, club: str) -> dict:
    return {
        "schema_version": "pm99-footballsquads-season-capture-v1",
        "source": {"title": repository, "repository": repository, "revision": "r", "license": "l"},
        "clubs": [{"country_catalog": repository, "competition_catalog": "top", "club_name": club,
                   "source_path": club, "source_sha256": "a" * 64, "players": [{"name": "P"}]}],
    }


def test_compose_preserves_different_source_credits() -> None:
    result = compose(inputs=[("a.json", capture("one", "A"), "1" * 64),
                             ("b.json", capture("two", "B"), "2" * 64)], catalog="2000-2001", label="2000/01")
    assert result["summary"]["club_count"] == 2
    assert [row["source"]["repository"] for row in result["source"]["inputs"]] == ["one", "two"]


def test_compose_rejects_duplicate_selector() -> None:
    same = capture("one", "A")
    with pytest.raises(MergeError, match="duplicate"):
        compose(inputs=[("a", same, "1" * 64), ("b", same, "2" * 64)], catalog="x", label="x")
