from __future__ import annotations

import pytest

from scripts.compose_opening_manager_supplements_v1 import ManagerSupplementCompositionError, compose


def _doc(manager: str, source: str) -> dict:
    return {"schema_version": "pm99-opening-manager-supplement-v1", "season_start_year": 2001,
            "sources": {"credit": source}, "managers": [{"source_selector": {
                "country_catalog": "eng", "competition_catalog": "d3", "club_name": "Example"},
                "opening_fixture_date": "2001-08-11", "manager_name": manager,
                "source_name": source, "source_url": "https://example.test", "source_snapshot_sha256": "a" * 64,
                "reason": "dated source"}], "gaps": []}


def test_compose_deduplicates_agreeing_evidence_and_binds_inputs() -> None:
    result = compose([(_doc("Exact Manager", "A"), "1" * 64), (_doc("Exact Manager", "B"), "2" * 64)])
    assert result["summary"]["supplemented_manager_count"] == 1
    assert [row["sha256"] for row in result["sources"]["inputs"]] == ["1" * 64, "2" * 64]


def test_compose_refuses_conflicting_manager_names() -> None:
    with pytest.raises(ManagerSupplementCompositionError, match="conflicting"):
        compose([(_doc("One", "A"), "1" * 64), (_doc("Two", "B"), "2" * 64)])
