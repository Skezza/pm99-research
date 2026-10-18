"""Focused tests for clean-base world package projection policies."""

from pathlib import Path

from scripts.build_2015_world_strict_v2_package import (
    _fit_source_players_to_native_roster,
    _source_rating_method,
)


def test_native_roster_fit_preserves_slot_count_and_records_dropped_depth() -> None:
    source = [
        {"player_carrier_id": 900 + index, "slot_index": index, "source_player": {"name": name}}
        for index, name in enumerate(("Starter", "Reserve", "Depth"))
    ]
    fitted, receipt = _fit_source_players_to_native_roster(source, [10, 20])
    assert [row["player_carrier_id"] for row in fitted] == [10, 20]
    assert [row["source_candidate_carrier_id"] for row in fitted] == [900, 901]
    assert [row["slot_index"] for row in fitted] == [0, 1]
    assert receipt == {
        "native_slot_count": 2,
        "dated_source_player_count": 3,
        "dated_players_written": 2,
        "dated_players_dropped": 1,
        "native_tail_preserved": 0,
    }


def test_native_roster_fit_reports_preserved_tail_slots() -> None:
    fitted, receipt = _fit_source_players_to_native_roster(
        [{"player_carrier_id": 900, "slot_index": 0}], [10, 20, 30]
    )
    assert [row["player_carrier_id"] for row in fitted] == [10]
    assert receipt["native_tail_preserved"] == 2
    assert receipt["dated_players_dropped"] == 0


def test_rating_provenance_distinguishes_fifa_and_deterministic_fallback() -> None:
    assert _source_rating_method({"rating_disposition": {"status": "fifa16-complete-candidate"}}) == "fifa-nearest-edition"
    assert _source_rating_method({"rating_disposition": {"status": "editorial-fallback-applied"}}) == "deterministic-context"


def test_ownership_review_is_not_described_as_editorial_rating_provenance() -> None:
    source = Path(__file__).with_name("build_2015_world_strict_v2_package.py").read_text(encoding="utf-8")
    assert 'rating_method = "preserved-baseline-readback"' in source
    assert '"reviewed-editorial"\n                    if sourced == "ownership-displaced"' not in source


def test_goalkeeper_handling_guard_is_a_named_deterministic_policy() -> None:
    source = Path(__file__).with_name("build_2015_world_strict_v2_package.py").read_text(encoding="utf-8")
    assert 'ratings["handling"] < ratings["quality"] - 15' in source
    assert 'rating_method = "deterministic-goalkeeper-handling-guard"' in source
