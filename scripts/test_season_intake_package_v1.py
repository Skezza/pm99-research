"""Tests for the generic strict source-intake to V2 package bridge."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_intake_package_v1 as projector  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


HASH = "a" * 64


def _proof() -> dict[str, str]:
    return {"grade": "source-captured", "artifact_id": "receipt-contract"}


def _intake() -> dict:
    players = []
    for number in range(1, 12):
        player_id = f"player-{number:03d}"
        players.append({
            "id": player_id,
            "person_id": f"person-player-{number:03d}",
            "carrier_id": 1000 + number,
            "carrier_family": "dd6361",
            "club_id": "club-example-town",
            "name": f"Player {number}",
            "source_name": f"Player {number}",
            "facts": {
                "birth_date": f"198{number % 10}-01-01",
                "nationality": "ENG",
                "height_cm": 180,
                "weight_kg": 75,
                "primary_position": "G" if number == 1 else "M",
                "fine_roles": [0],
                "shirt_number": number,
            },
            "proof": _proof(),
        })
    return {
        "schema_version": projector.INTAKE_SCHEMA,
        "intake_id": "intake-2000-01-fixture",
        "season": {"start_year": 2000, "end_year": 2001, "label": "2000/01"},
        "scope": {
            "id": "fixture-existing-carriers",
            "title": "Fixture existing carrier scope",
            "countries": ["ENG"],
            "competition_policy": "existing-carriers-only",
        },
        "artifacts": [
            {"id": "calendar-output", "kind": "calendar-patch", "sha256": HASH},
            {"id": "kit-home", "kind": "kit-render", "sha256": HASH},
            {"id": "receipt-contract", "kind": "season-input", "sha256": HASH},
        ],
        "sources": [{
            "id": "source-ledger",
            "title": "Fixture source ledger",
            "proof_grade": "source-captured",
            "evidence_artifact_id": "receipt-contract",
        }],
        "clubs": [{
            "id": "club-example-town",
            "identity_id": "club-identity-example-town",
            "carrier_id": 600,
            "name": "Example Town",
            "division": "Fixture Division",
            "manager_id": "manager-example-town",
            "roster_player_ids": [f"player-{number:03d}" for number in range(1, 12)],
            "proof": _proof(),
        }],
        "players": players,
        "managers": [{
            "id": "manager-example-town",
            "person_id": "person-manager-example-town",
            "carrier_id": 700,
            "name": "Fixture Manager",
            "proof": _proof(),
        }],
        "calendar": {
            "base_year": 1998,
            "target_year": 2000,
            "target_rollover_year": 2001,
            "patch_artifact_id": "calendar-output",
            "proof": _proof(),
        },
        "proofs": [{
            "id": "proof-source-capture",
            "grade": "source-captured",
            "artifact_id": "receipt-contract",
            "covers": ["fixture historical source facts"],
        }],
        "migration": {
            "status": "native-v2",
            "source_artifact_ids": ["receipt-contract"],
            "known_gaps": [],
        },
    }


def _overlay(intake: dict, *, overlay_id: str = "overlay-fixture-all") -> dict:
    intake_sha = projector._sha256_document(intake)
    return {
        "schema_version": projector.OVERLAY_SCHEMA,
        "overlay_id": overlay_id,
        "intake_sha256": intake_sha,
        "package_id": "package-2000-01-fixture",
        "club_openings": [{
            "club_id": "club-example-town",
            "opening": {
                "fixture_date": "2000-08-12",
                "starting_xi_player_ids": [f"player-{number:03d}" for number in range(1, 12)],
                "substitute_player_ids": [],
                "formation": "4-4-2",
                "tactics_positions": [[128, 55, 128, 55] for _ in range(11)],
                "proof": _proof(),
            },
        }],
        "club_kits": [{
            "club_id": "club-example-town",
            "artifact_ids": ["kit-home"],
            "proof": _proof(),
        }],
        "player_ratings": [{
            "player_id": f"player-{number:03d}",
            "ratings": {
                "profile": "pm99-visible-skills-v1",
                "values": {
                    "quality": 60,
                    "speed": 60,
                    "stamina": 60,
                    "aggression": 60,
                    "passing": 60,
                    "tackling": 60,
                    "heading": 60,
                    "shooting": 60,
                    "dribbling": 60,
                    "handling": 60,
                },
                "provenance": {
                    "method": "fixture editorial rating",
                    "proof_grade": "reviewed-editorial",
                    "source_ids": ["source-ledger"],
                },
            },
        } for number in range(1, 12)],
        "player_portraits": [{
            "player_id": f"player-{number:03d}",
            "status": "native-no-photo",
            "review_reason": "Fixture intentionally records the native no-photo fallback.",
            "proof": _proof(),
        } for number in range(1, 12)],
    }


def test_projects_a_complete_generic_intake_to_a_strict_package() -> None:
    intake = _intake()
    overlay = _overlay(intake)
    package, receipt = projector.project_package(
        intake=intake,
        overlays=[(overlay, projector._sha256_document(overlay))],
    )
    package_v2.validate_package(package, strict=True)
    assert package["package_id"] == "package-2000-01-fixture"
    assert package["clubs"][0]["opening"]["formation"] == "4-4-2"
    assert len(package["assets"]["portraits"]) == 11
    assert receipt["coverage"] == {
        "club_count": 1,
        "manager_count": 1,
        "player_count": 11,
        "kit_declaration_count": 1,
        "portrait_declaration_count": 11,
    }


def test_refuses_incomplete_editorial_coverage() -> None:
    intake = _intake()
    overlay = _overlay(intake)
    overlay["player_ratings"].pop()
    with pytest.raises(projector.IntakePackageError, match="player_ratings incomplete"):
        projector.project_package(
            intake=intake,
            overlays=[(overlay, projector._sha256_document(overlay))],
        )


def test_refuses_stale_overlay_even_if_its_rows_are_complete() -> None:
    intake = _intake()
    overlay = _overlay(intake)
    overlay["intake_sha256"] = "0" * 64
    with pytest.raises(projector.IntakePackageError, match="different source intake"):
        projector.project_package(
            intake=intake,
            overlays=[(overlay, projector._sha256_document(overlay))],
        )


def test_refuses_missing_source_fact_before_constructing_package() -> None:
    intake = _intake()
    broken = copy.deepcopy(intake)
    broken["players"][0]["facts"].pop("nationality")
    overlay = _overlay(broken)
    with pytest.raises(projector.IntakePackageError, match="must contain every strict player fact"):
        projector.project_package(
            intake=broken,
            overlays=[(overlay, projector._sha256_document(overlay))],
        )


def test_accepts_logged_secondary_fact_fallback() -> None:
    intake = _intake()
    player = intake["players"][0]
    player["facts"]["nationality"] = "UNK"
    player["fact_fallbacks"] = [{
        "field": "nationality",
        "method": "deterministic-default",
        "value": "UNK",
        "reason": "No reliable target-season nationality source was available.",
        "proof": _proof(),
    }]
    overlay = _overlay(intake)
    package, _receipt = projector.project_package(
        intake=intake,
        overlays=[(overlay, projector._sha256_document(overlay))],
    )
    assert package["players"][0]["fact_fallbacks"][0]["field"] == "nationality"


def test_refuses_unlogged_preserve_fallback_and_primary_position_fallback() -> None:
    intake = _intake()
    intake["players"][0]["facts"]["height_cm"] = {"policy": "preserve-existing-mode1"}
    overlay = _overlay(intake)
    with pytest.raises(projector.IntakePackageError, match="must be logged"):
        projector.project_package(
            intake=intake,
            overlays=[(overlay, projector._sha256_document(overlay))],
        )

    intake = _intake()
    intake["players"][0]["facts"]["primary_position"] = {
        "policy": "preserve-existing-mode1"
    }
    overlay = _overlay(intake)
    with pytest.raises(projector.IntakePackageError, match="required and cannot use"):
        projector.project_package(
            intake=intake,
            overlays=[(overlay, projector._sha256_document(overlay))],
        )


def test_refuses_two_overlays_that_change_the_same_field_target() -> None:
    intake = _intake()
    left = _overlay(intake, overlay_id="overlay-fixture-left")
    right = _overlay(intake, overlay_id="overlay-fixture-right")
    right["club_openings"] = []
    right["club_kits"] = []
    right["player_portraits"] = []
    with pytest.raises(projector.IntakePackageError, match="same player_ratings target"):
        projector.project_package(
            intake=intake,
            overlays=[
                (left, projector._sha256_document(left)),
                (right, projector._sha256_document(right)),
            ],
        )
