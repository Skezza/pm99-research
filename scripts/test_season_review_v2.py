"""Tests for source-only PM99 post-playtest review workflow."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2
from scripts import season_review_v2 as review


HASH = "a" * 64


def _proof(artifact_id: str = "receipt-contract") -> dict[str, str]:
    return {"grade": "static-contract", "artifact_id": artifact_id}


def _package() -> dict:
    players = []
    portraits = []
    for carrier_id in range(1, 12):
        player_id = f"player-{carrier_id}"
        players.append({
            "id": player_id, "person_id": f"person-fixture-player-{carrier_id}",
            "carrier_id": carrier_id,
            "carrier_family": "dd6361",
            "club_id": "club-100",
            "name": f"Player {carrier_id}",
            "facts": {
                "birth_date": "1990-01-01", "nationality": "ENG", "height_cm": 180,
                "weight_kg": 75, "primary_position": "G" if carrier_id == 1 else "M",
                "fine_roles": [0], "shirt_number": carrier_id,
            },
            "ratings": {
                "profile": "pm99-visible-skills-v1",
                "values": {key: 60 for key in review.RATING_KEYS},
                "provenance": {"method": "fixture", "proof_grade": "source-captured", "source_ids": ["source-ledger"]},
            },
            "proof": _proof(),
        })
        if carrier_id == 1:
            portraits.append({
                "player_id": player_id,
                "status": "native-no-photo",
                "review_reason": "no identity-safe era photograph was found",
                "proof": _proof(),
            })
        else:
            portraits.append({
                "player_id": player_id,
                "status": "applied",
                "original_artifact_id": "portrait-original",
                "crop_artifact_id": "portrait-crop",
                "conversion_receipt_artifact_id": "portrait-conversion",
                "output_container_artifact_id": "portrait-container",
                "proof": _proof(),
            })
    players.sort(key=lambda row: row["id"])
    portraits.sort(key=lambda row: row["player_id"])
    return {
        "schema_version": package_v2.SCHEMA_VERSION,
        "package_id": "pm99-2015-16-review-fixture",
        "season": {"start_year": 2015, "end_year": 2016, "label": "2015/16"},
        "scope": {"id": "english-four-divisions", "title": "Fixture scope", "countries": ["ENG"], "competition_policy": "proven-membership-only"},
        "artifacts": [
            {"id": "calendar-output", "kind": "calendar-patch", "sha256": HASH},
            {"id": "kit-home", "kind": "kit-render", "sha256": HASH},
            {"id": "portrait-container", "kind": "portrait-conversion", "sha256": HASH},
            {"id": "portrait-conversion", "kind": "portrait-conversion", "sha256": HASH},
            {"id": "portrait-crop", "kind": "portrait-crop", "sha256": HASH},
            {"id": "portrait-original", "kind": "portrait-original", "sha256": HASH},
            {"id": "receipt-contract", "kind": "season-input", "sha256": HASH},
        ],
        "sources": [{"id": "source-ledger", "title": "Fixture source", "proof_grade": "source-captured", "evidence_artifact_id": "receipt-contract"}],
        "clubs": [{
            "id": "club-100", "identity_id": "club-fixture-town", "carrier_id": 100, "name": "Fixture Town", "division": "Premier League",
            "manager_id": "manager-1", "roster_player_ids": [f"player-{number}" for number in range(1, 12)],
            "opening": {"fixture_date": "2015-08-08", "starting_xi_player_ids": [f"player-{number}" for number in range(1, 12)], "substitute_player_ids": [], "formation": "4-4-2", "tactics_positions": [[128, 55, 128, 55] for _ in range(11)], "proof": _proof()},
            "proof": _proof(),
        }],
        "players": players,
        "managers": [{"id": "manager-1", "person_id": "person-fixture-manager", "carrier_id": 1, "name": "Fixture Manager", "proof": _proof()}],
        "assets": {"kits": [{"club_id": "club-100", "artifact_ids": ["kit-home"], "proof": _proof()}], "portraits": portraits},
        "calendar": {"base_year": 1998, "target_year": 2015, "target_rollover_year": 2016, "patch_artifact_id": "calendar-output", "proof": _proof()},
        "proofs": [{"id": "proof-static", "grade": "static-contract", "artifact_id": "receipt-contract", "covers": ["fixture"]}],
        "migration": {"status": "native-v2", "source_artifact_ids": ["receipt-contract"], "known_gaps": []},
    }


def _overrides(package: dict) -> dict:
    return {
        "schema_version": review.OVERRIDES_SCHEMA,
        "override_id": "playtest-review-1",
        "base_package_canonical_sha256": review._package_hash(package),
        "artifacts": [{"id": "review-note", "kind": "season-input", "sha256": "b" * 64}],
        "sources": [{"id": "source-playtest", "title": "Named tester feedback", "proof_grade": "reviewed-editorial", "evidence_artifact_id": "review-note"}],
        "proofs": [{"id": "proof-playtest", "grade": "reviewed-editorial", "artifact_id": "review-note", "covers": ["player-2", "player-3"]}],
        "data_patches": [{
            "id": "player-2-speed", "target": {"entity": "player", "id": "player-2"},
            "expected": {"ratings.values.speed": 60}, "set": {"ratings.values.speed": 91},
            "reason": "playtest review found the speed rating too low", "proof": {"grade": "reviewed-editorial", "artifact_id": "review-note"},
            "rating_provenance": {"method": "playtest review correction", "proof_grade": "reviewed-editorial", "source_ids": ["source-playtest"]},
        }],
        "portrait_patches": [{
            "id": "player-3-remove-wrong-photo", "player_id": "player-3", "expected_status": "applied",
            "action": "set-native-no-photo", "reason": "review found the current portrait depicts the wrong player",
            "proof": {"grade": "reviewed-editorial", "artifact_id": "review-note"},
        }],
    }


def test_review_queue_is_machine_readable_and_names_no_photo_players() -> None:
    package = _package()
    package_v2.validate_package(package, strict=True)
    results = {
        "schema_version": review.PORTRAIT_RESULTS_SCHEMA,
        "package_canonical_sha256": review._package_hash(package),
        "results": sorted([
            {
                "player_id": f"player-{number}",
                "resulting_state": "native-no-photo" if number in {1, 2} else "applied",
                "reason_code": "download-failed" if number == 2 else "declared-no-photo" if number == 1 else "applied",
                "reason": "portrait download failed" if number == 2 else "no safe image exists" if number == 1 else "approved portrait applied",
            }
            for number in range(1, 12)
        ], key=lambda row: row["player_id"]),
    }
    review.validate_portrait_results(results, package)
    queue = review.build_portrait_review_queue(package, results)
    assert queue["summary"] == {"players_total": 11, "approved_portraits": 9, "native_no_photo": 2}
    assert queue["entries"] == [
        {
            "player_id": "player-1", "carrier_id": 1, "player_name": "Player 1", "club_id": "club-100", "club_name": "Fixture Town",
            "declared_state": "native-no-photo", "resulting_state": "native-no-photo", "pm99_photo_state": "native-no-photo",
            "reason_code": "declared-no-photo", "reason": "no safe image exists",
        },
        {
            "player_id": "player-2", "carrier_id": 2, "player_name": "Player 2", "club_id": "club-100", "club_name": "Fixture Town",
            "declared_state": "applied", "resulting_state": "native-no-photo", "pm99_photo_state": "native-no-photo",
            "reason_code": "download-failed", "reason": "portrait download failed",
        },
    ]


def test_overrides_derive_new_package_without_mutating_source() -> None:
    package = _package()
    before = package_v2.canonical_json_bytes(package)
    overrides = _overrides(package)
    review.validate_overrides(overrides)
    derived, receipt = review.apply_overrides(package, overrides, derived_package_id="pm99-2015-16-review-fixture-r1")
    assert package_v2.canonical_json_bytes(package) == before
    player = next(row for row in derived["players"] if row["id"] == "player-2")
    assert player["ratings"]["values"]["speed"] == 91
    assert player["ratings"]["provenance"]["source_ids"] == ["source-playtest"]
    portrait = next(row for row in derived["assets"]["portraits"] if row["player_id"] == "player-3")
    assert portrait == {
        "player_id": "player-3", "status": "native-no-photo",
        "review_reason": "review found the current portrait depicts the wrong player",
        "proof": {"grade": "reviewed-editorial", "artifact_id": "review-note"},
    }
    package_v2.validate_package(derived, strict=True)
    assert receipt["data_patch_count"] == 1
    assert receipt["portrait_patch_count"] == 1
    assert receipt["base_package_canonical_sha256"] == review._package_hash(package)


def test_stale_feedback_and_unsafe_paths_are_rejected() -> None:
    package = _package()
    overrides = _overrides(package)
    overrides["data_patches"][0]["expected"] = {"ratings.values.speed": 59}
    with pytest.raises(review.SeasonReviewError, match="stale target"):
        review.apply_overrides(package, overrides, derived_package_id="pm99-2015-16-review-fixture-r1")

    unsafe = _overrides(package)
    unsafe["data_patches"][0]["expected"] = {"club_id": "club-100"}
    unsafe["data_patches"][0]["set"] = {"club_id": "club-200"}
    with pytest.raises(review.SeasonReviewError, match="cannot write"):
        review.validate_overrides(unsafe)


def test_legacy_face_receipt_keeps_intentional_no_photo_distinct_from_unresolved(tmp_path: Path) -> None:
    package = _package()
    receipt = tmp_path / "face-receipt.json"
    receipt.write_text('{"rows":[{"record_id":1,"status":"intentionally-no-photo","no_verified_portrait_reason":"not found"},{"record_id":2,"status":"applied"},{"record_id":3,"status":"unresolved-download-failed"}]}', encoding="utf-8")
    results = review.portrait_results_from_legacy_face_receipt(package, receipt)
    result_by_player = {row["player_id"]: row for row in results["results"]}
    assert result_by_player["player-1"]["resulting_state"] == "native-no-photo"
    assert result_by_player["player-2"]["resulting_state"] == "applied"
    assert result_by_player["player-3"]["reason_code"] == "face-stage-download-failed"


def test_application_receipt_fails_unselected_players_open(tmp_path: Path) -> None:
    package = _package()
    receipt = tmp_path / "portrait-application.json"
    receipt.write_text(
        '{"operations":['
        '{"player_carrier_id":1,"resulting_state":"applied","candidate_status":"approved"},'
        '{"player_carrier_id":2,"resulting_state":"preserved-native-portrait","candidate_status":"identity-safe"},'
        '{"player_carrier_id":3,"resulting_state":"native-no-photo","candidate_status":"download-failed"}'
        ']}',
        encoding="utf-8",
    )
    results = review.portrait_results_from_application_receipt(package, receipt)
    by_player = {row["player_id"]: row for row in results["results"]}
    assert by_player["player-1"]["resulting_state"] == "applied"
    assert by_player["player-2"]["resulting_state"] == "applied"
    assert by_player["player-3"]["resulting_state"] == "native-no-photo"
    assert by_player["player-4"]["reason_code"] == "not-selected-by-legacy-portrait-stage"
    review.validate_portrait_results(results, package)
