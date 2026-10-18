"""Unit coverage for the no-write foreign-roster topology comparator."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_foreign_mode1_roster_topology import compare_slots  # noqa: E402


def test_compare_slots_accepts_identical_rows() -> None:
    rows = [{"slot_index": 0, "flag": 1, "player_carrier_id": 42}]
    assert compare_slots(expected=rows, actual=rows) is None


def test_compare_slots_reports_first_changed_fixed_row() -> None:
    expected = [{"slot_index": 0, "flag": 1, "player_carrier_id": 42}]
    actual = [{"slot_index": 0, "flag": 1, "player_carrier_id": 99}]
    assert compare_slots(expected=expected, actual=actual) == {
        "kind": "fixed-roster-tail-changed",
        "expected_count": 1,
        "actual_count": 1,
        "first_difference_slot_index": 0,
        "expected_slot": expected[0],
        "actual_slot": actual[0],
    }
