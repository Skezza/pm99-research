"""Tests for the read-only source-club selection proposal queue."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_source_club_selection_proposals_v1 as proposals  # noqa: E402


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _selector(club_name: str, source_path: str) -> dict[str, str]:
    return {
        "country_catalog": "england",
        "competition_catalog": "national-league",
        "club_name": club_name,
        "source_path": source_path,
        "source_sha256": _sha(source_path),
    }


def _source_row(*, player: str, selector: dict[str, str]) -> dict:
    return {
        "id": f"player-{player}",
        "person_id": f"person-source-{player}",
        "role": "current-source",
        "source_trace": {
            "mapped_source_club_name": selector["club_name"],
            "matches": [{"selector": selector, "source_row_sha256": _sha(player)}],
            "state": "exact-source-row-match",
        },
    }


def _collision(*, name: str, left: dict[str, str], right: dict[str, str], signal: bool) -> dict:
    return {
        "candidate": {"normalised_name": name, "birth_date": "1990-01-01", "nationality": "ENG"},
        "classification": "source-source",
        "likely_duplicate_club_representation_signals": ([{
            "clubs": sorted([left["club_name"], right["club_name"]]),
            "method": "bare-name-versus-terminal-generic-club-suffix",
        }] if signal else []),
        "rows": [
            _source_row(player=f"{name}-left", selector=left),
            _source_row(player=f"{name}-right", selector=right),
        ],
    }


def _matrix() -> dict:
    aldershot_full = _selector("Aldershot Town", "all-season/aldershot")
    aldershot_august = _selector("Aldershot", "opening-date/aldershot")
    alpha = _selector("Alpha City", "all-season/alpha")
    bravo = _selector("Bravo United", "opening-date/bravo")
    return {
        "schema_version": proposals.MATRIX_SCHEMA,
        "state": proposals.MATRIX_STATE,
        "seasons": [{
            "season": {"start_year": 2016, "end_year": 2017, "label": "2016/17"},
            "input_package": {"path": "draft.json", "sha256": _sha("draft")},
            "build_audit": {
                "path": "audit.json", "sha256": _sha("audit"), "source_intake_sha256": _sha("intake"),
            },
            "source_intake_trace": {"state": "matched", "matched_paths": ["intake.json"]},
            "collisions": [
                _collision(name="aliasone", left=aldershot_full, right=aldershot_august, signal=True),
                _collision(name="aliastwo", left=aldershot_full, right=aldershot_august, signal=True),
                _collision(name="possibletransfer", left=alpha, right=bravo, signal=False),
                {
                    "candidate": {"normalised_name": "legacy", "birth_date": "1990-01-01", "nationality": "ENG"},
                    "classification": "source-legacy",
                    "likely_duplicate_club_representation_signals": [],
                    "rows": [],
                },
            ],
        }],
    }


def test_direct_label_signals_group_without_selecting_an_owner(tmp_path: Path) -> None:
    report = proposals.build_report(
        matrix=_matrix(), matrix_path=tmp_path / "matrix.json", matrix_sha256=_sha("matrix"),
    )
    proposals.validate_report(report, expected_season_count=1)

    season = report["seasons"][0]
    direct = season["direct_label_normalised_alias_candidates"]
    assert len(direct) == 1
    assert direct[0]["classification"] == "direct-label-normalised-alias-candidate"
    assert len(direct[0]["evidence"]) == 2
    assert direct[0]["review_contract"]["automatic_choice"] == "prohibited"
    assert "canonical_selector" not in direct[0]
    assert "selected_selector" not in direct[0]
    assert report["summary"] == {
        "ambiguous_player_overlap_count": 1,
        "direct_label_normalised_alias_candidate_count": 1,
        "direct_label_normalised_collision_count": 2,
        "season_count": 1,
        "source_source_collision_count": 3,
    }


def test_non_signal_source_overlap_stays_ambiguous_and_report_is_deterministic(tmp_path: Path) -> None:
    matrix = _matrix()
    first = proposals.build_report(
        matrix=matrix, matrix_path=tmp_path / "matrix.json", matrix_sha256=_sha("matrix"),
    )
    second = proposals.build_report(
        matrix=matrix, matrix_path=tmp_path / "matrix.json", matrix_sha256=_sha("matrix"),
    )
    assert proposals.canonical_json_bytes(first) == proposals.canonical_json_bytes(second)
    ambiguous = first["seasons"][0]["ambiguous_player_overlaps"]
    assert len(ambiguous) == 1
    assert ambiguous[0]["classification"] == "ambiguous-player-overlap"
    assert "review_contract" not in ambiguous[0]


def test_report_validator_rejects_an_automatic_selection(tmp_path: Path) -> None:
    report = proposals.build_report(
        matrix=_matrix(), matrix_path=tmp_path / "matrix.json", matrix_sha256=_sha("matrix"),
    )
    proposal = report["seasons"][0]["direct_label_normalised_alias_candidates"][0]
    proposal["canonical_selector"] = proposal["source_selectors"][0]
    with pytest.raises(proposals.ProposalError, match="must not make a source selection"):
        proposals.validate_report(report, expected_season_count=1)
