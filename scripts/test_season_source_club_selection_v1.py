"""Tests for the explicit all-season versus opening-date source selector stage."""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_source_club_selection_v1 as selection_v1  # noqa: E402


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _selector(*, club: str, source_path: str, source_sha: str) -> dict:
    return {
        "country_catalog": "eng",
        "competition_catalog": "national",
        "club_name": club,
        "source_path": source_path,
        "source_sha256": source_sha,
    }


def _club(*, selector: dict, player_names: list[str]) -> dict:
    return {
        "selector": selector,
        "competition_name": "National League",
        "players": [
            {
                "source_row_index": index,
                "source_row_sha256": _sha(name),
                "facts": {"name": name},
            }
            for index, name in enumerate(player_names)
        ],
    }


def _intake() -> dict:
    all_season = _selector(club="Aldershot Town", source_path="eng/alder.txt", source_sha=_sha("all"))
    august = _selector(club="Aldershot", source_path="soccerbase/team/92/august", source_sha=_sha("august"))
    other = _selector(club="Braintree Town", source_path="eng/braintree.txt", source_sha=_sha("other"))
    return {
        "schema_version": selection_v1.SOURCE_INTAKE_SCHEMA,
        "intake_id": "world-2016-17-source-intake",
        "season": {"catalog": "2016-2017", "label": "2016/17"},
        "source": {"title": "Composed credited captures", "repository": "example"},
        "source_capture_sha256": _sha("capture"),
        "source_clubs": [
            _club(selector=all_season, player_names=["All-season One", "All-season Two"]),
            _club(selector=other, player_names=["Braintree Player"]),
            _club(selector=august, player_names=["August One", "August Two"]),
        ],
    }


def _manifest(intake: dict) -> dict:
    all_season, _other, august = [row["selector"] for row in intake["source_clubs"]]
    return {
        "schema_version": selection_v1.MANIFEST_SCHEMA,
        "selection_id": "world-2016-17-opening-source-selection",
        "season": copy.deepcopy(intake["season"]),
        "inputs": {
            "source_intake_sha256": selection_v1._sha256_document(intake),
            "source_capture_sha256": intake["source_capture_sha256"],
        },
        "selections": [{
            "id": "aldershot-opening-source",
            "canonical_selector": all_season,
            "selected_selector": august,
            "basis": selection_v1.SELECTION_BASIS,
        }],
    }


def test_explicit_selection_retains_canonical_selector_and_uses_exact_august_rows() -> None:
    intake = _intake()
    result, audit = selection_v1.build_selection(source_intake=intake, manifest=_manifest(intake))

    assert result["summary"] == {
        "raw_source_club_count": 3,
        "explicit_selection_count": 1,
        "suppressed_alias_source_club_count": 1,
        "effective_source_club_count": 2,
        "raw_source_player_count": 5,
        "effective_source_player_count": 3,
    }
    assert [row["selector"]["club_name"] for row in result["effective_source_clubs"]] == [
        "Aldershot Town", "Braintree Town"
    ]
    assert [row["facts"]["name"] for row in result["effective_source_clubs"][0]["players"]] == [
        "August One", "August Two"
    ]
    assert result["selections"][0]["canonical_source"]["selector"]["club_name"] == "Aldershot Town"
    assert result["selections"][0]["selected_source"]["selector"]["club_name"] == "Aldershot"
    assert audit["state"] == selection_v1.STATE
    assert "database compilation" in audit["not_performed"]
    selection_v1.validate_selection(selection=result, source_intake=intake)


def test_selection_is_byte_deterministic_and_preserves_raw_input() -> None:
    intake = _intake()
    manifest = _manifest(intake)
    first = selection_v1.build_selection(source_intake=intake, manifest=manifest)
    second = selection_v1.build_selection(source_intake=intake, manifest=manifest)
    assert selection_v1.canonical_json_bytes(first[0]) == selection_v1.canonical_json_bytes(second[0])
    assert intake == _intake()


def test_refuses_unknown_selector_and_stale_raw_hash() -> None:
    intake = _intake()
    unknown = _manifest(intake)
    unknown["selections"][0]["selected_selector"] = _selector(
        club="Unknown", source_path="missing", source_sha=_sha("missing")
    )
    with pytest.raises(selection_v1.SourceClubSelectionError, match="absent from source intake"):
        selection_v1.build_selection(source_intake=intake, manifest=unknown)

    stale = _manifest(intake)
    stale["inputs"]["source_intake_sha256"] = _sha("not the intake")
    with pytest.raises(selection_v1.SourceClubSelectionError, match="does not bind"):
        selection_v1.build_selection(source_intake=intake, manifest=stale)


def test_refuses_selector_reuse_so_one_capture_cannot_silently_own_two_clubs() -> None:
    intake = _intake()
    manifest = _manifest(intake)
    all_season, other, august = [row["selector"] for row in intake["source_clubs"]]
    manifest["selections"].append({
        "id": "braintree-opening-source",
        "canonical_selector": other,
        "selected_selector": august,
        "basis": selection_v1.SELECTION_BASIS,
    })
    with pytest.raises(selection_v1.SourceClubSelectionError, match="reuses a selected selector"):
        selection_v1.build_selection(source_intake=intake, manifest=manifest)


def test_detects_tampered_projection() -> None:
    intake = _intake()
    result, _audit = selection_v1.build_selection(source_intake=intake, manifest=_manifest(intake))
    result["effective_source_clubs"][0]["players"][0]["facts"]["name"] = "Unsourced edit"
    with pytest.raises(selection_v1.SourceClubSelectionError, match="does not exactly match"):
        selection_v1.validate_selection(selection=result, source_intake=intake)
