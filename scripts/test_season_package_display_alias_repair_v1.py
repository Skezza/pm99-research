"""Focused tests for deterministic display-name alias derivation."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_display_alias_repair_v1 as repair  # noqa: E402


def test_portable_source_text_transliterates_non_cp1252_and_strips_format_marks() -> None:
    assert repair._portable_source_text("Sadıqov, Rəşad F.") == "Sadiqov, Resad F."
    assert repair._portable_source_text("Nemanja Vidic\u200e") == "Nemanja Vidic"


def test_candidate_names_preserve_source_then_use_identity_safe_aliases() -> None:
    candidates = repair._candidate_names(
        source_name="Steve Aspinall",
        requested_name="Steve Aspinall",
        native_name="John Jerome",
    )
    assert candidates[:4] == [
        ("Steve Aspinall", "requested-display-name"),
        ("S. Aspinall", "source-derived-initial-surname"),
        ("Aspinall", "source-derived-surname"),
        ("Steve A.", "source-derived-given-initial"),
    ]
    assert candidates[-1] == ("John Jerome", "retain-native-display-name")


def test_comma_ordered_source_prefers_initial_and_surname() -> None:
    candidates = repair._candidate_names(
        source_name="Sadıqov, Rəşad F.",
        requested_name="Sadıqov, Rəşad F.",
        native_name="Vidadi Rzayev",
    )
    assert ("R. Sadiqov", "source-derived-initial-surname") in candidates
    assert ("Sadiqov", "source-derived-surname") in candidates
