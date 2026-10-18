"""Tests for the fail-closed safe source-club selection manifest generator."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_safe_source_club_selection_v1 as safe  # noqa: E402


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _selector(club_name: str, *, opening: bool) -> dict[str, str]:
    if opening:
        return {
            "club_name": club_name,
            "competition_catalog": "soccerbase-august",
            "country_catalog": "english-non-league",
            "source_path": "soccerbase/team/99/august",
            "source_sha256": _sha("opening"),
        }
    return {
        "club_name": club_name,
        "competition_catalog": "national",
        "country_catalog": "eng",
        "source_path": "eng/2016-2017/national/alpha.txt",
        "source_sha256": _sha("canonical"),
    }


def _proposal() -> dict:
    canonical = _selector("Alpha Town", opening=False)
    opening = _selector("Alpha", opening=True)
    return {
        "proposal_id": "source-club-review-0123456789abcdef0123",
        "direct_label_normalised_alias_signal": {
            "clubs": ["Alpha", "Alpha Town"],
            "method": "bare-name-versus-terminal-generic-club-suffix",
        },
        "source_selectors": [canonical, opening],
        "evidence": [{
            "candidate": {"normalised_name": "player", "birth_date": "1990-01-01", "nationality": "ENG"},
            "source_rows": [
                {"selector": canonical, "source_row_sha256": _sha("left")},
                {"selector": opening, "source_row_sha256": _sha("right")},
            ],
        }],
    }


def _allocation() -> dict:
    canonical = _selector("Alpha Town", opening=False)
    return {
        "assignments": [{
            "carrier_id": 42,
            "club_name": "Alpha Town",
            "method": "continuing-club-normalized-identity",
            "source_selector": {
                "competition_catalog": canonical["competition_catalog"],
                "country_catalog": canonical["country_catalog"],
                "source_path": canonical["source_path"],
                "source_sha256": canonical["source_sha256"],
            },
        }],
    }


def _source_intake() -> dict:
    canonical = _selector("Alpha Town", opening=False)
    opening = _selector("Alpha", opening=True)
    return {
        "schema_version": "pm99-season-source-intake-v1",
        "season": {"catalog": "2016-2017", "label": "2016/17"},
        "source_capture_sha256": _sha("capture"),
        "source": {"title": "fixture source"},
        "source_clubs": [
            {
                "selector": canonical,
                "competition_name": "National League",
                "players": [{
                    "facts": {"name": "Jamie Grimes", "birth_date": "1990-12-22", "nationality": "ENG"},
                    "source_row_sha256": _sha("player-one"),
                }],
            },
            {
                "selector": opening,
                "competition_name": "National League",
                "players": [{
                    "facts": {"name": "Jamie Grimes", "birth_date": "1990-12-22", "nationality": "ENG"},
                    "source_row_sha256": _sha("player-two"),
                }],
            },
        ],
    }


def test_safe_direct_alias_yields_a_hash_bound_selection_manifest_entry() -> None:
    proposal = _proposal()
    entry, audit = safe._candidate_or_rejection(
        proposal=proposal,
        allocation=_allocation(),
        ambiguous_keys=set(),
        exclusion_by_pair={},
        label="fixture",
    )
    assert audit is not None
    assert entry is not None
    assert entry["canonical_selector"]["club_name"] == "Alpha Town"
    assert entry["selected_selector"]["club_name"] == "Alpha"
    assert audit["allocated_canonical_club"]["carrier_id"] == 42

    source_intake = _source_intake()
    manifest = safe._source_intake_manifest(
        season={"start_year": 2016, "end_year": 2017, "label": "2016/17"},
        source_intake=source_intake,
        source_intake_sha256=safe._sha256_value(source_intake),
        selections=[entry],
    )
    assert manifest["schema_version"] == "pm99-season-source-club-selection-manifest-v1"
    assert manifest["selections"] == [entry]


def test_ambiguous_player_interclub_overlap_is_never_auto_selected() -> None:
    proposal = _proposal()
    opening_key = safe._selector_sort_key(proposal["source_selectors"][1])
    entry, rejected = safe._candidate_or_rejection(
        proposal=proposal,
        allocation=_allocation(),
        ambiguous_keys={opening_key},
        exclusion_by_pair={},
        label="fixture",
    )
    assert entry is None
    assert rejected == {
        "proposal_id": "source-club-review-0123456789abcdef0123",
        "reason": "selector-occurs-in-ambiguous-player-interclub-overlap",
    }


def test_missing_unique_canonical_allocation_is_rejected() -> None:
    proposal = _proposal()
    entry, rejected = safe._candidate_or_rejection(
        proposal=proposal,
        allocation={"assignments": []},
        ambiguous_keys=set(),
        exclusion_by_pair={},
        label="fixture",
    )
    assert entry is None
    assert rejected == {
        "proposal_id": "source-club-review-0123456789abcdef0123",
        "reason": "canonical-source-is-not-a-unique-exact-allocated-club",
        "matching_allocated_carrier_count": 0,
    }


def test_manifest_is_byte_deterministic_and_existing_root_is_not_replaced(tmp_path: Path) -> None:
    proposal = _proposal()
    entry, _audit = safe._candidate_or_rejection(
        proposal=proposal,
        allocation=_allocation(),
        ambiguous_keys=set(),
        exclusion_by_pair={},
        label="fixture",
    )
    assert entry is not None
    source_intake = _source_intake()
    first = safe._source_intake_manifest(
        season={"start_year": 2016, "end_year": 2017, "label": "2016/17"},
        source_intake=source_intake,
        source_intake_sha256=safe._sha256_value(source_intake),
        selections=[entry],
    )
    second = safe._source_intake_manifest(
        season={"start_year": 2016, "end_year": 2017, "label": "2016/17"},
        source_intake=source_intake,
        source_intake_sha256=safe._sha256_value(source_intake),
        selections=[entry],
    )
    assert safe.canonical_json_bytes(first) == safe.canonical_json_bytes(second)
    root = tmp_path / "new-root"
    safe.write_safe_manifests(output_root=root, manifests={"2016-17": first}, receipt={"ok": True})
    with pytest.raises(safe.SafeSelectionError, match="refusing to overwrite"):
        safe.write_safe_manifests(output_root=root, manifests={"2016-17": first}, receipt={"ok": True})


def test_hash_bound_known_interclub_exclusion_blocks_an_otherwise_safe_alias() -> None:
    proposal = _proposal()
    source_intake = _source_intake()
    intake_sha = safe._sha256_value(source_intake)
    report_sha = _sha("report")
    matrix_sha = _sha("matrix")
    exclusion_manifest = {
        "schema_version": safe.EXCLUSION_SCHEMA,
        "policy_id": "fixture-known-interclub-exclusions",
        "inputs": {"proposal_report_sha256": report_sha, "collision_matrix_sha256": matrix_sha},
        "exclusions": [{
            "id": "fixture-alpha-known-conflict",
            "reason": "known-interclub-conflict-requires-dated-opening-evidence",
            "proposal_id": proposal["proposal_id"],
            "season": {"catalog": "2016-2017", "label": "2016/17"},
            "source_intake_sha256": intake_sha,
            "source_capture_sha256": source_intake["source_capture_sha256"],
            "source_selectors": proposal["source_selectors"],
            "person_claims": [{
                "name": "Jamie Grimes", "birth_date": "1990-12-22", "nationality": "ENG",
            }],
        }],
    }
    exclusions, audit = safe._validated_exclusions(
        exclusion_manifest=exclusion_manifest,
        exclusion_manifest_sha256=safe._sha256_value(exclusion_manifest),
        proposal_report_sha256=report_sha,
        collision_matrix_sha256=matrix_sha,
        proposal_report={"seasons": [{
            "season": {"label": "2016/17"},
            "direct_label_normalised_alias_candidates": [proposal],
        }]},
        source_intakes={"2016/17": (source_intake, intake_sha)},
    )
    assert audit["validated_exclusion_count"] == 1
    entry, rejected = safe._candidate_or_rejection(
        proposal=proposal,
        allocation=_allocation(),
        ambiguous_keys=set(),
        exclusion_by_pair=exclusions["2016/17"],
        label="fixture",
    )
    assert entry is None
    assert rejected == {
        "exclusion_id": "fixture-alpha-known-conflict",
        "proposal_id": "source-club-review-0123456789abcdef0123",
        "reason": "known-interclub-conflict-explicitly-excluded-from-auto-selection",
    }
