"""Fixture tests for explicit partial and blocked carrier dispositions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_2015_unresolved_disposition_ledger import build


def test_partial_prefix_and_native_tail_are_separate() -> None:
    draft = {"proposals": [{"carrier_id": 1, "group": "test", "baseline_name": "Club", "fixed_roster_slot_count": 3, "status": "undersized-source-squad", "source_selector": {"source_path": "club.html"}}]}
    capture = {"clubs": [{"candidate_carrier_id": 1, "source_url": "https://example.test/club", "source_sha256": "abc", "source_path": "club.html", "players": [{"name": "One", "position": "G"}, {"name": "Two", "position": "D"}], "supplemental_sources": []}]}
    result = build(draft=draft, source_capture=capture, draft_sha256="draft", capture_sha256="capture")
    row = result["dispositions"][0]
    assert row["sourced_prefix_count"] == 2
    assert row["preserved_native_tail_count"] == 1
    assert row["release_disposition"] == "partial-sourced-prefix-preserved-native-tail"


def test_blocked_rows_have_next_action() -> None:
    draft = {"proposals": [{"carrier_id": 2, "group": "test", "baseline_name": "Missing", "fixed_roster_slot_count": 3, "status": "no-captured-source-country"}]}
    result = build(draft=draft, source_capture={"clubs": []}, draft_sha256="draft", capture_sha256="capture")
    assert result["coverage"]["genuinely_blocked_carrier_count"] == 1
    assert "acquire a dated" in result["dispositions"][0]["next_action"]


if __name__ == "__main__":
    test_partial_prefix_and_native_tail_are_separate()
    test_blocked_rows_have_next_action()
    print("manual fixture tests: ok")
